import hashlib
import json
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

from app.preflight_service import get_live_preflight
from app.schemas import (
    LivePromotionApproveRequest,
    LivePromotionRequestOut,
    LivePromotionRequestResponse,
    LivePromotionStatusOut,
    StrategyUpdate,
)
from app.services import update_active_strategy

PROMOTION_TOKEN_BYTES = 32
DEFAULT_TTL_HOURS = 24


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def request_live_promotion(conn: sqlite3.Connection) -> LivePromotionRequestResponse:
    preflight = get_live_preflight(conn)
    token = secrets.token_urlsafe(PROMOTION_TOKEN_BYTES)
    now = datetime.now(timezone.utc)
    expires_at = (now + timedelta(hours=DEFAULT_TTL_HOURS)).isoformat()
    conn.execute(
        """
        INSERT INTO live_promotion_requests (
            token_hash, status, requested_at, expires_at, preflight_snapshot_json
        ) VALUES (?, 'pending', ?, ?, ?)
        """,
        (
            _hash_token(token),
            now.isoformat(),
            expires_at,
            json.dumps(preflight.model_dump()),
        ),
    )
    return LivePromotionRequestResponse(
        promotion_token=token,
        expires_at=expires_at,
        preflight_ready=preflight.ready_for_live,
        message=(
            "Approve with POST /api/admin/live-promotion/approve using this token."
            if preflight.ready_for_live
            else "Preflight not passing — fix checks before approving live mode."
        ),
    )


def approve_live_promotion(
    conn: sqlite3.Connection,
    payload: LivePromotionApproveRequest,
) -> LivePromotionStatusOut:
    if not payload.promotion_token.strip():
        raise ValueError("promotion_token is required")

    row = conn.execute(
        """
        SELECT id, status, expires_at, preflight_snapshot_json
        FROM live_promotion_requests
        WHERE token_hash = ?
        """,
        (_hash_token(payload.promotion_token),),
    ).fetchone()
    if row is None:
        raise ValueError("Invalid or unknown promotion token")

    if row["status"] != "pending":
        raise ValueError(f"Promotion request already {row['status']}")

    expires = datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00"))
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires <= datetime.now(timezone.utc):
        conn.execute(
            "UPDATE live_promotion_requests SET status = 'expired' WHERE id = ?",
            (row["id"],),
        )
        raise ValueError("Promotion token expired")

    preflight = get_live_preflight(conn)
    if not preflight.ready_for_live:
        raise ValueError("Preflight checks failing — cannot approve live promotion")

    now = _iso_now()
    conn.execute(
        """
        UPDATE live_promotion_requests
        SET status = 'approved', approved_at = ?, approved_by = ?
        WHERE id = ?
        """,
        (now, payload.approved_by or "operator", row["id"]),
    )

    update_active_strategy(
        conn,
        StrategyUpdate(mode="live", trading_enabled=True, kill_switch=False),
    )

    return get_live_promotion_status(conn)


def get_live_promotion_status(conn: sqlite3.Connection) -> LivePromotionStatusOut:
    row = conn.execute(
        """
        SELECT id, status, requested_at, approved_at, expires_at, approved_by,
               preflight_snapshot_json
        FROM live_promotion_requests
        ORDER BY id DESC LIMIT 1
        """
    ).fetchone()
    preflight = get_live_preflight(conn)
    latest = None
    if row is not None:
        latest = LivePromotionRequestOut(
            id=row["id"],
            status=row["status"],
            requested_at=row["requested_at"],
            approved_at=row["approved_at"],
            expires_at=row["expires_at"],
            approved_by=row["approved_by"],
        )
    return LivePromotionStatusOut(
        latest_request=latest,
        preflight_ready=preflight.ready_for_live,
        live_trading_allowed=preflight.ready_for_live,
    )
