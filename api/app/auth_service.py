import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import sqlite3

from app.config import settings

SESSION_TOKEN_BYTES = 32


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_dashboard_session(conn: sqlite3.Connection) -> tuple[str, str]:
    token = secrets.token_urlsafe(SESSION_TOKEN_BYTES)
    expires_at = (
        datetime.now(timezone.utc) + timedelta(hours=settings.session_ttl_hours)
    ).isoformat()
    conn.execute(
        """
        INSERT INTO dashboard_sessions (token_hash, expires_at, created_at)
        VALUES (?, ?, ?)
        """,
        (_hash_token(token), expires_at, _iso_now()),
    )
    return token, expires_at


def revoke_dashboard_session(conn: sqlite3.Connection, token: str) -> bool:
    cursor = conn.execute(
        "DELETE FROM dashboard_sessions WHERE token_hash = ?",
        (_hash_token(token),),
    )
    return cursor.rowcount > 0


def is_valid_dashboard_session(conn: sqlite3.Connection, token: str) -> bool:
    if not token.strip():
        return False
    row = conn.execute(
        """
        SELECT expires_at FROM dashboard_sessions
        WHERE token_hash = ?
        """,
        (_hash_token(token),),
    ).fetchone()
    if row is None:
        return False
    expires_at = datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00"))
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= datetime.now(timezone.utc):
        conn.execute(
            "DELETE FROM dashboard_sessions WHERE token_hash = ?",
            (_hash_token(token),),
        )
        return False
    return True


def purge_expired_sessions(conn: sqlite3.Connection) -> int:
    now = _iso_now()
    cursor = conn.execute(
        "DELETE FROM dashboard_sessions WHERE expires_at <= ?",
        (now,),
    )
    return cursor.rowcount
