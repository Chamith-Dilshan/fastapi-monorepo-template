"""Role-based access control.

Lives next to `security_dep.py` rather than in `app/core/` because it builds
on `get_current_user_dep` — `core` is the layer everything else depends on,
and it shouldn't import upward from the dependency layer.

Usage:

    @router.delete("/{user_id}")
    async def delete_user(admin: AdminUser, ...): # shortcut
        ...

    @router.get(" ")
    async def list_users(
        user: Annotated[User, Depends(require_role(UserRole.ADMIN, UserRole.MANAGER))],
    ): ...

The role set is a plain allowlist on purpose — no implicit "admin
includes manager" hierarchy. Where a route should accept several roles,
it says so, and the code reads the same as the intent.
"""

from typing import Annotated

from fastapi import Depends

from app.core.exceptions import ForbiddenException
from app.dependancies.security_dep import get_current_user_dep
from app.models.user import User, UserRole


def require_role(*allowed: UserRole):
    allowed_roles = frozenset(allowed)

    async def dependency(
        current_user: Annotated[User, Depends(get_current_user_dep)],
    ) -> User:
        if current_user.role not in allowed_roles:
            raise ForbiddenException(
                message="You do not have permission to perform this action"
            )
        return current_user

    return dependency


AdminUser = Annotated[User, Depends(require_role(UserRole.ADMIN))]
StaffUser = Annotated[User, Depends(require_role(UserRole.ADMIN, UserRole.MANAGER))]
