"""Store large raw payloads compactly with optional compression."""

import base64
import gzip
import json
import sqlite3
from datetime import datetime, timezone

from app.config import settings
from app.schemas import CompactPayloadOut

MAX_INLINE_CHARS = 2000


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _compress(text: str) -> tuple[str, bool]:
    raw = text.encode("utf-8")
    if len(raw) <= settings.compact_payload_max_bytes:
        return text, False
    compressed = gzip.compress(raw)
    encoded = base64.b64encode(compressed).decode("ascii")
    return encoded, True


def _decompress(stored: str, compressed: bool) -> str:
    if not compressed:
        return stored
    data = gzip.decompress(base64.b64decode(stored.encode("ascii")))
    return data.decode("utf-8")


def store_compact_payload(
    conn: sqlite3.Connection,
    *,
    entity_type: str,
    entity_id: str,
    payload: dict | str,
    summary: str | None = None,
) -> CompactPayloadOut:
    if isinstance(payload, dict):
        text = json.dumps(payload, separators=(",", ":"))
    else:
        text = payload

    truncated = len(text) > MAX_INLINE_CHARS
    display_summary = summary or (text[:MAX_INLINE_CHARS] + "…" if truncated else text)
    stored, is_compressed = _compress(text)
    byte_size = len(text.encode("utf-8"))
    now = _iso_now()

    conn.execute(
        """
        INSERT INTO compact_payloads (
            entity_type, entity_id, summary, payload_storage, is_compressed,
            byte_size, truncated, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(entity_type, entity_id) DO UPDATE SET
            summary = excluded.summary,
            payload_storage = excluded.payload_storage,
            is_compressed = excluded.is_compressed,
            byte_size = excluded.byte_size,
            truncated = excluded.truncated,
            updated_at = excluded.updated_at
        """,
        (
            entity_type,
            entity_id,
            display_summary,
            stored,
            1 if is_compressed else 0,
            byte_size,
            1 if truncated else 0,
            now,
        ),
    )
    row = conn.execute(
        """
        SELECT id, entity_type, entity_id, summary, byte_size, truncated, is_compressed, updated_at
        FROM compact_payloads WHERE entity_type = ? AND entity_id = ?
        """,
        (entity_type, entity_id),
    ).fetchone()
    return CompactPayloadOut(
        id=row["id"],
        entity_type=row["entity_type"],
        entity_id=row["entity_id"],
        summary=row["summary"],
        byte_size=row["byte_size"],
        truncated=bool(row["truncated"]),
        is_compressed=bool(row["is_compressed"]),
        updated_at=row["updated_at"],
    )


def get_compact_payload(
    conn: sqlite3.Connection,
    *,
    entity_type: str,
    entity_id: str,
    include_full: bool = False,
) -> CompactPayloadOut | None:
    row = conn.execute(
        """
        SELECT id, entity_type, entity_id, summary, payload_storage, byte_size,
               truncated, is_compressed, updated_at
        FROM compact_payloads WHERE entity_type = ? AND entity_id = ?
        """,
        (entity_type, entity_id),
    ).fetchone()
    if row is None:
        return None
    full_payload = None
    if include_full:
        full_payload = _decompress(row["payload_storage"], bool(row["is_compressed"]))
    return CompactPayloadOut(
        id=row["id"],
        entity_type=row["entity_type"],
        entity_id=row["entity_id"],
        summary=row["summary"],
        byte_size=row["byte_size"],
        truncated=bool(row["truncated"]),
        is_compressed=bool(row["is_compressed"]),
        updated_at=row["updated_at"],
        full_payload=full_payload,
    )
