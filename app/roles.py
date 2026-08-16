from typing import Dict, List, Optional, Set

# Simple roles & permissions store
roles: Dict[str, Dict] = {}
# user_id -> list of role names
user_roles: Dict[str, List[str]] = {}


def create_role(name: str, permissions: List[str], description: Optional[str] = None) -> Dict:
    if name in roles:
        raise ValueError("role exists")
    roles[name] = {"name": name, "permissions": list(sorted(set(permissions))), "description": description}
    return roles[name]


def update_role(name: str, permissions: List[str], description: Optional[str] = None) -> Dict:
    if name not in roles:
        raise KeyError("role not found")
    roles[name]["permissions"] = list(sorted(set(permissions)))
    roles[name]["description"] = description
    return roles[name]


def delete_role(name: str) -> None:
    if name in roles:
        del roles[name]
    # remove from user_roles
    for uid, rlist in list(user_roles.items()):
        if name in rlist:
            user_roles[uid] = [r for r in rlist if r != name]


def assign_role_to_user(user_id: str, role_name: str) -> None:
    user_roles.setdefault(user_id, [])
    if role_name not in roles:
        raise KeyError("role not found")
    if role_name not in user_roles[user_id]:
        user_roles[user_id].append(role_name)


def remove_role_from_user(user_id: str, role_name: str) -> None:
    if user_id in user_roles:
        user_roles[user_id] = [r for r in user_roles[user_id] if r != role_name]


def get_user_roles(user_id: str) -> List[str]:
    return user_roles.get(user_id, [])


def get_user_permissions(user_id: str) -> Set[str]:
    perms = set()
    for r in get_user_roles(user_id):
        role = roles.get(r)
        if role:
            perms.update(role.get("permissions", []))
    return perms
