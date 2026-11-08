"""
Create the three demo accounts for trying login locally (Phase 17).

    employee  E1001                sees only E1001
    manager   E1064               sees E1064 and everyone reporting to them (E1001 among them)
    admin     -                   sees everyone, uploads documents, retrains

The passwords are RANDOM and printed once - this script never puts a fixed
password into the code or into Git. Run it again to get new ones.

    PS> python scripts/create_demo_users.py
"""

import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.security.users import UserStore  # noqa: E402

DEMO = [("employee", "employee", "E1001"), ("manager", "manager", "E1064"), ("admin", "admin", None)]

settings = get_settings()
store = UserStore(settings.users_file)
print(f"Demo accounts in {store.path} (synthetic data only):\n")
for username, role, employee_id in DEMO:
    password = secrets.token_urlsafe(12)
    store.save(username, password, role, employee_id, settings.rag_tenant)
    print(f"  {username:<9} password: {password:<18} role: {role:<8} employee: {employee_id or '-'}")
print("\nKeep these somewhere safe; they are not shown again. Then set AUTH_ENABLED=true in .env.")
