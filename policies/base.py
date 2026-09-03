from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class PermissionCheckContext:
    request: object
    view: object
    action: str


PermissionPolicy = Callable[[PermissionCheckContext], bool]


def deny_all(context: PermissionCheckContext) -> bool:
    return False


def any_authenticated_user(context: PermissionCheckContext) -> bool:
    user = getattr(context.request, 'user', None)
    return bool(user and getattr(user, 'is_authenticated', False))
