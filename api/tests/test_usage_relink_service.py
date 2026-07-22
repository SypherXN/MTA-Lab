import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

TEST_DB = Path(tempfile.gettempdir()) / "mta_lab_relink_test.db"
os.environ["MTA_DATABASE_PATH"] = str(TEST_DB)
os.environ["MTA_WRITE_API_KEY"] = "test-key"

if TEST_DB.exists():
    TEST_DB.unlink()

from app.database import get_connection, init_db  # noqa: E402
from app.lane_service import ensure_primary_lane  # noqa: E402
from app.usage_relink_service import relink_cursor_usage  # noqa: E402


class UsageRelinkServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        conn = get_connection()
        try:
            ensure_primary_lane(conn)
            conn.execute(
                """
                INSERT OR IGNORE INTO simulation_lanes (
                    id, name, strategy_version, plan_version, lane_role, status,
                    initial_cash_usd, created_at, updated_at
                ) VALUES (4, 'ticker-explorer', 'v2', 'v4', 'research', 'active', 1000, datetime('now'), datetime('now'))
                """
            )
            conn.commit()
        finally:
            conn.close()

    def setUp(self):
        self.conn = get_connection()
        self.conn.execute("DELETE FROM cursor_usage")
        self.conn.execute("DELETE FROM automation_runs")
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def _insert_explorer_run(self, *, run_at: datetime, cursor_run_id: str | None = None) -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO automation_runs (
                run_at, automation_name, run_type, status, strategy_version, plan_version,
                mode, lane_id, cursor_run_id
            ) VALUES (?, 'mta-explorer', 'daily_research', 'completed', 'v2', 'v4', 'research', 4, ?)
            """,
            (run_at.isoformat(), cursor_run_id),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def test_fuzzy_links_explorer_usage_by_time(self):
        run_at = datetime(2026, 7, 22, 10, 32, tzinfo=timezone.utc)
        run_id = self._insert_explorer_run(run_at=run_at)
        usage_at = (run_at + timedelta(minutes=3)).isoformat()
        self.conn.execute(
            """
            INSERT INTO cursor_usage (
                cursor_run_id, model, cost_usd, estimated_cost_usd, reconciled_at, source
            ) VALUES ('bc-explorer-test', 'composer-2.5', 0, 0.12, ?, 'test')
            """,
            (usage_at,),
        )
        self.conn.commit()

        result = relink_cursor_usage(self.conn, create_scout_runs=False)

        row = self.conn.execute(
            "SELECT run_id FROM cursor_usage WHERE cursor_run_id = 'bc-explorer-test'"
        ).fetchone()
        run = self.conn.execute(
            "SELECT cursor_run_id FROM automation_runs WHERE id = ?",
            (run_id,),
        ).fetchone()
        self.assertEqual(int(row["run_id"]), run_id)
        self.assertEqual(run["cursor_run_id"], "bc-explorer-test")
        self.assertGreaterEqual(result.fuzzy_usage_linked, 1)

    def test_exact_relink_after_run_backfill(self):
        run_id = self._insert_explorer_run(
            run_at=datetime(2026, 7, 21, 10, 30, tzinfo=timezone.utc),
            cursor_run_id="bc-known",
        )
        self.conn.execute(
            """
            INSERT INTO cursor_usage (
                run_id, cursor_run_id, model, cost_usd, estimated_cost_usd, reconciled_at, source
            ) VALUES (?, 'bc-known', 'composer-2.5', 0, 0.05, ?, 'test')
            """,
            (run_id, datetime(2026, 7, 21, 10, 31, tzinfo=timezone.utc).isoformat()),
        )
        self.conn.execute(
            """
            INSERT INTO cursor_usage (
                cursor_run_id, model, cost_usd, estimated_cost_usd, reconciled_at, source
            ) VALUES ('bc-known', 'composer-2.5', 0, 0.03, ?, 'test')
            """,
            (datetime(2026, 7, 21, 10, 32, tzinfo=timezone.utc).isoformat(),),
        )
        self.conn.commit()

        result = relink_cursor_usage(self.conn, create_scout_runs=False)
        unlinked = self.conn.execute(
            "SELECT COUNT(*) AS c FROM cursor_usage WHERE run_id IS NULL"
        ).fetchone()["c"]
        self.assertEqual(int(unlinked), 0)
        self.assertGreaterEqual(result.exact_usage_linked, 1)


if __name__ == "__main__":
    unittest.main()
