"""FastAPI dependencies: the signed-in researcher, and HTTP wrapping of domain errors."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .core import content, security, settings
from .schemas.auth import SessionUser

_bearer = HTTPBearer(auto_error=False, scheme_name=settings.AUTH_SCHEME)


def current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> SessionUser:
    """Verify the bearer token on a workspace request.

    Missing Atlas credentials lock the workspace with 503. A missing or
    unusable token is 401. The snapshot stays readable for public search either
    way.
    """
    try:
        security.signing_secret()
    except security.NotConfigured as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=content.ERRORS["auth_not_configured"],
        ) from error
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=content.ERRORS["sign_in_required"],
            headers={"WWW-Authenticate": settings.AUTH_SCHEME},
        )
    try:
        return security.read(credentials.credentials)
    except security.InvalidToken as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=content.ERRORS["session_expired"],
            headers={"WWW-Authenticate": settings.AUTH_SCHEME},
        ) from error


def is_admin(user: SessionUser) -> bool:
    if user.role == settings.ADMIN_ROLE:
        return True
    return str(user.email).lower() in settings.admin_emails()


def require_admin(user: Annotated[SessionUser, Depends(current_user)]) -> SessionUser:
    """Workspace session that must belong to an administrator."""
    if not is_admin(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=content.ERRORS["admin_required"],
        )
    return user


WORKSPACE = [Depends(current_user)]
ADMIN = [Depends(require_admin)]
