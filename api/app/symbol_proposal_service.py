"""Manual ticker scout proposals — review and promote into discovery pool."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from app.lane_service import list_lanes, update_lane
from app.safety import get_active_strategy
from app.schemas import (
    LaneUpdate,
    StrategyRules,
    StrategyUpdate,
    SymbolProposalOut,
    SymbolProposalPromoteRequest,
    SymbolProposalPromoteResponse,
    SymbolProposalsImportRequest,
    SymbolProposalsImportResponse,
)
from app.symbol_discovery_service import validate_discovery_rules


VALID_STATUSES = frozenset({"pending", "promoted", "dismissed"})


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_out(row: sqlite3.Row) -> SymbolProposalOut:
    return SymbolProposalOut(
        id=row["id"],
        symbol=row["symbol"],
        status=row["status"],
        source=row["source"],
        thesis=row["thesis"],
        score=row["score"],
        tags=row["tags"],
        scout_run_id=row["scout_run_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        promoted_at=row["promoted_at"],
    )


def import_symbol_proposals(
    conn: sqlite3.Connection,
    payload: SymbolProposalsImportRequest,
) -> SymbolProposalsImportResponse:
    inserted = 0
    updated = 0
    skipped = 0
    now = _iso_now()
    items: list[SymbolProposalOut] = []

    for item in payload.proposals:
        symbol = item.symbol.strip().upper()
        if not symbol:
            skipped += 1
            continue

        existing = conn.execute(
            """
            SELECT id, status FROM symbol_proposals
            WHERE symbol = ? AND status = 'pending'
            ORDER BY id DESC LIMIT 1
            """,
            (symbol,),
        ).fetchone()

        if existing is not None:
            conn.execute(
                """
                UPDATE symbol_proposals
                SET source = ?, thesis = ?, score = ?, tags = ?,
                    scout_run_id = COALESCE(?, scout_run_id), updated_at = ?
                WHERE id = ?
                """,
                (
                    item.source.strip() or "manual_scout",
                    item.thesis.strip(),
                    item.score,
                    ",".join(t.strip() for t in item.tags if t.strip()) or None,
                    payload.scout_run_id,
                    now,
                    existing["id"],
                ),
            )
            updated += 1
            items.append(_row_to_out(conn.execute(
                "SELECT * FROM symbol_proposals WHERE id = ?",
                (existing["id"],),
            ).fetchone()))
            continue

        already_allowed = False
        strategy = get_active_strategy(conn)
        if symbol in {s.upper() for s in strategy.rules.allowed_symbols}:
            # Still allow proposing for visibility, but mark as skipped if already tradable
            # unless caller wants a fresh thesis — keep as pending for review.
            already_allowed = True

        cursor = conn.execute(
            """
            INSERT INTO symbol_proposals (
                symbol, status, source, thesis, score, tags, scout_run_id, created_at, updated_at
            ) VALUES (?, 'pending', ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                symbol,
                item.source.strip() or "manual_scout",
                item.thesis.strip(),
                item.score,
                ",".join(t.strip() for t in item.tags if t.strip()) or None,
                payload.scout_run_id,
                now,
                now,
            ),
        )
        inserted += 1
        row = conn.execute(
            "SELECT * FROM symbol_proposals WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
        out = _row_to_out(row)
        if already_allowed:
            # Annotate in thesis is enough; still pending so user can promote into discovery_pool
            pass
        items.append(out)

    return SymbolProposalsImportResponse(
        inserted=inserted,
        updated=updated,
        skipped=skipped,
        proposals=items,
    )


def list_symbol_proposals(
    conn: sqlite3.Connection,
    *,
    status: str | None = "pending",
    limit: int = 50,
) -> list[SymbolProposalOut]:
    if status is not None and status not in VALID_STATUSES:
        raise ValueError("status must be pending, promoted, or dismissed")

    clauses: list[str] = []
    params: list[object] = []
    if status is not None:
        clauses.append("status = ?")
        params.append(status)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(min(limit, 200))

    rows = conn.execute(
        f"""
        SELECT * FROM symbol_proposals
        {where}
        ORDER BY COALESCE(score, 0) DESC, id DESC
        LIMIT ?
        """,
        params,
    )
    return [_row_to_out(row) for row in rows]


def dismiss_symbol_proposal(conn: sqlite3.Connection, proposal_id: int) -> SymbolProposalOut:
    row = conn.execute("SELECT * FROM symbol_proposals WHERE id = ?", (proposal_id,)).fetchone()
    if row is None:
        raise ValueError(f"Proposal {proposal_id} not found")
    if row["status"] != "pending":
        raise ValueError(f"Proposal {proposal_id} is {row['status']}, not pending")

    now = _iso_now()
    conn.execute(
        "UPDATE symbol_proposals SET status = 'dismissed', updated_at = ? WHERE id = ?",
        (now, proposal_id),
    )
    return _row_to_out(
        conn.execute("SELECT * FROM symbol_proposals WHERE id = ?", (proposal_id,)).fetchone()
    )


def promote_symbol_proposals(
    conn: sqlite3.Connection,
    payload: SymbolProposalPromoteRequest,
) -> SymbolProposalPromoteResponse:
    strategy = get_active_strategy(conn)
    rules = strategy.rules.model_copy(deep=True)

    symbols: list[str] = []
    proposal_ids = list(payload.proposal_ids or [])

    if proposal_ids:
        placeholders = ",".join("?" * len(proposal_ids))
        rows = conn.execute(
            f"""
            SELECT * FROM symbol_proposals
            WHERE id IN ({placeholders}) AND status = 'pending'
            """,
            proposal_ids,
        ).fetchall()
        if len(rows) != len(set(proposal_ids)):
            found = {int(r["id"]) for r in rows}
            missing = [i for i in proposal_ids if i not in found]
            raise ValueError(f"Pending proposals not found: {missing}")
        symbols = [r["symbol"].upper() for r in rows]
    elif payload.symbols:
        symbols = [s.strip().upper() for s in payload.symbols if s.strip()]
        if not symbols:
            raise ValueError("No symbols to promote")
        # Ensure pending rows exist or create lightweight ones
        for symbol in symbols:
            existing = conn.execute(
                """
                SELECT id FROM symbol_proposals
                WHERE symbol = ? AND status = 'pending'
                ORDER BY id DESC LIMIT 1
                """,
                (symbol,),
            ).fetchone()
            if existing is None:
                now = _iso_now()
                cursor = conn.execute(
                    """
                    INSERT INTO symbol_proposals (
                        symbol, status, source, thesis, created_at, updated_at
                    ) VALUES (?, 'pending', 'manual_promote', 'Promoted without prior scout row.', ?, ?)
                    """,
                    (symbol, now, now),
                )
                proposal_ids.append(int(cursor.lastrowid))
            else:
                proposal_ids.append(int(existing["id"]))
    else:
        raise ValueError("Provide proposal_ids or symbols")

    allowed = list(rules.allowed_symbols)
    pool = list(rules.discovery_pool)
    allowed_set = {s.upper() for s in allowed}
    pool_set = {s.upper() for s in pool}
    watchset = {s.upper() for s in (rules.watchlist or rules.allowed_symbols)}

    added_allowed: list[str] = []
    added_pool: list[str] = []
    for symbol in symbols:
        if symbol not in allowed_set:
            allowed.append(symbol)
            allowed_set.add(symbol)
            added_allowed.append(symbol)
        if symbol not in pool_set and symbol not in watchset:
            pool.append(symbol)
            pool_set.add(symbol)
            added_pool.append(symbol)

    new_rules = StrategyRules(
        allowed_symbols=allowed,
        max_order_usd=rules.max_order_usd,
        max_daily_trades=rules.max_daily_trades,
        max_daily_notional_usd=rules.max_daily_notional_usd,
        require_review_before_place=rules.require_review_before_place,
        watchlist=list(rules.watchlist or rules.allowed_symbols),
        symbol_cooldown_hours=rules.symbol_cooldown_hours,
        symbol_discovery_enabled=True if payload.enable_discovery else rules.symbol_discovery_enabled,
        discovery_max_per_run=(
            payload.discovery_max_per_run
            if payload.discovery_max_per_run is not None
            else (
                max(rules.discovery_max_per_run, 2)
                if payload.enable_discovery and rules.discovery_max_per_run < 1
                else rules.discovery_max_per_run
            )
        ),
        discovery_pool=pool,
    )
    validate_discovery_rules(new_rules)

    from app.services import update_active_strategy

    updated_strategy = update_active_strategy(
        conn,
        StrategyUpdate(rules=new_rules),
    )

    lanes_updated = 0
    if payload.update_lanes:
        for lane in list_lanes(conn, include_archived=False):
            if lane.strategy_version != updated_strategy.version:
                update_lane(
                    conn,
                    lane.id,
                    LaneUpdate(strategy_version=updated_strategy.version),
                )
                lanes_updated += 1

    now = _iso_now()
    promoted_rows: list[SymbolProposalOut] = []
    if proposal_ids:
        placeholders = ",".join("?" * len(proposal_ids))
        conn.execute(
            f"""
            UPDATE symbol_proposals
            SET status = 'promoted', promoted_at = ?, updated_at = ?
            WHERE id IN ({placeholders})
            """,
            (now, now, *proposal_ids),
        )
        for row in conn.execute(
            f"SELECT * FROM symbol_proposals WHERE id IN ({placeholders})",
            proposal_ids,
        ):
            promoted_rows.append(_row_to_out(row))

    return SymbolProposalPromoteResponse(
        strategy_version=updated_strategy.version,
        added_to_allowed=added_allowed,
        added_to_discovery_pool=added_pool,
        lanes_updated=lanes_updated,
        promoted=promoted_rows,
        message=(
            f"Promoted {len(symbols)} symbol(s) into strategy {updated_strategy.version}. "
            f"Discovery enabled={updated_strategy.rules.symbol_discovery_enabled}."
        ),
    )
