"""VT-Lanternfly development API: upload, EXIF extraction, and YOLO inference.

Accounts (register/login) use MySQL via SQLAlchemy; sightings still use local JSONL.
"""
import hashlib
import io
import re
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, Response
import logging

from services.image_verifier import detect_lanternflies

logger = logging.getLogger(__name__)
from PIL import Image, UnidentifiedImageError

from metadata_extractor import extract_metadata
from metadata_processor import process_metadata
from sighting_store import append_sighting, read_sightings
from map_visualization import generate_map

# User accounts (MySQL via SQLAlchemy)
import bcrypt
from fastapi import Depends
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session

from database import SessionLocal, get_db
from db_models import Badge, PointEvent, QuizPass, Report, User, UserBadge


BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = Path(os.environ.get("LANTERNFLY_UPLOAD_DIR", BASE_DIR / "uploads"))
SIGHTINGS_FILE = UPLOAD_DIR.parent / "sightings.jsonl"
MAX_UPLOAD_BYTES = 15 * 1024 * 1024
AUTO_APPROVE_CONFIDENCE = 0.5   # model confidence needed to approve automatically
STAGE_POINTS = {"Adult": 10, "Black nymph": 10, "Red nymph": 10, "Egg mass": 15}
CORRECT_STAGE_BONUS = 5
QUIZ_POINTS = 10
LESSON_COUNT = 3

ALLOWED_FORMATS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp", "HEIF": ".heif", "HEIC": ".heic", "MPO": ".jpg"}

app = FastAPI(title="VT-Lanternfly API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8443", "http://127.0.0.1:8443", "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Content-Type"],
)


@app.get("/api/health")
def health():
    return {"status": "ok"}


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)  # bcrypt limit is 72 bytes
    display_name: str = Field(min_length=1, max_length=100)
    major: str | None = Field(default=None, max_length=100)


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
        "streak": 0,  # still need to implement
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
        "passedLessons": list(db.scalars(
            select(QuizPass.lesson_index).where(QuizPass.user_id == user.id)
        )),
    }


@app.post("/api/auth/register", status_code=201)
def register_user(user_data: UserCreate, db: Session = Depends(get_db)):
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
    return _user_profile(db, new_user)


@app.post("/api/auth/login")
def login_user(credentials: UserLogin, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == credentials.email.lower()))
    if user is None or not _verify_password(credentials.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
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


def _mapped_sightings() -> list[dict]:
    """Only AI-detected sightings with actual coordinates appear on the prototype map."""
    return [
        record for record in read_sightings(SIGHTINGS_FILE)
        if record.get("detection_status") == "detected"
        and record.get("latitude") is not None
        and record.get("longitude") is not None
    ]


@app.get("/api/sightings/summary")
def sighting_summary():
    records = read_sightings(SIGHTINGS_FILE)
    return {
        "uploaded": len(records),
        "mapped": len(_mapped_sightings()),
        "detected": sum(record.get("detection_status") == "detected" for record in records),
    }


@app.get("/api/photos/{image_id}")
def sighting_photo(image_id: str):
    """Serve a browser-compatible preview of a locally indexed uploaded photograph."""
    if not re.fullmatch(r"[0-9a-f]{32}", image_id):
        raise HTTPException(status_code=404, detail="Photograph not found")
    record = next((item for item in read_sightings(SIGHTINGS_FILE) if item.get("image_id") == image_id), None)
    if record is None:
        raise HTTPException(status_code=404, detail="Photograph not found")
    path = UPLOAD_DIR / record["stored_name"]
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
def sightings_map():
    """Render the original Folium/Leaflet map inside the React frontend."""
    mapped = _mapped_sightings()
    image_urls = {str(r["photo_id"]): f"/api/photos/{r['image_id']}" for r in mapped}
    rows = [
        {**record, "verified": None}
        for record in mapped
    ]
    if not rows:
        rows = [{"latitude": None, "longitude": None, "verified": None}]
    map_object = generate_map(rows, image_urls=image_urls, allow_empty=True)
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
    result = {"report_id": None, "review_status": "pending", "life_stage": None, "points_awarded": 0}
    detections = detection.get("detections") or []
    best = max(detections, key=lambda d: d.get("confidence", 0), default=None)
    confident = (detection.get("status") == "detected" and best is not None
                 and best.get("confidence", 0) >= AUTO_APPROVE_CONFIDENCE)
    stage = _normalize_stage(best.get("label")) if best else None
    try:
        with SessionLocal() as db:
            existing = db.scalar(select(Report).where(Report.photo_hash == record["photo_id"]))
            if existing is not None:  # same photo again: no extra points
                result.update(report_id=existing.id, review_status=existing.review_status,
                              life_stage=existing.life_stage_verified)
                return result
            if user_id is not None and db.get(User, user_id) is None:
                user_id = None
            report = Report(
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
                review_status="approved" if confident else "pending",
            )
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
    except SQLAlchemyError:
        logger.exception("Could not save report to MySQL; kept in sightings.jsonl only")
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
    user_id: int | None = Form(None),
    life_stage: str | None = Form(None, max_length=50),
):
    """Validate and store photo; return EXIF metadata and YOLO detections.

    Stored files are private and not yet associated with a user or database.
    """
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
        # A temporary JSONL index lets the live map survive server restarts.
        # This is not a user-account database and does not imply AI approval.
        stored_record = {
            **metadata,
            "image_id": destination.stem,
            "stored_name": destination.name,
            "detection_status": detection["status"],
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            await run_in_threadpool(append_sighting, SIGHTINGS_FILE, stored_record)
        except OSError:
            logger.exception("Failed to persist local sighting index")
            raise HTTPException(status_code=500, detail="Could not save sighting locally.")
        saved = await run_in_threadpool(_save_report, stored_record, detection, user_id, life_stage)
        approved = saved["review_status"] == "approved"
        return {
            "message": "Verified; points awarded." if approved else "Saved to the review queue.",
            "report_id": saved["report_id"],
            "photo_id": digest.hexdigest(),
            "metadata": metadata,
            "detection": detection,
            "verification_status": "approved" if approved else "pending_review",
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
def get_user(user_id: int, db: Session = Depends(get_db)):
    return _user_profile(db, _get_user_or_404(db, user_id))


@app.post("/api/users/{user_id}/lessons/{lesson_index}/pass")
def pass_lesson(user_id: int, lesson_index: int, db: Session = Depends(get_db)):
    user = _get_user_or_404(db, user_id)
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


@app.patch("/api/users/{user_id}/settings")
def update_settings(user_id: int, settings: SettingsUpdate, db: Session = Depends(get_db)):
    user = _get_user_or_404(db, user_id)
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