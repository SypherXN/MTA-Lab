from fastapi import Depends, Header, HTTPException, status


def _extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


def require_write_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    from app.config import settings

    if not x_api_key or x_api_key != settings.write_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-API-Key",
        )


def require_read_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
) -> None:
    from app.auth_service import is_valid_dashboard_session
    from app.config import settings
    from app.database import get_connection

    if not settings.read_auth_enabled and not settings.dashboard_auth_enabled:
        return

    if x_api_key in (settings.read_api_key, settings.write_api_key):
        return

    session_token = _extract_bearer_token(authorization)
    if session_token and settings.dashboard_auth_enabled:
        conn = get_connection()
        try:
            if is_valid_dashboard_session(conn, session_token):
                return
        finally:
            conn.close()

    if settings.read_auth_enabled:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-API-Key for read access",
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Dashboard login required (POST /api/auth/login)",
    )


def require_dashboard_strategy_write(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
) -> None:
    from app.auth_service import is_valid_dashboard_session
    from app.config import settings
    from app.database import get_connection

    if x_api_key == settings.write_api_key:
        return

    session_token = _extract_bearer_token(authorization)
    if session_token and settings.dashboard_auth_enabled:
        conn = get_connection()
        try:
            if is_valid_dashboard_session(conn, session_token):
                return
        finally:
            conn.close()

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Write API key or dashboard login required for strategy changes",
    )


WriteKeyDep = Depends(require_write_api_key)
ReadKeyDep = Depends(require_read_api_key)
DashboardStrategyWriteDep = Depends(require_dashboard_strategy_write)
