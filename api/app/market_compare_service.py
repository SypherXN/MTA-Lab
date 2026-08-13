"""Compare lane paper equity against a buy-and-hold market benchmark."""

from __future__ import annotations

import sqlite3

from app.lane_service import get_lane, list_lanes
from app.quote_history_service import (
    DEFAULT_BENCHMARK,
    ensure_benchmark_history,
    get_price_as_of,
    get_quote_history,
)
from app.schemas import (
    LaneMarketPointOut,
    LaneVsMarketSeriesOut,
    LanesVsMarketOut,
    MarketPointOut,
)
from app.snapshot_service import get_portfolio_snapshots

BENCHMARK_NAMES = {
    "SPY": "S&P 500 (SPY)",
    "QQQ": "Nasdaq-100 (QQQ)",
    "DIA": "Dow Jones (DIA)",
}


def _pct_change(start: float | None, end: float | None) -> float | None:
    if start is None or end is None or start == 0:
        return None
    return round((end / start - 1.0) * 100.0, 4)


def lane_market_window(
    conn: sqlite3.Connection,
    lane_id: int,
    *,
    since: str | None = None,
    benchmark: str = DEFAULT_BENCHMARK,
) -> tuple[float | None, float | None, float | None]:
    """Return (lane_return_pct, market_return_pct, excess_pct) over the lane snapshot window."""
    rows = get_portfolio_snapshots(conn, lane_id=lane_id, since=since, limit=500)
    if len(rows) < 2:
        return None, None, None
    first = rows[0]
    last = rows[-1]
    lane_pct = _pct_change(float(first["total_equity_usd"]), float(last["total_equity_usd"]))
    start_px = get_price_as_of(conn, benchmark, first["snapshot_at"])
    end_px = get_price_as_of(conn, benchmark, last["snapshot_at"])
    market_pct = _pct_change(start_px, end_px)
    excess = None
    if lane_pct is not None and market_pct is not None:
        excess = round(lane_pct - market_pct, 4)
    return lane_pct, market_pct, excess


def compare_lanes_vs_market(
    conn: sqlite3.Connection,
    *,
    lane_ids: list[int] | None = None,
    since: str | None = None,
    benchmark: str = DEFAULT_BENCHMARK,
    auto_backfill: bool = True,
) -> LanesVsMarketOut:
    symbol = (benchmark or DEFAULT_BENCHMARK).upper().strip()
    if auto_backfill:
        try:
            ensure_benchmark_history(conn, symbols=(symbol,))
        except Exception:
            pass

    if lane_ids:
        lanes = [get_lane(conn, lid) for lid in lane_ids]
    else:
        lanes = [lane for lane in list_lanes(conn) if lane.status == "active"]

    series: list[LaneVsMarketSeriesOut] = []
    window_start: str | None = None
    window_end: str | None = None

    for lane in lanes:
        snapshots = get_portfolio_snapshots(conn, lane_id=lane.id, since=since, limit=500)
        if not snapshots:
            series.append(
                LaneVsMarketSeriesOut(
                    lane_id=lane.id,
                    name=lane.name,
                    points=[],
                )
            )
            continue

        first_eq = float(snapshots[0]["total_equity_usd"])
        last_eq = float(snapshots[-1]["total_equity_usd"])
        first_at = snapshots[0]["snapshot_at"]
        last_at = snapshots[-1]["snapshot_at"]
        first_mkt = get_price_as_of(conn, symbol, first_at)
        last_mkt = get_price_as_of(conn, symbol, last_at)
        lane_pct = _pct_change(first_eq, last_eq)
        market_pct = _pct_change(first_mkt, last_mkt)
        excess = (
            round(lane_pct - market_pct, 4)
            if lane_pct is not None and market_pct is not None
            else None
        )

        points: list[LaneMarketPointOut] = []
        for row in snapshots:
            at = row["snapshot_at"]
            equity = float(row["total_equity_usd"])
            mkt = get_price_as_of(conn, symbol, at)
            point_lane = _pct_change(first_eq, equity)
            point_mkt = _pct_change(first_mkt, mkt)
            point_excess = (
                round(point_lane - point_mkt, 4)
                if point_lane is not None and point_mkt is not None
                else None
            )
            points.append(
                LaneMarketPointOut(
                    at=at,
                    equity_usd=equity,
                    lane_return_pct=point_lane,
                    market_return_pct=point_mkt,
                    excess_pct=point_excess,
                )
            )

        if window_start is None or first_at < window_start:
            window_start = first_at
        if window_end is None or last_at > window_end:
            window_end = last_at

        series.append(
            LaneVsMarketSeriesOut(
                lane_id=lane.id,
                name=lane.name,
                start_equity_usd=first_eq,
                end_equity_usd=last_eq,
                lane_return_pct=lane_pct,
                market_return_pct=market_pct,
                excess_return_pct=excess,
                points=points,
            )
        )

    bench_points: list[MarketPointOut] = []
    if window_start and window_end:
        start_px = get_price_as_of(conn, symbol, window_start)
        history = get_quote_history(conn, symbol, since=window_start, until=window_end)
        seen: set[str] = set()
        for row in history:
            at = row["observed_at"]
            if at in seen:
                continue
            seen.add(at)
            price = float(row["price_usd"])
            bench_points.append(
                MarketPointOut(
                    at=at,
                    price_usd=price,
                    return_pct=_pct_change(start_px, price),
                )
            )
        if not bench_points and start_px:
            end_px = get_price_as_of(conn, symbol, window_end)
            bench_points = [
                MarketPointOut(at=window_start, price_usd=start_px, return_pct=0.0),
            ]
            if end_px is not None:
                bench_points.append(
                    MarketPointOut(
                        at=window_end,
                        price_usd=end_px,
                        return_pct=_pct_change(start_px, end_px),
                    )
                )

    return LanesVsMarketOut(
        benchmark_symbol=symbol,
        benchmark_name=BENCHMARK_NAMES.get(symbol, symbol),
        lanes=series,
        benchmark_points=bench_points,
    )
