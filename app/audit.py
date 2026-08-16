from datetime import datetime
from typing import Any, Dict, List, Optional

# Simple in-memory audit log. Persisted by main.save_data/load_data via the
# top-level persistence payload under key "audit_logs".
audit_logs: List[Dict[str, Any]] = []


def log_action(user_id: str, username: str, action: str, resource_type: str, resource_id: Optional[str] = None, before: Optional[Dict[str, Any]] = None, after: Optional[Dict[str, Any]] = None) -> None:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "user_id": user_id,
        "username": username,
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "before": before,
        "after": after,
    }
    audit_logs.append(entry)


def get_logs(limit: int = 200, resource_type: Optional[str] = None) -> List[Dict[str, Any]]:
    results = audit_logs[:]  # newest are appended at end
    if resource_type:
        results = [r for r in results if r.get("resource_type") == resource_type]
    return list(reversed(results))[:limit]
