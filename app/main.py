from io import BytesIO
from typing import Dict, List, Optional
from pathlib import Path
from uuid import uuid4
import os
import hashlib
import binascii
from datetime import datetime, timedelta

from fastapi import Depends, FastAPI, Header, HTTPException, Response
from fastapi import UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fpdf import FPDF
from pydantic import BaseModel, EmailStr, Field
from . import audit
from . import roles as roles_module
from . import mis as mis_module
from . import docs as docs_module
from . import notifications as notifications_module
from .database import initialize_database, load_legacy_state, load_state, save_state

app = FastAPI(title="CoHeart Academy API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class User(BaseModel):
    id: str
    username: str
    email: EmailStr
    password: str
    is_admin: bool = False
    is_active: bool = True


class UserCreate(BaseModel):
    username: str = Field(min_length=3)
    email: EmailStr
    password: str = Field(min_length=6)


class LoginRequest(BaseModel):
    username: Optional[str] = None
    email: Optional[EmailStr] = None
    password: str = Field(min_length=6)


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CourseBase(BaseModel):
    title: str
    description: str
    duration: str


class Course(CourseBase):
    id: str
    students: int


class Lesson(BaseModel):
    id: str
    title: str
    content: str


class QuizQuestion(BaseModel):
    id: str
    question: str
    options: List[str]
    answer: Optional[str] = None


class LessonCreate(BaseModel):
    title: str
    content: str


class QuizQuestionCreate(BaseModel):
    question: str
    options: List[str]
    answer: Optional[str] = None


class UserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[EmailStr] = None
    password: Optional[str] = Field(default=None, min_length=6)


class QuizSubmitItem(BaseModel):
    question_id: str
    answer: str


class QuizSubmitRequest(BaseModel):
    answers: List[QuizSubmitItem]


class ProgressItem(BaseModel):
    course_id: str
    enrolled: bool
    completed: bool
    score: Optional[int] = None
    certificate_ready: bool = False


users: Dict[str, User] = {}
sessions: Dict[str, str] = {}
progress: Dict[str, Dict[str, ProgressItem]] = {}

courses: Dict[str, Course] = {}
lessons: Dict[str, List[Lesson]] = {}
quizzes: Dict[str, List[QuizQuestion]] = {}

DATA_FILE = Path(__file__).resolve().parent.parent / "coheart_data.json"


def save_data() -> None:
    payload = {
        "users": {k: v.model_dump() for k, v in users.items()},
        "sessions": sessions,
        "progress": {uid: {cid: p.model_dump() for cid, p in items.items()} for uid, items in progress.items()},
        "courses": {k: v.model_dump() for k, v in courses.items()},
        "lessons": {k: [l.model_dump() for l in lst] for k, lst in lessons.items()},
        "quizzes": {k: [q.model_dump() for q in lst] for k, lst in quizzes.items()},
        "audit_logs": audit.audit_logs,
        "roles": roles_module.roles,
        "user_roles": roles_module.user_roles,
        "mis_trackers": mis_module.trackers,
        "mis_data": mis_module.mis_data,
        "documents": docs_module.documents,
        "notifications": notifications_module.notifications,
    }
    save_state(payload)


def load_data() -> None:
    obj = load_state()
    if obj is None:
        obj = load_legacy_state(DATA_FILE)
    if obj is None:
        return

    users.clear()
    for k, v in obj.get("users", {}).items():
        users[k] = User(**v)

    sessions.clear()
    sessions.update(obj.get("sessions", {}))

    progress.clear()
    for uid, items in obj.get("progress", {}).items():
        progress[uid] = {cid: ProgressItem(**p) for cid, p in items.items()}

    courses.clear()
    for k, v in obj.get("courses", {}).items():
        courses[k] = Course(**v)

    lessons.clear()
    for k, lst in obj.get("lessons", {}).items():
        lessons[k] = [Lesson(**l) for l in lst]

    quizzes.clear()
    for k, lst in obj.get("quizzes", {}).items():
        quizzes[k] = [QuizQuestion(**q) for q in lst]

    audit.audit_logs.clear()
    for e in obj.get("audit_logs", []):
        audit.audit_logs.append(e)

    roles_module.roles.clear()
    roles_module.roles.update(obj.get("roles", {}) or {})
    roles_module.user_roles.clear()
    roles_module.user_roles.update(obj.get("user_roles", {}) or {})

    mis_module.trackers.clear()
    mis_module.trackers.update(obj.get("mis_trackers", {}) or {})
    mis_module.mis_data.clear()
    mis_module.mis_data.update(obj.get("mis_data", {}) or {})

    docs_module.documents.clear()
    docs_module.documents.update(obj.get("documents", {}) or {})
    notifications_module.notifications.clear()
    notifications_module.notifications.extend(obj.get("notifications", []) or [])


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100_000)
    return binascii.hexlify(salt).decode() + '$' + binascii.hexlify(dk).decode()


def verify_password(stored: str, provided: str) -> bool:
    try:
        salt_hex, dk_hex = stored.split('$', 1)
        salt = binascii.unhexlify(salt_hex)
        dk = binascii.unhexlify(dk_hex)
        new_dk = hashlib.pbkdf2_hmac('sha256', provided.encode(), salt, 100_000)
        return binascii.hexlify(new_dk) == binascii.hexlify(dk)
    except Exception:
        return False


def initialize_data() -> None:
    global users, courses, lessons, quizzes

    if users:
        return

    admin = User(
        id="admin-user",
        username="admin",
        email="admin@example.com",
        password="change-me-strong-password",
        is_admin=True,
    )
    users[admin.id] = admin

    default_courses = [
        Course(
            id="skill-ed",
            title="SkillEd Essentials",
            description="Practical digital and vocational skills training for employability.",
            duration="6 weeks",
            students=138,
        ),
        Course(
            id="spectrum-inclusion",
            title="Spectrum Inclusion Support",
            description="Training educators and caregivers to build inclusive learning environments.",
            duration="4 weeks",
            students=94,
        ),
        Course(
            id="coheart-academy",
            title="CoHeart Academy Fundamentals",
            description="Core learning pathways for career readiness, life skills, and community impact.",
            duration="8 weeks",
            students=212,
        ),
    ]

    for course in default_courses:
        courses[course.id] = course

    lessons["skill-ed"] = [
        Lesson(id="s1", title="Digital Basics", content="Learn the foundations of digital tools and workplace communication."),
        Lesson(id="s2", title="Career Readiness", content="Build a resume, practice interview skills, and develop professionalism."),
    ]
    lessons["spectrum-inclusion"] = [
        Lesson(id="s3", title="Understanding Inclusion", content="Explore inclusive classrooms, learner strengths, and adaptive support."),
        Lesson(id="s4", title="Support Strategies", content="Learn techniques for collaboration, classroom support, and positive behavior."),
    ]
    lessons["coheart-academy"] = [
        Lesson(id="s5", title="Growth Mindset", content="Build confidence for learning, career pathways, and community leadership."),
        Lesson(id="s6", title="Community Projects", content="Create impactful projects that support local wellbeing and opportunity."),
    ]

    quizzes["skill-ed"] = [
        QuizQuestion(
            id="q1",
            question="What is one key skill employers look for in entry-level roles?",
            options=["Technical coding", "Communication", "Biology", "Graphic design"],
            answer="Communication",
        ),
        QuizQuestion(
            id="q2",
            question="Which activity helps improve workplace readiness?",
            options=["Watching videos", "Networking", "Playing games", "Ignoring deadlines"],
            answer="Networking",
        ),
    ]
    quizzes["spectrum-inclusion"] = [
        QuizQuestion(
            id="q3",
            question="Inclusive classrooms prioritize which approach?",
            options=["Standardized testing", "Individual strengths", "Punishment", "Competition"],
            answer="Individual strengths",
        ),
        QuizQuestion(
            id="q4",
            question="What is an important step for supporting diverse learners?",
            options=["Exclude notebooks", "Celebrate differences", "Limit collaboration", "Delay instruction"],
            answer="Celebrate differences",
        ),
    ]
    quizzes["coheart-academy"] = [
        QuizQuestion(
            id="q5",
            question="Which quality helps learners stay resilient?",
            options=["Fixed mindset", "Persistence", "Procrastination", "Isolation"],
            answer="Persistence",
        ),
        QuizQuestion(
            id="q6",
            question="A strong community project should be:",
            options=["Expensive", "Exclusive", "Impactful", "Unplanned"],
            answer="Impactful",
        ),
    ]


initialize_database()
load_data()
initialize_data()
save_data()


def find_user_by_email(email: str) -> Optional[User]:
    return next((user for user in users.values() if user.email == email), None)


def find_user_by_username(username: str) -> Optional[User]:
    return next((user for user in users.values() if user.username == username), None)


def get_user_from_token(authorization: Optional[str] = Header(None)) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization token")
    token = authorization.removeprefix("Bearer ")
    data = sessions.get(token)
    if not data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if isinstance(data, dict):
        user_id = data.get("user_id")
        expires = data.get("expires")
        if expires:
            try:
                exp = datetime.fromisoformat(expires)
                if datetime.utcnow() > exp:
                    sessions.pop(token, None)
                    save_data()
                    raise HTTPException(status_code=401, detail="Token expired")
            except ValueError:
                pass
    else:
        user_id = data
    if not user_id or user_id not in users:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = users[user_id]
    if not getattr(user, "is_active", True):
        raise HTTPException(status_code=403, detail="User deactivated")
    return user


def get_admin_user(user: User = Depends(get_user_from_token)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


@app.post("/auth/register", response_model=AuthResponse)
def register(payload: UserCreate):
    if find_user_by_email(payload.email) or find_user_by_username(payload.username):
        raise HTTPException(status_code=400, detail="User already exists")
    user_id = str(uuid4())
    users[user_id] = User(
        id=user_id,
        username=payload.username,
        email=payload.email,
        password=hash_password(payload.password),
    )
    token = str(uuid4())
    expires = (datetime.utcnow() + timedelta(hours=1)).isoformat()
    sessions[token] = {"user_id": user_id, "expires": expires}
    progress[user_id] = {}
    save_data()
    return AuthResponse(access_token=token)


@app.post("/auth/login", response_model=AuthResponse)
def login(payload: LoginRequest):
    if not payload.email and not payload.username:
        raise HTTPException(status_code=400, detail="Email or username is required")
    user = None
    if payload.email:
        user = find_user_by_email(payload.email)
    if not user and payload.username:
        user = find_user_by_username(payload.username)
    if not user or not verify_password(user.password, payload.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = str(uuid4())
    expires = (datetime.utcnow() + timedelta(hours=1)).isoformat()
    sessions[token] = {"user_id": user.id, "expires": expires}
    if user.id not in progress:
        progress[user.id] = {}
    save_data()
    return AuthResponse(access_token=token)


@app.get("/auth/me")
def auth_me(user: User = Depends(get_user_from_token)):
    perms = []
    try:
        from .roles import get_user_permissions
        perms = list(get_user_permissions(user.id))
    except Exception:
        perms = []
    return {"id": user.id, "username": user.username, "email": user.email, "is_admin": user.is_admin, "permissions": perms}


@app.put("/users/me")
def update_profile(payload: UserUpdate, user: User = Depends(get_user_from_token)):
    if payload.username:
        user.username = payload.username
    if payload.email:
        existing = find_user_by_email(payload.email)
        if existing and existing.id != user.id:
            raise HTTPException(status_code=400, detail="Email already in use")
        user.email = payload.email
    if payload.password:
        user.password = hash_password(payload.password)
    users[user.id] = user
    save_data()
    return {"detail": "Profile updated"}


@app.delete("/users/me")
def deactivate_me(user: User = Depends(get_user_from_token)):
    user.is_active = False
    to_delete = [t for t, s in sessions.items() if (isinstance(s, dict) and s.get("user_id") == user.id) or s == user.id]
    for t in to_delete:
        sessions.pop(t, None)
    save_data()
    return {"detail": "User deactivated"}


@app.get("/courses", response_model=List[Course])
def list_courses():
    return list(courses.values())


@app.get("/courses/{course_id}", response_model=Course)
def get_course(course_id: str):
    course = courses.get(course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return course


@app.get("/courses/{course_id}/lessons", response_model=List[Lesson])
def get_lessons(course_id: str):
    if course_id not in courses:
        raise HTTPException(status_code=404, detail="Course not found")
    return lessons.get(course_id, [])


@app.get("/courses/{course_id}/quiz", response_model=List[QuizQuestion])
def get_quiz(course_id: str, user: User = Depends(get_user_from_token)):
    if course_id not in courses:
        raise HTTPException(status_code=404, detail="Course not found")
    if course_id not in progress.get(user.id, {}):
        raise HTTPException(status_code=403, detail="User not enrolled in this course")
    quiz_questions = quizzes.get(course_id, [])
    return [QuizQuestion(id=q.id, question=q.question, options=q.options) for q in quiz_questions]


@app.post("/courses/{course_id}/enroll")
def enroll_course(course_id: str, user: User = Depends(get_user_from_token)):
    if course_id not in courses:
        raise HTTPException(status_code=404, detail="Course not found")
    user_progress = progress.setdefault(user.id, {})
    if course_id in user_progress:
        return {"message": "Already enrolled"}
    user_progress[course_id] = ProgressItem(course_id=course_id, enrolled=True, completed=False, score=0, certificate_ready=False)
    courses[course_id].students += 1
    save_data()
    return {"message": "Enrolled successfully"}


@app.post("/courses/{course_id}/quiz/submit")
def submit_quiz(course_id: str, payload: QuizSubmitRequest, user: User = Depends(get_user_from_token)):
    if course_id not in courses:
        raise HTTPException(status_code=404, detail="Course not found")
    user_progress = progress.setdefault(user.id, {})
    progress_entry = user_progress.get(course_id)
    if not progress_entry or not progress_entry.enrolled:
        raise HTTPException(status_code=403, detail="User not enrolled in this course")
    correct_answers = {q.id: q.answer for q in quizzes.get(course_id, []) if q.answer is not None}
    score = 0
    for answer in payload.answers:
        if correct_answers.get(answer.question_id) == answer.answer:
            score += 1
    total = len(correct_answers)
    percentage = int((score / total) * 100) if total else 0
    progress_entry.score = percentage
    progress_entry.completed = percentage >= 60
    progress_entry.certificate_ready = progress_entry.completed
    save_data()
    return {
        "score": percentage,
        "completed": progress_entry.completed,
        "certificate_ready": progress_entry.certificate_ready,
    }


@app.get("/progress", response_model=List[ProgressItem])
def get_progress(user: User = Depends(get_user_from_token)):
    return list(progress.get(user.id, {}).values())


@app.get("/certificates/{course_id}")
def get_certificate(course_id: str, user: User = Depends(get_user_from_token)):
    user_progress = progress.setdefault(user.id, {})
    progress_entry = user_progress.get(course_id)
    if not progress_entry or not progress_entry.certificate_ready:
        raise HTTPException(status_code=403, detail="Certificate not available")
    course = courses.get(course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 32)
    pdf.cell(0, 30, "Certificate of Completion", ln=1, align="C")
    pdf.set_font("Helvetica", "", 18)
    pdf.ln(10)
    pdf.multi_cell(0, 12, f"This is to certify that {user.username} has completed the course '{course.title}' through CoHeart Academy.", align="C")
    pdf.ln(10)
    pdf.set_font("Helvetica", "I", 14)
    pdf.cell(0, 10, f"Score: {progress_entry.score}%", ln=1, align="C")
    pdf.ln(10)
    pdf.cell(0, 10, "CoHeart Foundation", ln=1, align="C")
    result = pdf.output(dest="S").encode("latin-1")
    return StreamingResponse(
        BytesIO(result),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=CoHeart_{course_id}_certificate.pdf"},
    )


@app.get("/admin/courses", response_model=List[Course])
def admin_list_courses(user: User = Depends(get_admin_user)):
    return list(courses.values())


@app.post("/admin/courses", response_model=Course)
def admin_create_course(payload: CourseBase, user: User = Depends(get_admin_user)):
    course_id = payload.title.lower().replace(" ", "-")
    if course_id in courses:
        raise HTTPException(status_code=400, detail="Course already exists")
    course = Course(id=course_id, students=0, **payload.model_dump())
    courses[course.id] = course
    lessons[course.id] = []
    quizzes[course.id] = []
    save_data()
    try:
        audit.log_action(user.id, user.username, "create", "course", course.id, before=None, after=course.model_dump())
    except Exception:
        pass
    return course


@app.put("/admin/courses/{course_id}", response_model=Course)
def admin_update_course(course_id: str, payload: CourseBase, user: User = Depends(get_admin_user)):
    course = courses.get(course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    before = course.model_dump()
    course.title = payload.title
    course.description = payload.description
    course.duration = payload.duration
    try:
        audit.log_action(user.id, user.username, "update", "course", course.id, before=before, after=course.model_dump())
    except Exception:
        pass
    save_data()
    return course


@app.delete("/admin/courses/{course_id}")
def admin_delete_course(course_id: str, user: User = Depends(get_admin_user)):
    if course_id not in courses:
        raise HTTPException(status_code=404, detail="Course not found")
    before = courses.get(course_id).model_dump() if course_id in courses else None
    del courses[course_id]
    lessons.pop(course_id, None)
    quizzes.pop(course_id, None)
    for user_id, user_progress in progress.items():
        user_progress.pop(course_id, None)
    try:
        audit.log_action(user.id, user.username, "delete", "course", course_id, before=before, after=None)
    except Exception:
        pass
    save_data()
    return {"detail": "Course removed"}


@app.get("/admin/mis/trackers")
def admin_list_trackers(user: User = Depends(get_admin_user)):
    return list(mis_module.trackers.values())


@app.post("/admin/mis/trackers")
def admin_create_tracker(payload: dict, user: User = Depends(get_admin_user)):
    tid = payload.get("id")
    title = payload.get("title")
    indicators = payload.get("indicators", [])
    if not tid or not title:
        raise HTTPException(status_code=400, detail="id and title required")
    try:
        mis_module.create_tracker(tid, title, indicators)
    except ValueError:
        raise HTTPException(status_code=400, detail="tracker exists")
    try:
        audit.log_action(user.id, user.username, "create", "mis_tracker", tid, before=None, after={"id": tid, "title": title})
    except Exception:
        pass
    save_data()
    return {"id": tid, "title": title}


@app.post("/mis/{tracker_id}/submit")
def submit_mis(tracker_id: str, payload: dict, user: User = Depends(get_user_from_token)):
    values = payload.get("values", {})
    try:
        entry = mis_module.submit_data(tracker_id, user.id, values)
    except KeyError:
        raise HTTPException(status_code=404, detail="tracker not found")
    save_data()
    return entry


@app.get("/admin/mis/{tracker_id}/report")
def mis_report(tracker_id: str, user: User = Depends(get_admin_user)):
    try:
        return mis_module.report_aggregate(tracker_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="tracker not found")


@app.get("/admin/audit")
def admin_get_audit(user: User = Depends(get_admin_user)):
    return audit.get_logs()


@app.post("/admin/notifications")
def admin_send_notification(payload: dict, user: User = Depends(get_admin_user)):
    target = payload.get("target_user_id")
    title = payload.get("title")
    message = payload.get("message")
    send_email_flag = bool(payload.get("send_email"))
    if not title or not message:
        raise HTTPException(status_code=400, detail="title and message required")
    email_addr = None
    if send_email_flag and target:
        u = users.get(target)
        if u:
            email_addr = u.email
    entry = notifications_module.create_notification(target, title, message, user.id, send_email_flag, email_addr)
    save_data()
    try:
        audit.log_action(user.id, user.username, "create", "notification", entry["id"], before=None, after=entry)
    except Exception:
        pass
    return entry


@app.get('/notifications')
def get_notifications(user: User = Depends(get_user_from_token)):
    return notifications_module.list_user_notifications(user.id)


@app.post('/notifications/{notification_id}/read')
def post_mark_read(notification_id: str, user: User = Depends(get_user_from_token)):
    ok = notifications_module.mark_read(notification_id, user.id)
    if not ok:
        raise HTTPException(status_code=404, detail='notification not found')
    save_data()
    return {'detail': 'marked'}


@app.get("/admin/documents")
def admin_list_documents(user: User = Depends(get_admin_user)):
    return docs_module.list_documents()


@app.post("/admin/documents")
def admin_create_document(title: str = None, file: UploadFile = File(...), user: User = Depends(get_admin_user)):
    if not title:
        raise HTTPException(status_code=400, detail="title required")
    data = file.file.read()
    doc_id = title.lower().replace(' ', '-')
    try:
        docs_module.create_document(doc_id, title, file.filename or 'file', data, user.id)
    except ValueError:
        raise HTTPException(status_code=400, detail="document exists")
    save_data()
    try:
        audit.log_action(user.id, user.username, "create", "document", doc_id, before=None, after={"title": title})
    except Exception:
        pass
    return {"id": doc_id, "title": title}


@app.post("/admin/documents/{doc_id}/upload")
def admin_upload_version(doc_id: str, file: UploadFile = File(...), user: User = Depends(get_admin_user)):
    data = file.file.read()
    try:
        entry = docs_module.add_version(doc_id, file.filename or 'file', data, user.id)
    except KeyError:
        raise HTTPException(status_code=404, detail="document not found")
    save_data()
    try:
        audit.log_action(user.id, user.username, "upload", "document", doc_id, before=None, after=entry)
    except Exception:
        pass
    return entry


@app.get("/documents")
def list_documents(user: User = Depends(get_user_from_token)):
    return docs_module.list_documents()


@app.get("/documents/{doc_id}/versions")
def document_versions(doc_id: str, user: User = Depends(get_user_from_token)):
    try:
        return docs_module.list_versions(doc_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="document not found")


@app.get("/documents/{doc_id}/download/{version}")
def download_version(doc_id: str, version: int, user: User = Depends(get_user_from_token)):
    path = docs_module.get_version_file_path(doc_id, version)
    if not path:
        raise HTTPException(status_code=404, detail="version not found")
    return StreamingResponse(open(path, 'rb'), media_type='application/octet-stream', headers={"Content-Disposition": f"attachment; filename={Path(path).name}"})


@app.delete("/admin/documents/{doc_id}")
def admin_delete_document(doc_id: str, user: User = Depends(get_admin_user)):
    try:
        before = docs_module.documents.get(doc_id)
        docs_module.delete_document(doc_id)
        audit.log_action(user.id, user.username, "delete", "document", doc_id, before=before, after=None)
        save_data()
        return {"detail": "deleted"}
    except Exception:
        raise HTTPException(status_code=500, detail="failed to delete")


@app.post("/auth/logout")
def logout(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=400, detail="Missing authorization token")
    token = authorization.removeprefix("Bearer ")
    if token in sessions:
        del sessions[token]
        save_data()
    return {"detail": "Logged out"}


@app.get("/admin/users")
def admin_list_users(user: User = Depends(get_admin_user)):
    out = []
    for u in users.values():
        out.append({"id": u.id, "username": u.username, "email": u.email, "is_admin": u.is_admin, "roles": roles_module.get_user_roles(u.id)})
    return out


@app.get("/admin/courses/{course_id}/lessons", response_model=List[Lesson])
def admin_list_lessons(course_id: str, user: User = Depends(get_admin_user)):
    if course_id not in courses:
        raise HTTPException(status_code=404, detail="Course not found")
    return lessons.get(course_id, [])


@app.get("/admin/roles")
def admin_list_roles(user: User = Depends(get_admin_user)):
    return list(roles_module.roles.values())


@app.post("/admin/roles")
def admin_create_role(payload: dict, user: User = Depends(get_admin_user)):
    name = payload.get("name")
    perms = payload.get("permissions", [])
    desc = payload.get("description")
    if not name:
        raise HTTPException(status_code=400, detail="Role name required")
    try:
        roles_module.create_role(name, perms, desc)
    except ValueError:
        raise HTTPException(status_code=400, detail="Role exists")
    save_data()
    try:
        audit.log_action(user.id, user.username, "create", "role", name, before=None, after={"name": name, "permissions": perms})
    except Exception:
        pass
    return {"name": name, "permissions": perms}


@app.put("/admin/roles/{role_name}")
def admin_update_role(role_name: str, payload: dict, user: User = Depends(get_admin_user)):
    perms = payload.get("permissions", [])
    desc = payload.get("description")
    try:
        before = roles_module.roles.get(role_name)
        roles_module.update_role(role_name, perms, desc)
        audit.log_action(user.id, user.username, "update", "role", role_name, before=before, after=roles_module.roles.get(role_name))
    except KeyError:
        raise HTTPException(status_code=404, detail="Role not found")
    save_data()
    return roles_module.roles.get(role_name)


@app.delete("/admin/roles/{role_name}")
def admin_delete_role(role_name: str, user: User = Depends(get_admin_user)):
    before = roles_module.roles.get(role_name)
    delete_ok = True
    try:
        roles_module.delete_role(role_name)
    except Exception:
        delete_ok = False
    if not delete_ok:
        raise HTTPException(status_code=500, detail="Could not delete role")
    try:
        audit.log_action(user.id, user.username, "delete", "role", role_name, before=before, after=None)
    except Exception:
        pass
    save_data()
    return {"detail": "role removed"}


@app.post("/admin/users/{user_id}/roles")
def admin_assign_role(user_id: str, payload: dict, user: User = Depends(get_admin_user)):
    role_name = payload.get("role")
    if not role_name:
        raise HTTPException(status_code=400, detail="role required")
    if user_id not in users:
        raise HTTPException(status_code=404, detail="user not found")
    try:
        roles_module.assign_role_to_user(user_id, role_name)
        audit.log_action(user.id, user.username, "assign_role", "user", user_id, before=None, after={"role": role_name})
    except KeyError:
        raise HTTPException(status_code=404, detail="role not found")
    save_data()
    return {"detail": "role assigned"}


@app.delete("/admin/users/{user_id}/roles/{role_name}")
def admin_remove_role(user_id: str, role_name: str, user: User = Depends(get_admin_user)):
    if user_id not in users:
        raise HTTPException(status_code=404, detail="user not found")
    roles_module.remove_role_from_user(user_id, role_name)
    try:
        audit.log_action(user.id, user.username, "remove_role", "user", user_id, before=None, after={"role": role_name})
    except Exception:
        pass
    save_data()
    return {"detail": "role removed"}


@app.post("/admin/courses/{course_id}/lessons", response_model=Lesson)
def admin_create_lesson(course_id: str, payload: LessonCreate, user: User = Depends(get_admin_user)):
    if course_id not in courses:
        raise HTTPException(status_code=404, detail="Course not found")
    lid = uuid4().hex
    lesson = Lesson(id=lid, title=payload.title, content=payload.content)
    lessons.setdefault(course_id, []).append(lesson)
    save_data()
    return lesson


@app.put("/admin/courses/{course_id}/lessons/{lesson_id}", response_model=Lesson)
def admin_update_lesson(course_id: str, lesson_id: str, payload: LessonCreate, user: User = Depends(get_admin_user)):
    if course_id not in courses:
        raise HTTPException(status_code=404, detail="Course not found")
    lst = lessons.get(course_id, [])
    for i, l in enumerate(lst):
        if l.id == lesson_id:
            lst[i] = Lesson(id=lesson_id, title=payload.title, content=payload.content)
            save_data()
            return lst[i]
    raise HTTPException(status_code=404, detail="Lesson not found")


@app.delete("/admin/courses/{course_id}/lessons/{lesson_id}")
def admin_delete_lesson(course_id: str, lesson_id: str, user: User = Depends(get_admin_user)):
    if course_id not in courses:
        raise HTTPException(status_code=404, detail="Course not found")
    lst = lessons.get(course_id, [])
    lessons[course_id] = [l for l in lst if l.id != lesson_id]
    save_data()
    return {"detail": "Lesson removed"}


@app.get("/admin/courses/{course_id}/quizzes", response_model=List[QuizQuestion])
def admin_list_quizzes(course_id: str, user: User = Depends(get_admin_user)):
    if course_id not in courses:
        raise HTTPException(status_code=404, detail="Course not found")
    return quizzes.get(course_id, [])


@app.post("/admin/courses/{course_id}/quizzes", response_model=QuizQuestion)
def admin_create_quiz(course_id: str, payload: QuizQuestionCreate, user: User = Depends(get_admin_user)):
    if course_id not in courses:
        raise HTTPException(status_code=404, detail="Course not found")
    qid = uuid4().hex
    q = QuizQuestion(id=qid, question=payload.question, options=payload.options, answer=payload.answer)
    quizzes.setdefault(course_id, []).append(q)
    save_data()
    return q


@app.put("/admin/courses/{course_id}/quizzes/{quiz_id}", response_model=QuizQuestion)
def admin_update_quiz(course_id: str, quiz_id: str, payload: QuizQuestionCreate, user: User = Depends(get_admin_user)):
    if course_id not in courses:
        raise HTTPException(status_code=404, detail="Course not found")
    lst = quizzes.get(course_id, [])
    for i, q in enumerate(lst):
        if q.id == quiz_id:
            lst[i] = QuizQuestion(id=quiz_id, question=payload.question, options=payload.options, answer=payload.answer)
            save_data()
            return lst[i]
    raise HTTPException(status_code=404, detail="Quiz question not found")


@app.delete("/admin/courses/{course_id}/quizzes/{quiz_id}")
def admin_delete_quiz(course_id: str, quiz_id: str, user: User = Depends(get_admin_user)):
    if course_id not in courses:
        raise HTTPException(status_code=404, detail="Course not found")
    lst = quizzes.get(course_id, [])
    quizzes[course_id] = [q for q in lst if q.id != quiz_id]
    save_data()
    return {"detail": "Quiz question removed"}
