"""VT-Lanternfly development API: upload, EXIF extraction, and YOLO inference.

Accounts, sightings, points, and map data use MySQL via SQLAlchemy.
"""
import hashlib
import secrets
import io
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import os
from pathlib import Path
from uuid import uuid4
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, Response
import logging

from services.image_verifier import detect_lanternflies

logger = logging.getLogger(__name__)
from PIL import Image, UnidentifiedImageError

from metadata_extractor import extract_metadata
from metadata_processor import process_metadata
from map_visualization import generate_map
from majors import MAJORS, validate_major

# User accounts (MySQL via SQLAlchemy)
import bcrypt
from fastapi import Depends
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import func, select, delete
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session

from database import SessionLocal, get_db
from db_models import Badge, PointEvent, QuizPass, Report, User, UserBadge, Team, TeamMember, Friendship, UserSession, GoalReward


BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = Path(os.environ.get("LANTERNFLY_UPLOAD_DIR", BASE_DIR / "uploads"))
MAX_UPLOAD_BYTES = 15 * 1024 * 1024
STAGE_POINTS = {"Adult": 10, "Black nymph": 10, "Red nymph": 10, "Egg mass": 15}
CORRECT_STAGE_BONUS = 5
QUIZ_POINTS = 10
LESSON_COUNT = 3

ALLOWED_FORMATS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp", "HEIF": ".heif", "HEIC": ".heic", "MPO": ".jpg"}

app = FastAPI(title="VT-Lanternfly API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8443", "http://127.0.0.1:8443", "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Content-Type", "X-Requested-With"],
)


SESSION_COOKIE = "vtlanternfly_session"
SESSION_SECONDS = 7 * 24 * 60 * 60
COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true"


@app.middleware("http")
async def protect_api_requests(request: Request, call_next):
    # A custom header forces cross-origin browser writes through CORS preflight.
    if (request.url.path.startswith("/api/")
            and request.method in {"POST", "PATCH", "PUT", "DELETE"}
            and request.headers.get("X-Requested-With") != "VT-Lanternfly"):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=403, content={"detail": "Invalid request origin"})
    response = await call_next(request)
    if request.url.path.startswith(("/api/auth/", "/api/me/", "/api/users/", "/api/leaderboard")):
        response.headers["Cache-Control"] = "no-store"
    return response


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _start_session(request: Request, response: Response, db: Session, user: User):
    old_token = request.cookies.get(SESSION_COOKIE)
    if old_token:
        db.execute(delete(UserSession).where(UserSession.token_hash == _token_hash(old_token)))
    token = secrets.token_urlsafe(32)
    db.add(UserSession(user_id=user.id, token_hash=_token_hash(token),
                       expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=SESSION_SECONDS)))
    db.commit()
    response.set_cookie(SESSION_COOKIE, token, max_age=SESSION_SECONDS,
                        httponly=True, secure=COOKIE_SECURE or request.url.scheme == "https", samesite="lax", path="/")


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        user = db.scalar(select(User).join(UserSession, UserSession.user_id == User.id).where(
            UserSession.token_hash == _token_hash(token),
            UserSession.expires_at > datetime.now(timezone.utc).replace(tzinfo=None),
        ))
        if user is not None:
            return user
    raise HTTPException(status_code=401, detail="Please log in again. Your session has expired or is invalid.")


@app.get("/api/auth/me")
def current_profile(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _user_profile(db, user)


@app.post("/api/auth/logout")
def logout_user(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        db.execute(delete(UserSession).where(UserSession.token_hash == _token_hash(token)))
        db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/", secure=COOKIE_SECURE or request.url.scheme == "https", httponly=True, samesite="lax")
    return {"message": "Logged out"}


@app.get("/api/majors")
def list_majors():
    return MAJORS


@app.get("/api/health")
def health():
    return {"status": "ok"}


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)  # bcrypt limit is 72 bytes
    display_name: str = Field(min_length=1, max_length=100)
    major: str | None = Field(default=None, max_length=100)

    @field_validator("major")
    @classmethod
    def official_major(cls, value: str | None) -> str | None:
        return validate_major(value)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def _user_points(db: Session, user_id: int) -> int:
    return db.scalar(
        select(func.coalesce(func.sum(PointEvent.points), 0)).where(PointEvent.user_id == user_id)
    )


def _goal_progress(db: Session, user_id: int) -> list[dict]:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    approved = select(func.count(Report.id)).where(Report.user_id == user_id, Report.review_status == "approved")
    rewards = {(r.goal_key, r.period_key) for r in db.scalars(select(GoalReward).where(GoalReward.user_id == user_id))}
    definitions = [
        ("report_3", "Report 3 verified lanternflies this week", 3,
         db.scalar(approved.where(Report.created_at >= week_start)), week_start.date().isoformat()),
        ("egg_mass", "Find 1 verified egg mass", 1,
         db.scalar(approved.where(Report.life_stage_verified == "Egg mass")), "all-time"),
        ("quiz", "Complete a Learn quiz", 1,
         db.scalar(select(func.count()).select_from(QuizPass).where(QuizPass.user_id == user_id)), "all-time"),
        ("invite", "Invite 1 friend", 1,
         db.scalar(select(func.count(User.id)).where(User.invited_by == user_id)), "all-time"),
    ]
    return [{"key": key, "label": label, "current": min(count, target), "target": target,
             "completed": count >= target, "rewarded": (key, period) in rewards,
             "period": period, "points": 10}
            for key, label, target, count, period in definitions]


def _award_goal_rewards(db: Session, user_id: int, goal_key: str, period: str) -> int:
    """Unique goal/period records keep bonuses idempotent, including concurrent requests."""
    db.flush()
    awarded = 0
    for goal in _goal_progress(db, user_id):
        if goal["key"] != goal_key:
            continue
        if goal["period"] != period:
            raise HTTPException(status_code=409, detail="This goal period has ended. Refresh your goals.")
        if goal["rewarded"]:
            return 0
        if not goal["completed"]:
            raise HTTPException(status_code=400, detail="Complete this goal before claiming its points.")
        try:
            with db.begin_nested():
                db.add(GoalReward(user_id=user_id, goal_key=goal["key"], period_key=goal["period"]))
                db.flush()
                db.add(PointEvent(user_id=user_id, points=10, reason=f"Goal completed: {goal['label']}"))
        except IntegrityError:
            # A simultaneous request already awarded this goal for this period.
            return 0
        awarded += 10
        return awarded
    raise HTTPException(status_code=404, detail="Goal not found")


class GoalClaim(BaseModel):
    goal_key: Literal["report_3", "egg_mass", "quiz", "invite"]
    period: str = Field(max_length=10)


@app.post("/api/me/goals/claim")
def claim_goals(claim: GoalClaim, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _award_goal_rewards(db, user.id, claim.goal_key, claim.period)
    db.commit()
    return _user_profile(db, user)


def _upload_streak(db: Session, user_id: int, now: datetime | None = None) -> int:
    return _upload_streaks(db, [user_id], now)[user_id]


def _upload_streaks(db: Session, user_ids: list[int], now: datetime | None = None) -> dict[int, int]:
    """Fetch streak activity together for profile and leaderboard requests."""
    now = now or datetime.now(timezone.utc)
    uploads = {user_id: [] for user_id in user_ids}
    if user_ids:
        for user_id, uploaded_at in db.execute(select(Report.user_id, Report.created_at).where(
            Report.user_id.in_(user_ids), Report.review_status == "approved",
            Report.created_at <= now.astimezone(timezone.utc).replace(tzinfo=None),
        ).order_by(Report.created_at.desc())):
            uploads[user_id].append(uploaded_at)
    return {user_id: _count_upload_streak(dates, now) for user_id, dates in uploads.items()}


def _count_upload_streak(uploads: list[datetime], now: datetime) -> int:
    """Consecutive approved upload days, with today allowed to be in progress."""
    campus_timezone = ZoneInfo("America/New_York")
    today = now.astimezone(campus_timezone).date()
    expected = today
    streak = 0
    for uploaded_at in uploads:
        day = uploaded_at.replace(tzinfo=timezone.utc).astimezone(campus_timezone).date()
        # Multiple approved photos in one day contribute just one streak day.
        if day > expected:
            continue
        if streak == 0 and day == today - timedelta(days=1):
            expected = day
        if day != expected:
            break
        streak += 1
        expected -= timedelta(days=1)
    return streak


def _user_profile(db: Session, user: User) -> dict:
    points = _user_points(db, user.id)

    totals = (
        select(PointEvent.user_id, func.sum(PointEvent.points).label("total"))
        .group_by(PointEvent.user_id)
        .subquery()
    )
    rank = 1 + db.scalar(select(func.count()).select_from(totals).where(totals.c.total > points))

    approved = select(func.count(Report.id)).where(
        Report.user_id == user.id, Report.review_status == "approved"
    )
    week_start = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=7)

    return {
        "id": user.id,
        "displayName": user.display_name,
        "major": user.major,
        "points": points,
        "rank": rank,
        "streak": _upload_streak(db, user.id),
        "reportsTotal": db.scalar(approved),
        "reportsThisWeek": db.scalar(approved.where(Report.created_at >= week_start)),
        "eggFound": bool(db.scalar(approved.where(Report.life_stage_verified == "Egg mass"))),
        "reportsByStage": {
            "adult": db.scalar(approved.where(Report.life_stage_verified == "Adult")),
            "nymph": db.scalar(approved.where(Report.life_stage_verified.in_(["Black nymph", "Red nymph"]))),
            "eggMass": db.scalar(approved.where(Report.life_stage_verified == "Egg mass")),
        },
        "anonymous": user.anonymous,
        "shareWithResearchers": user.share_with_researchers,
        "badges": list(db.scalars(
            select(Badge.name).join(UserBadge, UserBadge.badge_id == Badge.id)
            .where(UserBadge.user_id == user.id)
        )),
        "goals": _goal_progress(db, user.id),
        "passedLessons": list(db.scalars(
            select(QuizPass.lesson_index).where(QuizPass.user_id == user.id)
        )),
    }


@app.post("/api/auth/register", status_code=201)
def register_user(user_data: UserCreate, request: Request, response: Response, db: Session = Depends(get_db)):
    email = user_data.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=400, detail="Email already registered")

    new_user = User(
        email=email,
        password_hash=_hash_password(user_data.password),
        display_name=user_data.display_name.strip(),
        major=(user_data.major or "").strip() or None,
        anonymous=False,
    )
    db.add(new_user)
    try:
        db.commit()
    except IntegrityError:  # two simultaneous sign-ups with the same email
        db.rollback()
        raise HTTPException(status_code=400, detail="Email already registered")
    db.refresh(new_user)
    _start_session(request, response, db, new_user)
    return _user_profile(db, new_user)


@app.post("/api/auth/login")
def login_user(credentials: UserLogin, request: Request, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == credentials.email.lower()))
    if user is None or not _verify_password(credentials.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    _start_session(request, response, db, user)
    return _user_profile(db, user)


@app.exception_handler(OperationalError)
async def database_unavailable(_request, exc: OperationalError):
    from fastapi.responses import JSONResponse
    logger.error("Database error: %s", exc.orig)
    code = exc.orig.args[0] if exc.orig is not None and exc.orig.args else None
    if code in (1054, 1146):  # unknown column / table doesn't exist
        detail = "Database schema is out of date. Re-run schema.sql (see backend logs for the missing column/table)."
    else:
        detail = "Database unavailable. Is MySQL running and DATABASE_URL set in backend/.env?"
    return JSONResponse(status_code=503, content={"detail": detail})


def _mapped_sightings(db: Session) -> list[dict]:
    """The map only publishes approved database reports with valid GPS."""
    reports = db.scalars(select(Report).where(
        Report.review_status == "approved",
        Report.lat.between(-90, 90),
        Report.lng.between(-180, 180),
    ).order_by(Report.id))
    return [{
        "photo_id": report.photo_hash,
        "image_id": Path(report.stored_name).stem,
        "latitude": float(report.lat),
        "longitude": float(report.lng),
        "verified": True,
    } for report in reports]


@app.get("/api/sightings/summary")
def sighting_summary(db: Session = Depends(get_db)):
    return {
        "uploaded": db.scalar(select(func.count(Report.id))),
        "mapped": len(_mapped_sightings(db)),
        "detected": db.scalar(select(func.count(Report.id)).where(Report.review_status == "approved")),
    }


@app.get("/api/me/reports")
def report_history(offset: int = Query(0, ge=0), limit: int = Query(12, ge=1, le=50),
                   user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    total = db.scalar(select(func.count(Report.id)).where(Report.user_id == user.id))
    points = (select(PointEvent.report_id, func.sum(PointEvent.points).label("points"))
              .where(PointEvent.user_id == user.id).group_by(PointEvent.report_id).subquery())
    rows = db.execute(select(Report, func.coalesce(points.c.points, 0))
                      .outerjoin(points, points.c.report_id == Report.id)
                      .where(Report.user_id == user.id)
                      .order_by(Report.created_at.desc(), Report.id.desc())
                      .offset(offset).limit(limit + 1)).all()
    def timestamp(value):
        return value.replace(tzinfo=timezone.utc).isoformat() if value else None
    return {"reports": [{
        "id": report.id,
        "reportNumber": total - offset - index,
        "photoUrl": f"/api/me/reports/{report.id}/photo",
        "submittedAt": timestamp(report.created_at),
        "capturedAt": report.captured_at.isoformat() if report.captured_at else None,
        "status": report.review_status,
        "detectionStatus": report.detection_status,
        "lifeStage": report.life_stage_verified,
        "confidence": float(report.model_confidence) if report.model_confidence is not None else None,
        "latitude": float(report.lat) if report.lat is not None else None,
        "longitude": float(report.lng) if report.lng is not None else None,
        "points": int(awarded),
    } for index, (report, awarded) in enumerate(rows[:limit])],
        "nextOffset": offset + limit if len(rows) > limit else None}


@app.get("/api/me/reports/{report_id}/photo")
def report_history_photo(report_id: int, user: User = Depends(get_current_user),
                         db: Session = Depends(get_db)):
    report = db.scalar(select(Report).where(Report.id == report_id, Report.user_id == user.id))
    if report is None:
        raise HTTPException(status_code=404, detail="Photograph not found")
    return _photo_preview(report)


@app.get("/api/photos/{image_id}")
def sighting_photo(image_id: str, db: Session = Depends(get_db)):
    """Serve photos only while their approved database report exists."""
    if not re.fullmatch(r"[0-9a-f]{32}", image_id):
        raise HTTPException(status_code=404, detail="Photograph not found")
    report = db.scalar(select(Report).where(
        Report.review_status == "approved",
        Report.stored_name.like(image_id + ".%"),
    ))
    if report is None:
        raise HTTPException(status_code=404, detail="Photograph not found")
    return _photo_preview(report)


def _photo_preview(report: Report):
    path = UPLOAD_DIR / report.stored_name
    if not path.is_file() or path.parent.resolve() != UPLOAD_DIR.resolve():
        raise HTTPException(status_code=404, detail="Photograph not found")
    from PIL import ImageOps
    with Image.open(path) as source:
        preview = ImageOps.exif_transpose(source).convert("RGB")
        preview.thumbnail((900, 900))
        output = io.BytesIO()
        preview.save(output, format="JPEG", quality=85)
    return Response(content=output.getvalue(), media_type="image/jpeg")


@app.get("/api/map", response_class=HTMLResponse)
def sightings_map(db: Session = Depends(get_db)):
    """Render the original Folium/Leaflet map inside the React frontend."""
    mapped = _mapped_sightings(db)
    image_urls = {str(r["photo_id"]): f"/api/photos/{r['image_id']}" for r in mapped}
    rows = mapped
    if not rows:
        rows = [{"latitude": None, "longitude": None, "verified": None}]
    map_object = generate_map(rows, verified_only=True, image_urls=image_urls, allow_empty=True)
    return HTMLResponse(
        map_object.get_root().render(),
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


def _parse_timestamp(value: str | None) -> datetime | None:
    """ISO timestamp from metadata -> naive UTC datetime for a MySQL TIMESTAMP column."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed

def _normalize_stage(label: str | None) -> str:
    text = (label or "").lower()
    if "egg" in text:
        return "Egg mass"
    if "red" in text:
        return "Red nymph"
    if "nymph" in text or "black" in text:
        return "Black nymph"
    return "Adult"

BADGE_RULES = {  # badge name -> minimum verified reports
    "First Squash": 1, "Lanternfly Hunter": 10, "Pest Patrol": 25, "Campus Defender": 50,
}


def _award_badges(db: Session, user_id: int) -> None:
    """Give the user any badges they've newly earned. Call before db.commit()."""
    db.flush()  # make reports/quiz passes added in this session visible to the queries below
    approved = select(func.count(Report.id)).where(
        Report.user_id == user_id, Report.review_status == "approved"
    )
    total = db.scalar(approved)
    stages = set(db.scalars(
        select(Report.life_stage_verified).distinct().where(
            Report.user_id == user_id, Report.review_status == "approved"
        )
    ))
    quizzes = db.scalar(select(func.count()).select_from(QuizPass).where(QuizPass.user_id == user_id))

    earned = {name for name, needed in BADGE_RULES.items() if total >= needed}
    if "Egg mass" in stages:
        earned.add("Egg Hunter")
    if stages & {"Black nymph", "Red nymph"}:
        earned.add("Nymph Spotter")
    if {"Egg mass", "Black nymph", "Red nymph", "Adult"} <= stages:
        earned.add("Full Life Cycle")
    if quizzes >= LESSON_COUNT:
        earned.add("Field Expert")

    already = set(db.scalars(select(UserBadge.badge_id).where(UserBadge.user_id == user_id)))
    for badge in db.scalars(select(Badge).where(Badge.name.in_(earned))):
        if badge.id not in already:
            db.add(UserBadge(user_id=user_id, badge_id=badge.id))


def _save_report(record: dict, detection: dict, user_id: int | None, life_stage: str | None) -> dict:
    result = {"report_id": None, "review_status": "unavailable", "life_stage": None, "points_awarded": 0, "duplicate": False}
    detections = detection.get("detections") or []
    best = max(detections, key=lambda d: d.get("confidence", 0), default=None)
    confident = detection.get("status") == "detected" and best is not None
    if detection.get("status") == "unavailable":
        return result
    stage = _normalize_stage(best.get("label")) if best else None
    try:
        with SessionLocal() as db:
            existing = db.scalar(select(Report).where(Report.photo_hash == record["photo_id"]))
            if existing is not None and (existing.review_status != "pending" or existing.user_id != user_id):  # no extra points
                result.update(report_id=existing.id, review_status=existing.review_status,
                              life_stage=existing.life_stage_verified, duplicate=True)
                return result
            if user_id is not None and db.get(User, user_id) is None:
                user_id = None
            report_values = dict(
                user_id=user_id,
                photo_hash=record["photo_id"],
                stored_name=record["stored_name"],
                lat=record.get("latitude"),
                lng=record.get("longitude"),
                captured_at=_parse_timestamp(record.get("timestamp")),
                location_source=record.get("location_source"),
                life_stage_claimed=life_stage,
                life_stage_verified=stage if confident else None,
                detection_status=detection.get("status"),
                model_confidence=round(best["confidence"], 4) if best else None,
                bbox=[d.get("bbox_xyxy") for d in detections] or None,
                review_status="approved" if confident else "rejected",
            )
            # Re-uploading an older pending report resolves it automatically.
            if existing is not None:
                report = existing
                report_values["user_id"] = existing.user_id
                user_id = existing.user_id
                for key, value in report_values.items():
                    setattr(report, key, value)
            else:
                report = Report(**report_values)
                db.add(report)
            db.flush()  # gives report.id
            points = 0
            if confident and user_id is not None:
                points = STAGE_POINTS.get(stage, 10)
                if life_stage and life_stage.strip().lower() == stage.lower():
                    points += CORRECT_STAGE_BONUS
                db.add(PointEvent(user_id=user_id, report_id=report.id, points=points,
                                  reason=f"Verified report: {stage}"))
                _award_badges(db, user_id)
            db.commit()
            result.update(report_id=report.id, review_status=report.review_status,
                          life_stage=stage if confident else None, points_awarded=points)
            return result
    except IntegrityError:
        # A simultaneous upload may have committed the same unique photo hash.
        with SessionLocal() as db:
            existing = db.scalar(select(Report).where(Report.photo_hash == record["photo_id"]))
            if existing is not None:
                result.update(report_id=existing.id, review_status=existing.review_status,
                              life_stage=existing.life_stage_verified, duplicate=True)
                return result
        logger.exception("Could not save report due to a database constraint")
        return result
    except SQLAlchemyError:
        logger.exception("Could not save report to MySQL; no points awarded or map publication")
        return result


def _profile_by_id(user_id: int | None) -> dict | None:
    if user_id is None:
        return None
    try:
        with SessionLocal() as db:
            user = db.get(User, user_id)
            return _user_profile(db, user) if user else None
    except SQLAlchemyError:
        return None

@app.post("/api/sightings", status_code=201)
async def upload_sighting(
    photo: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    life_stage: str | None = Form(None, max_length=50),
):
    """Validate and store photo; return EXIF metadata and YOLO detections.

    Only approved reports earn points and appear on the database-backed map.
    """
    user_id = current_user.id
    extension = Path(photo.filename or "").suffix.lower()
    if extension not in {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".mpo"}:
        raise HTTPException(status_code=400, detail="Use a JPG, PNG, WebP, HEIC, or MPO photo.")

    destination = None
    try:
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        # Always generate our own filename; never use user-supplied paths.
        destination = UPLOAD_DIR / f"{uuid4().hex}{extension}"
        size = 0
        digest = hashlib.sha256()
        with destination.open("xb") as handle:
            while chunk := await photo.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="Photo exceeds 15 MB limit.")
                handle.write(chunk)
                digest.update(chunk)
        if size == 0:
            raise HTTPException(status_code=400, detail="The uploaded file is empty.")

        try:
            with Image.open(destination) as img:
                image_format = img.format
                img.verify()
            if image_format not in ALLOWED_FORMATS:
                raise ValueError("Unsupported image format")
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="Invalid or unsupported image file.") from exc

        raw_metadata = extract_metadata(destination)
        # Preserve the user's original filename only in the response metadata.
        raw_metadata["file_name"] = Path(photo.filename or "photo").name
        metadata = process_metadata(raw_metadata, photo_id=digest.hexdigest())
        # Model inference is CPU-intensive and must not block FastAPI's event loop.
        # Preserve the upload and metadata even if the optional model fails.
        try:
            detection = await run_in_threadpool(detect_lanternflies, destination)
        except Exception:
            logger.exception("Lanternfly model inference failed")
            detection = {
                "status": "unavailable", "model": "my_model.pt",
                "detections": [], "detection_count": 0,
                "message": "Detection model is unavailable; see backend logs.",
            }
        # Persist once in MySQL; the map and points use the same report status.
        stored_record = {
            **metadata,
            "image_id": destination.stem,
            "stored_name": destination.name,
            "detection_status": detection["status"],
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
        }
        saved = await run_in_threadpool(_save_report, stored_record, detection, user_id, life_stage)
        if saved["duplicate"]:
            destination.unlink(missing_ok=True)  # keep the original stored photo
        verification_status = saved["review_status"] if saved["review_status"] != "pending" else "unavailable"
        messages = {
            "approved": "Automatically approved.",
            "rejected": "No lanternfly detected. Try another photo.",
            "unavailable": "Could not complete identification or save the report. Please retry.",
        }
        return {
            "message": "This photo has already been submitted; no additional points awarded." if saved["duplicate"] else messages[verification_status],
            "duplicate": saved["duplicate"],
            "report_id": saved["report_id"],
            "photo_id": digest.hexdigest(),
            "metadata": metadata,
            "detection": detection,
            "verification_status": verification_status,
            "life_stage": saved["life_stage"],
            "points_awarded": saved["points_awarded"],
            "user": await run_in_threadpool(_profile_by_id, user_id),
        }
    except HTTPException:
        if destination is not None:
            destination.unlink(missing_ok=True)
        raise
    except (OSError, ValueError, UnidentifiedImageError) as exc:
        if destination is not None:
            destination.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Could not process image.") from exc
    finally:
        await photo.close()

class FriendRequestCreate(BaseModel):
    email: EmailStr


class FriendRequestResponse(BaseModel):
    action: Literal["accept", "decline"]


@app.get("/api/me/friend-requests")
def friend_requests(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    incoming = db.execute(select(Friendship, User).join(User, User.id == Friendship.requester_id).where(
        Friendship.addressee_id == user.id, Friendship.status == "pending"
    ).order_by(User.display_name, User.id)).all()
    return [{"requesterId": sender.id, "name": sender.display_name} for _, sender in incoming]


@app.post("/api/me/friend-requests", status_code=201)
def send_friend_request(data: FriendRequestCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    recipient = db.scalar(select(User).where(User.email == data.email.lower()))
    if recipient is None:
        raise HTTPException(status_code=404, detail="No account found with that email address")
    if recipient.id == user.id:
        raise HTTPException(status_code=400, detail="You cannot add yourself as a friend")
    # Serialize both directions of a pair so simultaneous sends cannot create two requests.
    db.execute(select(User.id).where(User.id.in_([user.id, recipient.id])).order_by(User.id).with_for_update()).all()
    existing = db.scalar(select(Friendship).where(
        ((Friendship.requester_id == user.id) & (Friendship.addressee_id == recipient.id)) |
        ((Friendship.requester_id == recipient.id) & (Friendship.addressee_id == user.id))
    ).with_for_update())
    if existing is not None:
        if existing.status == "accepted":
            raise HTTPException(status_code=409, detail="You are already friends")
        if existing.status == "pending":
            detail = ("Friend request already sent" if existing.requester_id == user.id
                      else "This person has already sent you a request. Accept it below.")
            raise HTTPException(status_code=409, detail=detail)
        db.delete(existing)
        db.flush()
    db.add(Friendship(requester_id=user.id, addressee_id=recipient.id, status="pending"))
    db.commit()
    return {"message": "Friend request sent"}


@app.patch("/api/me/friend-requests/{requester_id}")
def respond_friend_request(requester_id: int, data: FriendRequestResponse,
                           user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    friendship = db.scalar(select(Friendship).where(
        Friendship.requester_id == requester_id, Friendship.addressee_id == user.id
    ).with_for_update())
    if friendship is None:
        raise HTTPException(status_code=404, detail="Friend request not found")
    status = "accepted" if data.action == "accept" else "declined"
    if friendship.status != "pending" and friendship.status != status:
        raise HTTPException(status_code=409, detail="This request has already been answered")
    friendship.status = status
    db.commit()
    return {"message": "Friend request accepted" if status == "accepted" else "Friend request declined"}


@app.get("/api/leaderboard")
def leaderboard(
    segment: Literal["Friends", "Teams", "Majors", "Campus"] = "Campus",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _leaderboard(current_user, segment, db)


def _leaderboard(current: User, segment: str, db: Session):
    totals = (select(PointEvent.user_id, func.sum(PointEvent.points).label("points"))
              .group_by(PointEvent.user_id).subquery())
    users = db.execute(
        select(User, func.coalesce(totals.c.points, 0))
        .outerjoin(totals, totals.c.user_id == User.id)
    ).all()
    sightings = dict(db.execute(
        select(Report.user_id, func.count(Report.id))
        .where(Report.review_status == "approved", Report.user_id.is_not(None))
        .group_by(Report.user_id)
    ).all())
    entries = []
    if segment == "Teams":
        memberships = db.execute(select(TeamMember.team_id, TeamMember.user_id)).all()
        points = {user.id: int(total) for user, total in users}
        for team in db.scalars(select(Team)):
            members = {uid for tid, uid in memberships if tid == team.id}
            entries.append({"id": team.id, "name": team.name,
                            "points": sum(points.get(uid, 0) for uid in members),
                            "sightings": sum(sightings.get(uid, 0) for uid in members),
                            "isCurrentUser": current.id in members})
    elif segment == "Majors":
        majors = {}
        for user, total in users:
            major = (user.major or "").strip()
            if not major:
                continue
            entry = majors.setdefault(major, {"id": major, "name": major,
                                              "points": 0, "sightings": 0, "isCurrentUser": False})
            entry["points"] += int(total)
            entry["sightings"] += sightings.get(user.id, 0)
            entry["isCurrentUser"] |= user.id == current.id
        entries = list(majors.values())
    else:
        visible = {current.id}
        if segment == "Friends":
            for friendship in db.scalars(select(Friendship).where(Friendship.status == "accepted")):
                if friendship.requester_id == current.id:
                    visible.add(friendship.addressee_id)
                if friendship.addressee_id == current.id:
                    visible.add(friendship.requester_id)
        for user, total in users:
            if segment == "Friends" and user.id not in visible:
                continue
            entries.append({"id": user.id,
                            "name": "Anonymous Hokie" if user.anonymous else user.display_name,
                            "points": int(total), "sightings": sightings.get(user.id, 0),
                            "major": user.major, "isCurrentUser": user.id == current.id})
    entries.sort(key=lambda entry: (-entry["points"], entry["name"].casefold(), entry["id"]))
    if segment in {"Friends", "Campus"}:
        streaks = _upload_streaks(db, [entry["id"] for entry in entries])
        for entry in entries:
            entry["streak"] = streaks[entry["id"]]
    previous_points = None
    rank = 0
    for index, entry in enumerate(entries, 1):
        if entry["points"] != previous_points:
            rank = index
        entry["rank"] = rank
        previous_points = entry["points"]
    return entries


TEAM_GOAL_TARGET = 20
@app.get("/api/team-goal")
def team_goal(db: Session = Depends(get_db)):
    found = db.scalar(
        select(func.count(Report.id)).where(
            Report.review_status == "approved",
            Report.life_stage_verified == "Adult",
            )
    )
    return {
        "title": f"{TEAM_GOAL_TARGET} Adult lanternflies before December",
        "target": TEAM_GOAL_TARGET,
        "found": found,
    }

def _get_user_or_404(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@app.get("/api/users/{user_id}")
def get_user(user_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only access your own profile")
    return _user_profile(db, current_user)


@app.post("/api/me/lessons/{lesson_index}/pass")
def pass_lesson(lesson_index: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user_id = user.id
    if not 0 <= lesson_index < LESSON_COUNT:
        raise HTTPException(status_code=400, detail="Unknown lesson")
    if db.get(QuizPass, (user_id, lesson_index)) is None:  # points only once
        db.add(QuizPass(user_id=user_id, lesson_index=lesson_index))
        db.add(PointEvent(user_id=user_id, lesson_id=lesson_index, points=QUIZ_POINTS,
                          reason=f"Passed lesson {lesson_index + 1}"))
        _award_badges(db, user_id)
        db.commit()
    return _user_profile(db, user)


class SettingsUpdate(BaseModel):
    anonymous: bool | None = None
    shareWithResearchers: bool | None = None


@app.patch("/api/me/settings")
def update_settings(settings: SettingsUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if settings.anonymous is not None:
        user.anonymous = settings.anonymous
    if settings.shareWithResearchers is not None:
        user.share_with_researchers = settings.shareWithResearchers
    db.commit()
    return _user_profile(db, user)


from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

DIST_DIR = BASE_DIR.parent / "frontend" / "dist"

if DIST_DIR.exists():
    app.mount("/assets", StaticFiles(directory=DIST_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_frontend(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404)
        file = DIST_DIR / full_path
        return FileResponse(file if file.is_file() else DIST_DIR / "index.html")
