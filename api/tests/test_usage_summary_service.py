import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

TEST_DB = Path(tempfile.gettempdir()) / "mta_lab_usage_summary_test.db"
os.environ["MTA_DATABASE_PATH"] = str(TEST_DB)
os.environ["MTA_WRITE_API_KEY"] = "test-key"

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


if __name__ == "__main__":
    unittest.main()
