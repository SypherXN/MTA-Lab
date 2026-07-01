import hashlib
import json
from datetime import datetime, timezone

import sqlite3

from app.config import settings
from app.schemas import (
    AgentPlanOut,
    AgentPlanPayload,
    AgentPlanSummaryOut,
    AgentPlanUpdate,
    AgentPlanUpdateResponse,
)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_plan_json(payload: AgentPlanPayload) -> str:
    return json.dumps(payload.model_dump(), separators=(",", ":"), sort_keys=True)


def plan_content_hash(plan_json: str) -> str:
    return hashlib.sha256(plan_json.encode("utf-8")).hexdigest()


def _store_plan_content(conn: sqlite3.Connection, plan_json: str) -> str:
    content_hash = plan_content_hash(plan_json)
    conn.execute(
        """
        INSERT OR IGNORE INTO agent_plan_contents (content_hash, plan_json, byte_size)
        VALUES (?, ?, ?)
        """,
        (content_hash, plan_json, len(plan_json.encode("utf-8"))),
    )
    return content_hash


def _load_plan_json(conn: sqlite3.Connection, row: sqlite3.Row) -> str:
    if row["content_hash"]:
        content = conn.execute(
            "SELECT plan_json FROM agent_plan_contents WHERE content_hash = ?",
            (row["content_hash"],),
        ).fetchone()
        if content is not None:
            return content["plan_json"]
    return row["plan_json"]


def _row_to_plan_out(conn: sqlite3.Connection, row: sqlite3.Row) -> AgentPlanOut:
    payload = AgentPlanPayload.model_validate(json.loads(_load_plan_json(conn, row)))
    return AgentPlanOut(
        version=row["version"],
        name=row["name"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        change_source=row["change_source"],
        content_hash=row["content_hash"],
        **payload.model_dump(),
    )


def _next_plan_version(current: str) -> str:
    if len(current) >= 2 and current[0] == "v" and current[1:].isdigit():
        return f"v{int(current[1:]) + 1}"
    return f"{current}.1"


def _prune_plan_history(conn: sqlite3.Connection) -> None:
    keep = settings.plan_history_keep
    stale = conn.execute(
        """
        SELECT id FROM agent_plans
        WHERE is_active = 0
        ORDER BY id DESC
        LIMIT -1 OFFSET ?
        """,
        (keep,),
    ).fetchall()
    if not stale:
        return

    stale_ids = [row["id"] for row in stale]
    placeholders = ",".join("?" * len(stale_ids))
    conn.execute(f"DELETE FROM agent_plans WHERE id IN ({placeholders})", stale_ids)

    conn.execute(
        """
        DELETE FROM agent_plan_contents
        WHERE content_hash NOT IN (
            SELECT content_hash FROM agent_plans WHERE content_hash IS NOT NULL
        )
        """
    )


def get_active_agent_plan(conn: sqlite3.Connection) -> AgentPlanOut:
    row = conn.execute(
        """
        SELECT version, name, plan_json, content_hash, change_source, created_at, updated_at
        FROM agent_plans
        WHERE is_active = 1
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()
    if row is None:
        raise RuntimeError("No active agent plan configured")
    return _row_to_plan_out(conn, row)


def get_active_plan_version(conn: sqlite3.Connection) -> str | None:
    row = conn.execute(
        "SELECT version FROM agent_plans WHERE is_active = 1 ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return row["version"] if row else None


def list_agent_plan_versions(conn: sqlite3.Connection, limit: int = 50) -> list[AgentPlanSummaryOut]:
    rows = conn.execute(
        """
        SELECT version, name, is_active, change_source, content_hash, created_at, updated_at
        FROM agent_plans
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [
        AgentPlanSummaryOut(
            version=row["version"],
            name=row["name"],
            is_active=bool(row["is_active"]),
            change_source=row["change_source"],
            content_hash=row["content_hash"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]


def get_agent_plan_by_version(conn: sqlite3.Connection, version: str) -> AgentPlanOut:
    row = conn.execute(
        """
        SELECT version, name, plan_json, content_hash, change_source, created_at, updated_at
        FROM agent_plans
        WHERE version = ?
        """,
        (version,),
    ).fetchone()
    if row is None:
        raise ValueError(f"Agent plan {version} not found")
    return _row_to_plan_out(conn, row)


def update_active_agent_plan(
    conn: sqlite3.Connection,
    payload: AgentPlanUpdate,
) -> AgentPlanUpdateResponse:
    active = conn.execute(
        """
        SELECT id, version, name, plan_json, content_hash, change_source, created_at, updated_at
        FROM agent_plans
        WHERE is_active = 1
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()
    if active is None:
        raise RuntimeError("No active agent plan configured")

    current_payload = AgentPlanPayload.model_validate(json.loads(_load_plan_json(conn, active)))
    if payload.plan is not None:
        current_payload = payload.plan

    name = payload.name if payload.name is not None else active["name"]
    plan_json = canonical_plan_json(current_payload)
    content_hash = _store_plan_content(conn, plan_json)

    if content_hash == active["content_hash"] and name == active["name"]:
        plan = _row_to_plan_out(conn, active)
        return AgentPlanUpdateResponse(
            plan=plan,
            unchanged=True,
            previous_version=active["version"],
            message="Plan content unchanged; no new version created.",
        )

    previous_version = active["version"]
    new_version = _next_plan_version(previous_version)
    now = _iso_now()

    conn.execute("UPDATE agent_plans SET is_active = 0, updated_at = ? WHERE is_active = 1", (now,))
    conn.execute(
        """
        INSERT INTO agent_plans (
            version, name, plan_json, content_hash, change_source, is_active, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, 1, ?, ?)
        """,
        (
            new_version,
            name,
            plan_json,
            content_hash,
            payload.change_source.strip() or "api",
            now,
            now,
        ),
    )

    _prune_plan_history(conn)
    plan = get_agent_plan_by_version(conn, new_version)
    return AgentPlanUpdateResponse(
        plan=plan,
        unchanged=False,
        previous_version=previous_version,
        message=f"Agent plan updated from {previous_version} to {new_version}.",
    )


def seed_plan_content(conn: sqlite3.Connection, plan_json: str) -> str:
    return _store_plan_content(conn, plan_json)


def upsert_agent_plan_version(
    conn: sqlite3.Connection,
    *,
    version: str,
    name: str,
    payload: AgentPlanPayload,
    change_source: str = "github",
    make_active: bool = False,
) -> tuple[AgentPlanOut, bool]:
    """Insert or update a plan pinned to version. Returns (plan, changed)."""
    plan_json = canonical_plan_json(payload)
    content_hash = _store_plan_content(conn, plan_json)
    existing = conn.execute(
        "SELECT version, name, content_hash FROM agent_plans WHERE version = ?",
        (version,),
    ).fetchone()
    now = _iso_now()

    if existing is not None:
        if existing["content_hash"] == content_hash and existing["name"] == name:
            row = conn.execute(
                """
                SELECT version, name, plan_json, content_hash, change_source, created_at, updated_at
                FROM agent_plans WHERE version = ?
                """,
                (version,),
            ).fetchone()
            return _row_to_plan_out(conn, row), False

        conn.execute(
            """
            UPDATE agent_plans
            SET name = ?, plan_json = ?, content_hash = ?, change_source = ?, updated_at = ?
            WHERE version = ?
            """,
            (name, plan_json, content_hash, change_source.strip() or "github", now, version),
        )
        return get_agent_plan_by_version(conn, version), True

    if make_active:
        conn.execute("UPDATE agent_plans SET is_active = 0, updated_at = ?", (now,))

    conn.execute(
        """
        INSERT INTO agent_plans (
            version, name, plan_json, content_hash, change_source, is_active, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            version,
            name,
            plan_json,
            content_hash,
            change_source.strip() or "github",
            1 if make_active else 0,
            now,
            now,
        ),
    )
    return get_agent_plan_by_version(conn, version), True


def _load_plan_file(path) -> tuple[str, str, AgentPlanPayload, bool, str]:
    import json
    from pathlib import Path

    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    version = str(raw.get("version") or Path(path).stem).strip()
    if not version:
        raise ValueError(f"{path.name}: missing version")
    name = str(raw.get("name") or version).strip()
    make_active = bool(raw.get("is_active", False))
    change_source = str(raw.get("change_source") or "github").strip() or "github"

    payload_data = raw.get("plan")
    if payload_data is None:
        payload_data = {
            key: raw[key]
            for key in ("run_order", "required_inputs", "scoring_rules", "data_sources", "stop_conditions")
            if key in raw
        }
    payload = AgentPlanPayload.model_validate(payload_data)
    return version, name, payload, make_active, change_source


def sync_agent_plans_from_directory(conn: sqlite3.Connection, directory):
    from app.schemas import AgentPlanSyncItemOut, AgentPlanSyncResponse
    from pathlib import Path

    root = Path(directory)
    if not root.is_dir():
        raise FileNotFoundError(f"Plans directory not found: {root}")

    imported = 0
    updated = 0
    unchanged = 0
    errors: list[str] = []
    items: list[AgentPlanSyncItemOut] = []

    for path in sorted(root.glob("*.json")):
        try:
            version, name, payload, make_active, change_source = _load_plan_file(path)
            existed = (
                conn.execute("SELECT 1 FROM agent_plans WHERE version = ?", (version,)).fetchone() is not None
            )
            _, changed = upsert_agent_plan_version(
                conn,
                version=version,
                name=name,
                payload=payload,
                change_source=change_source,
                make_active=make_active,
            )
            if changed:
                if existed:
                    updated += 1
                    status = "updated"
                else:
                    imported += 1
                    status = "imported"
                items.append(
                    AgentPlanSyncItemOut(
                        version=version,
                        name=name,
                        status=status,
                        message=f"Synced from {path.name}",
                    )
                )
            else:
                unchanged += 1
                items.append(
                    AgentPlanSyncItemOut(
                        version=version,
                        name=name,
                        status="unchanged",
                        message=f"No changes in {path.name}",
                    )
                )
        except Exception as exc:
            errors.append(f"{path.name}: {exc}")

    return AgentPlanSyncResponse(
        imported=imported,
        updated=updated,
        unchanged=unchanged,
        errors=errors,
        items=items,
    )
