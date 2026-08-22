# CoHeart API

Standalone FastAPI backend for the CoHeart Academy platform.

## Overview

This module exposes the application APIs that power the CoHeart Academy web app, including:

- Authentication and user sessions
- Course catalog and enrollment
- Lesson and quiz management
- Progress tracking and certificate generation
- Admin controls for roles, documents, MIS trackers, notifications, and audit logs
- PostgreSQL-backed data storage

## Tech stack

- Python 3.10+
- FastAPI
- Pydantic v2
- PostgreSQL via SQLAlchemy and psycopg
- FPDF for certificate PDFs

## Quick start

```powershell
cd <project-folder>
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The app will be available at:

- http://localhost:8000
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Default admin account

The API initializes a default admin user on first run. Replace these values before deployment:

- Username: admin
- Email: admin@example.com
- Password: change-me-strong-password

## Data persistence

Application state is stored in PostgreSQL. Set `DATABASE_URL` before starting
the API, for example:

```powershell
$env:DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/coheart"
```

Create the database before starting the API:

```sql
CREATE DATABASE coheart;
```

The API creates its `app_state` table automatically on startup. Existing
`coheart_data.json` data is imported automatically the first time the database
does not contain application state. The JSON file is no longer written after
the import.

The PostgreSQL state includes:

- users
- sessions
- progress
- courses
- lessons
- quizzes
- audit_logs
- roles
- user_roles
- mis_trackers
- mis_data
- documents
- notifications

Uploaded document files remain in the local `data/docs` directory; PostgreSQL
stores their metadata. Use shared object storage for files when deploying more
than one API instance.

## API summary

### Authentication

- POST /auth/register
- POST /auth/login
- GET /auth/me
- POST /auth/logout

Request/response examples:

```json
POST /auth/login
{
  "email": "admin@example.com",
  "password": "change-me-strong-password"
}
```

```json
{
  "access_token": "<token>",
  "token_type": "bearer"
}
```

Use the returned token in the Authorization header:

```http
Authorization: Bearer <token>
```

### Courses and learning

- GET /courses
- GET /courses/{course_id}
- GET /courses/{course_id}/lessons
- GET /courses/{course_id}/quiz
- POST /courses/{course_id}/enroll
- POST /courses/{course_id}/quiz/submit
- GET /progress
- GET /certificates/{course_id}

### Documents

- GET /documents
- GET /documents/{doc_id}/versions
- GET /documents/{doc_id}/download/{version}

Admin-only:

- GET /admin/documents
- POST /admin/documents
- POST /admin/documents/{doc_id}/upload
- DELETE /admin/documents/{doc_id}

### Notifications

- GET /notifications
- POST /notifications/{notification_id}/read

Admin-only:

- POST /admin/notifications

### MIS trackers

- GET /admin/mis/trackers
- POST /admin/mis/trackers
- POST /mis/{tracker_id}/submit
- GET /admin/mis/{tracker_id}/report

### Roles and permissions

- GET /admin/roles
- POST /admin/roles
- PUT /admin/roles/{role_name}
- DELETE /admin/roles/{role_name}
- POST /admin/users/{user_id}/roles
- DELETE /admin/users/{user_id}/roles/{role_name}

### Admin course management

- GET /admin/courses
- POST /admin/courses
- PUT /admin/courses/{course_id}
- DELETE /admin/courses/{course_id}
- GET /admin/courses/{course_id}/lessons
- POST /admin/courses/{course_id}/lessons
- PUT /admin/courses/{course_id}/lessons/{lesson_id}
- DELETE /admin/courses/{course_id}/lessons/{lesson_id}
- GET /admin/courses/{course_id}/quizzes
- POST /admin/courses/{course_id}/quizzes
- PUT /admin/courses/{course_id}/quizzes/{quiz_id}
- DELETE /admin/courses/{course_id}/quizzes/{quiz_id}

### Audit

- GET /admin/audit

### Users

- GET /admin/users
- PUT /users/me
- DELETE /users/me

## Notes

- CORS is enabled for the frontend origin: http://localhost:5173
- The backend expects the frontend to send bearer tokens for authenticated routes
- File uploads are stored in the local data/documents structure under the repository
- All admin endpoints require admin privileges via the token-based auth flow

## Development tips

```powershell
# run the app
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# open API docs
Start-Process http://localhost:8000/docs
```

## Production note

This repository is intentionally a backend module and is designed to be consumed by a separate frontend or client application. For production, replace the default admin account, set a strong PostgreSQL password, and secure the environment, session handling, and SMTP settings before deployment. The current adapter preserves the existing API contracts in a single PostgreSQL JSONB row; it can be normalized into relational tables as the domain grows.
