"""
Users and roles (Phase 17).

ROLES
    employee   their own data only (skills, roles, courses, path, assistant)
    manager    their own data and their team's (employees whose manager chain
               leads to them, from employees.csv manager_id)
    admin      everyone's data, plus administrator actions: retraining (API 6)
               and document uploads/deletions (API 7)

WHERE USERS ARE STORED
    A JSON file, USERS_FILE (default data/users.json, git-ignored), managed with
        python scripts/create_user.py <username> --role employee --employee E1001
        python scripts/create_demo_users.py
    Each user has a password HASH (never the password), a role, the employee it
    belongs to (for employee/manager) and a tenant. In the LMS integration the
    LMS's own login replaces this file; the roles stay the same.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from app.data_processing.loader import resolve_folder
from app.security.passwords import hash_password, verify_password

ROLES = ("employee", "manager", "admin")


@dataclass(frozen=True)
class User:
    username: str
    password_hash: str
    role: str
    employee_id: str | None = None
    tenant: str = "default"
    disabled: bool = False


@dataclass(frozen=True)
class Principal:
    """Who is making a request: the result of checking their token."""

    username: str
    role: str  # employee | manager | admin | anonymous (login switched off)
    employee_id: str | None
    tenant: str = "default"
    authenticated: bool = True

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


class UserStore:
    def __init__(self, path: str | Path) -> None:
        file = Path(path)
        self.path = file if file.is_absolute() else resolve_folder(file.parent) / file.name

    def _load(self) -> dict[str, User]:
        if not self.path.exists():
            return {}
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return {u["username"]: User(**u) for u in raw.get("users", [])}

    def get(self, username: str) -> User | None:
        return self._load().get(username)

    def all(self) -> list[User]:
        return sorted(self._load().values(), key=lambda u: u.username)

    def authenticate(self, username: str, password: str) -> User | None:
        user = self.get(username)
        if user is None:
            verify_password(
                password, _DUMMY_HASH
            )  # same work for unknown users: timing does not reveal names
            return None
        if user.disabled or not verify_password(password, user.password_hash):
            return None
        return user

    def save(
        self,
        username: str,
        password: str,
        role: str,
        employee_id: str | None = None,
        tenant: str = "default",
    ) -> User:
        if role not in ROLES:
            raise ValueError(f"Role must be one of {', '.join(ROLES)}.")
        if role in ("employee", "manager") and not employee_id:
            raise ValueError(f"A {role} account needs the employee ID it belongs to.")
        users = self._load()
        users[username] = User(username, hash_password(password), role, employee_id, tenant)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {"users": [asdict(u) for u in sorted(users.values(), key=lambda u: u.username)]}
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return users[username]


_DUMMY_HASH = "pbkdf2_sha256$600000$00000000000000000000000000000000$" + "0" * 64
