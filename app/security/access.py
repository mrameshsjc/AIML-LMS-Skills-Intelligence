"""
Who may see whose data (Phase 17).

THE RULES
    login switched off   everyone may see everything (local development only)
    admin                every employee
    manager              themselves and everyone below them in the manager chain
    employee             themselves only

    A request for someone else's data is refused with 403 ACCESS_DENIED - the
    API never says whether that employee exists, so IDs cannot be probed.

TENANTS
    A token belongs to one tenant (customer). This server serves RAG_TENANT; a
    token for another tenant is refused, so no customer can reach another's
    employees or documents.
"""

from __future__ import annotations

from app.core.errors import ForbiddenError
from app.repositories.base import LmsRepository
from app.security.users import Principal


def team_of(manager_employee_id: str, repo: LmsRepository) -> set[str]:
    """The manager and everyone who reports to them, directly or indirectly."""
    team, stack = {manager_employee_id}, [manager_employee_id]
    while stack:
        for report in repo.direct_reports(stack.pop()):
            if report not in team:
                team.add(report)
                stack.append(report)
    return team


def can_view(principal: Principal, employee_id: str, repo: LmsRepository) -> bool:
    if not principal.authenticated or principal.is_admin:
        return True
    if principal.employee_id is None:
        return False
    if principal.role == "manager":
        return employee_id in team_of(principal.employee_id, repo)
    return employee_id == principal.employee_id


def authorize_employee(principal: Principal, employee_id: str | None, repo: LmsRepository) -> None:
    if employee_id is not None and not can_view(principal, employee_id, repo):
        raise ForbiddenError("ACCESS_DENIED", "You may not view this employee's data.")


def check_tenant(principal: Principal, tenant: str) -> None:
    if principal.authenticated and principal.tenant != tenant:
        raise ForbiddenError("WRONG_TENANT", "This account belongs to another organisation.")
