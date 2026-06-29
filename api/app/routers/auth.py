from fastapi import APIRouter, Header, HTTPException, status

from app.auth_service import create_dashboard_session, purge_expired_sessions, revoke_dashboard_session
from app.config import settings
from app.database import get_connection
from app.schemas import DashboardLoginRequest, DashboardLoginResponse, DashboardLogoutResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=DashboardLoginResponse)
def dashboard_login(payload: DashboardLoginRequest) -> DashboardLoginResponse:
    if not settings.dashboard_auth_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Dashboard login is not configured (set MTA_DASHBOARD_PASSWORD)",
        )
    if payload.password != settings.dashboard_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid password",
        )

    conn = get_connection()
    try:
        purge_expired_sessions(conn)
        token, expires_at = create_dashboard_session(conn)
        conn.commit()
        return DashboardLoginResponse(token=token, expires_at=expires_at)
    finally:
        conn.close()


@router.post("/logout", response_model=DashboardLogoutResponse)
def dashboard_logout(
    authorization: str | None = Header(default=None),
) -> DashboardLogoutResponse:
    token = _extract_bearer_token(authorization)
    if not token:
        return DashboardLogoutResponse(revoked=False, message="No session token provided")

    conn = get_connection()
    try:
        revoked = revoke_dashboard_session(conn, token)
        conn.commit()
        return DashboardLogoutResponse(
            revoked=revoked,
            message="Session revoked" if revoked else "Session not found",
        )
    finally:
        conn.close()


def _extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None
