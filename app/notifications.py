from typing import Dict, List, Optional
from uuid import uuid4
from datetime import datetime
import smtplib
import os
from email.message import EmailMessage

notifications: List[Dict] = []


def _now():
    return datetime.utcnow().isoformat()


def send_email(to_email: str, subject: str, body: str) -> bool:
    # Uses env vars: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM
    host = os.environ.get('SMTP_HOST')
    port = int(os.environ.get('SMTP_PORT', '0') or 0)
    user = os.environ.get('SMTP_USER')
    password = os.environ.get('SMTP_PASS')
    sender = os.environ.get('SMTP_FROM', user)
    if not host or not port:
        return False
    try:
        msg = EmailMessage()
        msg['Subject'] = subject
        msg['From'] = sender
        msg['To'] = to_email
        msg.set_content(body)
        with smtplib.SMTP(host, port, timeout=10) as s:
            if os.environ.get('SMTP_STARTTLS', 'true').lower() in ('1', 'true', 'yes'):
                s.starttls()
            if user and password:
                s.login(user, password)
            s.send_message(msg)
        return True
    except Exception:
        return False


def create_notification(target_user_id: Optional[str], title: str, message: str, sent_by: str, send_email_flag: bool = False, email_addr: Optional[str] = None) -> Dict:
    nid = str(uuid4())
    entry = {
        'id': nid,
        'target_user_id': target_user_id,
        'title': title,
        'message': message,
        'sent_by': sent_by,
        'timestamp': _now(),
        'read': False,
    }
    notifications.append(entry)
    if send_email_flag and email_addr:
        send_email(email_addr, title, message)
    return entry


def list_user_notifications(user_id: str, limit: int = 200) -> List[Dict]:
    # include broadcasts (target_user_id is None) and specific
    results = [n for n in notifications if n.get('target_user_id') in (None, user_id)]
    return list(reversed(results))[:limit]


def mark_read(notification_id: str, user_id: str) -> bool:
    for n in notifications:
        if n.get('id') == notification_id and (n.get('target_user_id') in (None, user_id)):
            n['read'] = True
            return True
    return False
