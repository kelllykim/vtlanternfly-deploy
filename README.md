# VT Lanternfly

Mobile-oriented React/TypeScript website with a FastAPI backend and MySQL database.
Users can register, identify lanternflies from photos, earn points, view mapped
sightings, complete learning quizzes, and send friend requests.

## Current features

- Email/password accounts with hashed passwords and seven-day server-validated sessions.
- Photo uploads with EXIF metadata extraction and automatic YOLO identification.
- Approved sightings earn points; rejected photos and model failures do not.
- MySQL-backed map showing only approved reports with valid GPS coordinates.
- Friends, Teams, Majors, and Campus rankings with points and approved sighting counts.
- Friend requests by registered email, with recipient acceptance or decline.
- Profile contributions, badges, quiz progress, and goal bonuses.
- Searchable registration choices from Virginia Tech’s official program list.

## Local configuration

Install Node.js and Python 3.12, and start a MySQL database. Create a database and
an account with permission to use it, or get connection details from your teammate.

Create `backend/.env` locally:

```dotenv
DATABASE_URL=mysql+pymysql://USERNAME:PASSWORD@localhost:3306/vtlanternfly_db
LANTERNFLY_CONFIDENCE_THRESHOLD=0.15
```

Replace the placeholders with your MySQL connection details. URL-encode special
characters in the username/password. Keep `.env` out of Git; it is already ignored.
Environment variables set by the host or shell take precedence over this file.
Leave `SESSION_COOKIE_SECURE` unset for local HTTP development.

## Database setup

The SQL files describe the database structure and starting data. Pushing them to
GitHub does not execute them against MySQL.

For a new database, run these commands from the project root, substituting your
host, port, username, and database name:

```bash
mysql -h HOST -P PORT -u USERNAME -p DATABASE_NAME < server/src/main/resources/schema.sql
mysql -h HOST -P PORT -u USERNAME -p DATABASE_NAME < server/src/main/resources/data.sql
```

`data.sql` includes the lesson IDs and badge catalog used by the application.

For an existing shared database, coordinate schema changes with its owner and
back it up before applying them. `schema.sql` creates missing tables, including
`user_sessions`, `friendships`, `teams`, `team_members`, and `goal_rewards`.
Its `CREATE TABLE IF NOT EXISTS` statements do not add columns to existing tables.
After installing backend dependencies, apply the additive goal migration with
`DATABASE_URL` pointing to the intended database:

```bash
backend/.venv/bin/python backend/migrate_goal_rewards.py
```

The migration creates `goal_rewards` and adds `users.invited_by` if missing.
It does not initialize all application tables or repair every older schema.
Older databases must also match the report columns in `schema.sql`, including
`reports.is_simulated`. The ORM mappings are in `backend/db_models.py`.

## Start locally

Backend, terminal 1:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
uvicorn main:app --reload
```

Frontend, terminal 2:

```bash
cd frontend
npm ci
npm run dev
```

Open http://localhost:8443/. Vite forwards `/api` requests to FastAPI on port 8000.
Keep both processes running. Backend health: http://127.0.0.1:8000/api/health.
Interactive API documentation: http://127.0.0.1:8000/docs.

## Identification, uploads, and map behavior

Uploads accept JPEG, PNG, WebP, HEIC/HEIF, and MPO photos up to 15 MB. The backend
uses `backend/models/my_model.pt` with Ultralytics YOLO, CPU inference, and a
1024-pixel inference size. Only use trusted checkpoint files.

`LANTERNFLY_CONFIDENCE_THRESHOLD` controls which detections are accepted. The code
default is 0.25; set it to 0.15 to match the current local configuration. Values
must be greater than 0 and at most 1. Lower thresholds accept more predictions
and may produce more false positives; scores are not guaranteed probabilities.
Restart the backend after changing configuration.

Accepted detections are automatically approved. There is no manual review queue.
Approval is an AI decision, not an independent expert verification.
Duplicate photos retain their original report and account, award no additional
points, and show an explicit already-submitted message across accounts.

Photos are stored in `backend/uploads/`; report records and points are stored in
MySQL. The map reads approved reports directly from MySQL. Rejected and unavailable
identifications cannot appear as pins. Approved photos without GPS can earn points
but do not appear on the map. The result screen explains how to enable camera
location permissions and photo location tags for future photos; changing permissions
does not add coordinates to an existing image.

Deleting a report removes its pin and photo-preview access on refresh. A database
cleanup must also remove its associated `point_events` to reset awarded points.
The old `backend/sightings.jsonl` index is no longer used by the API. Internet
access is required for map assets and tiles.

## Accounts, friends, and goals

Login and registration issue an HttpOnly, SameSite=Lax session cookie. MySQL stores
only a SHA-256 hash of the random token. Logout revokes the session; expired sessions
require login again. Uploads, settings, lesson rewards, and personalized rankings
use the server-validated account rather than browser-supplied user IDs.

On the leaderboard, **Add friend** sends a request to an existing account by email.
Recipients see **Friend requests** on that page and can accept or decline. Requests
refresh every 15 seconds while the page is open and when the window regains focus.
Acceptance adds both accounts to each other’s Friends rankings. No email is sent.
**Invite friends** and **Create team** remain placeholders; existing database team
memberships are reflected in the Teams rankings.

Report points are 10 for adults/nymphs and 15 for egg masses. Passed quizzes award
10 points once per lesson. Each completed profile goal awards an additional 10 points:

- Three approved reports: once per week, Monday–Sunday UTC.
- First approved egg-mass report: once per account.
- First passed quiz: once per account.
- First recruited account: once per account, based on `users.invited_by`.

Goal rewards are recorded uniquely to prevent repeat awards. Opening the profile
also awards eligible bonuses for existing activity. Adding an existing friend does
not recruit a new account; the recruitment interface is not implemented yet.

The official major catalog is versioned in `backend/data/vt_majors.json`, sourced
from https://www.vt.edu/academics/majors.html. `/api/majors` supplies the searchable
selector and the backend validates the same choices. Major is optional; existing
account values are not automatically renamed. Update the catalog when VT changes
its programs.

## Build and deployment

Build and check the frontend from the project root:

```bash
npm run build --prefix frontend
frontend/node_modules/.bin/tsc --noEmit -p frontend/tsconfig.json
```

The root `Dockerfile` builds the React frontend and runs FastAPI, which serves
`frontend/dist` and the API together. It listens on the host’s `PORT`, defaulting
to 8000. The database schema is not applied automatically during build or startup.

Set these variables in the hosting service, independently of GitHub:

```dotenv
DATABASE_URL=mysql+pymysql://USERNAME:PASSWORD@HOST:PORT/DATABASE_NAME
LANTERNFLY_CONFIDENCE_THRESHOLD=0.15
SESSION_COOKIE_SECURE=true
```

Use `SESSION_COOKIE_SECURE=true` for the HTTPS deployment, particularly when TLS
terminates at a reverse proxy. Cookies also become Secure automatically when the
backend recognizes an HTTPS request. A missing threshold setting uses 0.25.

Mount persistent storage for `backend/uploads/`, or set `LANTERNFLY_UPLOAD_DIR`
to a persistent directory. MySQL contains filenames, not image bytes. Without
persistent storage, photo previews may be lost on redeployment even when report
records remain. A shared database does not synchronize photos between computers.

Commit the source, including `backend/data/` and new components. Keep `.env`,
credentials, uploads, virtual environments, `node_modules`, and generated builds
out of Git. Existing users must log in again when moving from the old browser-ID
login implementation to server sessions.

## Standalone scripts

`metadata_extractor.py`, `metadata_processor.py`, `map_visualization.py`, and
`run_pipeline.py` remain available in `backend/`. For standalone pipeline usage,
run `python run_pipeline.py --help` from that directory. FastAPI calls the needed
functions directly rather than invoking the entire standalone pipeline.
