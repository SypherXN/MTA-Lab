import csv
import io
import tempfile
import unittest
from pathlib import Path

from app.cursor_usage_csv import (
    is_automation_row,
    is_usage_events_format,
    load_cursor_usage_csv,
    parse_cost_usd,
    parse_usage_row,
)

USAGE_EVENTS_SAMPLE = """Date,Cloud Agent ID,Automation ID,Kind,Model,Max Mode,Input (w/ Cache Write),Input (w/o Cache Write),Cache Read,Output Tokens,Total Tokens,Cost
"2026-07-22T14:05:00.902Z","bc-c169401d-0cbc-458d-83c1-da5904854765","a417d0c5-7caa-11f1-ba66-0e7d0216e441","Included","composer-2.5","Yes","0","80414","263007","7668","351089","Included"
"2026-07-22T20:24:14.529Z","","","Included","composer-2.5","No","0","2855","300520","2496","305871","Included"
"2026-07-13T22:11:01.046Z","","","Errored, No Charge","composer-2.5","No","","","","","","Free"
"2026-07-10T23:34:52.000Z","bc-legacy-1","","","","composer-2.5","","","","","1200","500","0.12"
"""

LEGACY_SAMPLE = """timestamp,model,cost,input_tokens,output_tokens,run_id
2026-07-10T12:00:00Z,composer-2.5,0.08,1000,200,bc-legacy-ide
"""


class CursorUsageCsvTests(unittest.TestCase):
    def test_detect_usage_events_format(self):
        reader = csv.DictReader(io.StringIO(USAGE_EVENTS_SAMPLE))
        self.assertTrue(is_usage_events_format(reader.fieldnames))

    def test_is_automation_row(self):
        reader = csv.DictReader(io.StringIO(USAGE_EVENTS_SAMPLE))
        rows = list(reader)
        self.assertTrue(is_automation_row(rows[0]))
        self.assertFalse(is_automation_row(rows[1]))
        self.assertFalse(is_automation_row(rows[2]))

    def test_parse_included_cost_as_zero(self):
        self.assertEqual(parse_cost_usd("Included"), 0.0)
        self.assertEqual(parse_cost_usd("Free"), 0.0)
        self.assertEqual(parse_cost_usd("0.12"), 0.12)

    def test_parse_automation_usage_row(self):
        reader = csv.DictReader(io.StringIO(USAGE_EVENTS_SAMPLE))
        row = next(reader)
        parsed = parse_usage_row(row, usage_events_format=True)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["cursor_run_id"], "bc-c169401d-0cbc-458d-83c1-da5904854765")
        self.assertEqual(parsed["model"], "composer-2.5")
        self.assertEqual(parsed["cost_usd"], 0.0)
        self.assertEqual(parsed["input_tokens"], 343421)
        self.assertEqual(parsed["output_tokens"], 7668)
        self.assertEqual(parsed["timestamp"], "2026-07-22T14:05:00.902Z")

    def test_load_automations_only_filters_ide_rows(self):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".csv", delete=False) as handle:
            handle.write(USAGE_EVENTS_SAMPLE)
            path = Path(handle.name)
        try:
            rows = load_cursor_usage_csv(path, automations_only=True)
            self.assertEqual(len(rows), 2)
            self.assertTrue(all(row["cursor_run_id"] for row in rows))
        finally:
            path.unlink()

    def test_load_all_rows_legacy_format(self):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".csv", delete=False) as handle:
            handle.write(LEGACY_SAMPLE)
            path = Path(handle.name)
        try:
            rows = load_cursor_usage_csv(path, automations_only=True)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["cost_usd"], 0.08)
            self.assertEqual(rows[0]["cursor_run_id"], "bc-legacy-ide")
        finally:
            path.unlink()


if __name__ == "__main__":
    unittest.main()
