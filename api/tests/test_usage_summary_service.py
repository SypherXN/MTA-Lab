import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

TEST_DB = Path(tempfile.gettempdir()) / "mta_lab_usage_summary_test.db"
os.environ["MTA_DATABASE_PATH"] = str(TEST_DB)
os.environ["MTA_WRITE_API_KEY"] = "test-key"
os.environ["MTA_SKIP_BENCHMARK_BACKFILL"] = "true"

if TEST_DB.exists():
    TEST_DB.unlink()

from app.database import get_connection, init_db  # noqa: E402
from app.usage_summary_service import get_usage_summary  # noqa: E402


class UsageSummaryServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        self.conn = get_connection()
        self.conn.execute("DELETE FROM cursor_usage")
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def _insert_usage(self, *, cost: float, days_ago: int) -> None:
        ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
        self.conn.execute(
            """
            INSERT INTO cursor_usage (
                model, cost_usd, estimated_cost_usd, reconciled_at, source
            ) VALUES ('composer-2.5', ?, 0, ?, 'test')
            """,
            (cost, ts),
        )
        self.conn.commit()

    def test_period_totals_and_projections(self):
        self._insert_usage(cost=1.0, days_ago=1)
        self._insert_usage(cost=2.0, days_ago=2)
        self._insert_usage(cost=3.0, days_ago=20)

        summary = get_usage_summary(self.conn)

        self.assertAlmostEqual(summary.last_7_days.cost_usd, 3.0)
        self.assertEqual(summary.last_7_days.row_count, 2)
        self.assertAlmostEqual(summary.last_30_days.cost_usd, 6.0)
        self.assertIsNotNone(summary.projections)
        assert summary.projections is not None
        self.assertAlmostEqual(summary.projections.avg_daily_usd, 1.5)
        self.assertAlmostEqual(summary.projections.projected_weekly_usd, 10.5)
        self.assertGreater(summary.projections.projected_monthly_usd, 0)
        self.assertIsInstance(summary.by_lane, list)

    def test_usage_day_detail_groups_lane_and_model(self):
        day = "2026-08-15"
        self.conn.execute(
            """
            INSERT INTO cursor_usage (
                run_id, model, cost_usd, estimated_cost_usd, reconciled_at, source
            ) VALUES (NULL, 'cursor-grok-4.6-high', 0, 0.40, ?, 'test')
            """,
            (f"{day}T12:00:00+00:00",),
        )
        self.conn.execute(
            """
            INSERT INTO cursor_usage (
                run_id, model, cost_usd, estimated_cost_usd, reconciled_at, source
            ) VALUES (NULL, 'composer-2.5', 0, 0.10, ?, 'test')
            """,
            (f"{day}T13:00:00+00:00",),
        )
        self.conn.commit()

        from app.usage_summary_service import get_usage_day_detail

        detail = get_usage_day_detail(self.conn, day)
        self.assertEqual(detail.day, day)
        self.assertAlmostEqual(detail.cost_usd, 0.50)
        self.assertEqual(detail.row_count, 2)
        models = {row.key: row.cost_usd for row in detail.by_model}
        self.assertAlmostEqual(models["cursor-grok-4.6-high"], 0.40)
        self.assertAlmostEqual(models["composer-2.5"], 0.10)
        self.assertEqual(detail.by_lane[0].key, "unlinked")
        empty = get_usage_day_detail(self.conn, "2026-01-01")
        self.assertEqual(empty.row_count, 0)
        with self.assertRaises(ValueError):
            get_usage_day_detail(self.conn, "15-08-2026")


if __name__ == "__main__":
    unittest.main()
