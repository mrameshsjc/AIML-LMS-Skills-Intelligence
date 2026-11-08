"""
Create or update a login account (Phase 17).

Accounts live in USERS_FILE (default data/users.json, git-ignored). Only a salted
PBKDF2 hash of the password is stored, never the password itself.

ROLES
    employee   sees only their own data           needs --employee E1001
    manager    sees themselves and their team     needs --employee (their own ID)
    admin      sees everyone; uploads documents and retrains the model

HOW TO RUN (PowerShell, venv activated, from the project folder)
    PS> python scripts/create_user.py asha --role employee --employee E1001
    PS> python scripts/create_user.py admin --role admin
    PS> python scripts/create_user.py --list
    The password is asked for (not shown, not stored in your shell history).
    For scripts only: --password-env NAME reads it from an environment variable.

Then start the API with AUTH_ENABLED=true and AUTH_SECRET_KEY set (see .env.example).
"""

import argparse
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.repositories.csv_repository import CsvLmsRepository  # noqa: E402
from app.security.users import ROLES, UserStore  # noqa: E402

parser = argparse.ArgumentParser(description="Create or update a login account.")
parser.add_argument("username", nargs="?", help="letters, digits, '.', '-' and '_'")
parser.add_argument("--role", choices=ROLES, default="employee")
parser.add_argument("--employee", help="the employee ID the account belongs to (employee and manager)")
parser.add_argument("--password-env", help="read the password from this environment variable")
parser.add_argument("--list", action="store_true", help="list the accounts (never the passwords)")
args = parser.parse_args()

settings = get_settings()
store = UserStore(settings.users_file)

if args.list:
    users = store.all()
    print(f"{len(users)} account(s) in {store.path}")
    for u in users:
        flag = "  (disabled)" if u.disabled else ""
        print(f"  {u.username:<20} {u.role:<9} {u.employee_id or '-':<6} tenant={u.tenant}{flag}")
    sys.exit(0)

if not args.username or not args.username.replace(".", "").replace("-", "").replace("_", "").isalnum():
    sys.exit("Give a username made of letters, digits, '.', '-' and '_'.")
if args.employee and CsvLmsRepository(settings.data_dir).get_employee(args.employee) is None:
    sys.exit(f"Employee {args.employee} does not exist in {settings.data_dir}.")

if args.password_env:
    password = os.environ.get(args.password_env, "")
else:
    password = getpass.getpass("Password (at least 8 characters): ")
    if getpass.getpass("Repeat it: ") != password:
        sys.exit("The passwords differ.")

try:
    user = store.save(args.username, password, args.role, args.employee, settings.rag_tenant)
except ValueError as error:
    sys.exit(str(error))
belongs = f", {user.employee_id}" if user.employee_id else ""
print(f"Saved {user.username} ({user.role}{belongs}) in {store.path}")
if not settings.auth_enabled:
    print("Note: AUTH_ENABLED is false, so the API does not ask for a login yet.")
