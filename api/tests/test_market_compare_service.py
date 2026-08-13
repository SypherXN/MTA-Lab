import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

TEST_DB = Path(tempfile.gettempdir()) / "mta_lab_market_compare_test.db"
os.environ["MTA_DATABASE_PATH"] = str(TEST_DB)
os.environ["MTA_WRITE_API_KEY"] = "test-key"
os.environ["MTA_SKIP_BENCHMARK_BACKFILL"] = "true"

if TEST_DB.exists():
    TEST_DB.unlink()

from app.database import get_connection, init_db  # noqa: E402
from app.lane_compare_service import compare_lanes  # noqa: E402
from app.lane_service import ensure_primary_lane  # noqa: E402
from app.market_compare_service import compare_lanes_vs_market  # noqa: E402
from app.quote_history_service import record_quote_history  # noqa: E402


class MarketCompareServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        conn = get_connection()
        try:
            ensure_primary_lane(conn)
            conn.commit()
        finally:
            conn.close()

    def setUp(self):
        self.conn = get_connection()
        self.conn.execute("DELETE FROM quote_history")
        self.conn.execute("DELETE FROM portfolio_snapshots")
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def _snapshot(self, *, at: str, equity: float, lane_id: int = 1) -> None:
        self.conn.execute(
            """
            INSERT INTO portfolio_snapshots (
                lane_id, snapshot_at, cash_usd, positions_value_usd, total_equity_usd, source
            ) VALUES (?, ?, ?, ?, ?, 'test')
            """,
            (lane_id, at, equity, 0, equity),
        )

    def test_lane_beats_market_over_historical_window(self):
        start = datetime(2026, 7, 10, 14, 0, tzinfo=timezone.utc).isoformat()
        end = datetime(2026, 7, 22, 14, 0, tzinfo=timezone.utc).isoformat()
        self._snapshot(at=start, equity=1000.0)
        self._snapshot(at=end, equity=1100.0)
        record_quote_history(
            self.conn, symbol="SPY", price_usd=500.0, source="test", observed_at=start
        )
        record_quote_history(
            self.conn, symbol="SPY", price_usd=520.0, source="test", observed_at=end
        )
        self.conn.commit()

        compare = compare_lanes(self.conn)
        primary = next(row for row in compare.lanes if row.lane_id == 1)
        self.assertAlmostEqual(primary.equity_change_pct, 10.0, places=3)
        self.assertAlmostEqual(primary.market_return_pct, 4.0, places=3)
        self.assertAlmostEqual(primary.excess_return_pct, 6.0, places=3)

        vs_market = compare_lanes_vs_market(self.conn, auto_backfill=False)
        series = next(row for row in vs_market.lanes if row.lane_id == 1)
        self.assertEqual(len(series.points), 2)
        self.assertAlmostEqual(series.points[0].lane_return_pct or 0, 0.0, places=3)
        self.assertAlmostEqual(series.points[-1].excess_pct or 0, 6.0, places=3)
        self.assertGreaterEqual(len(vs_market.benchmark_points), 2)


if __name__ == "__main__":
    unittest.main()
