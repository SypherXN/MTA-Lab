import unittest

from datetime import date

from app.option_service import (
    format_strike,
    next_session_date,
    normalize_right,
    option_collateral_usd,
    option_debit_usd,
    option_display_symbol,
    option_quote_key,
    session_dte,
)


class OptionHelpersTests(unittest.TestCase):
    def test_quote_key_and_display(self):
        self.assertEqual(
            option_quote_key("nvda", "2026-08-21", 180.0, "call"),
            "OPT:NVDA:2026-08-21:180:C",
        )
        self.assertEqual(
            option_display_symbol("nvda", "2026-08-21", 180.5, "put"),
            "NVDA 2026-08-21 180.5P",
        )

    def test_debit_and_collateral(self):
        self.assertAlmostEqual(option_debit_usd(2.5, 1), 250)
        self.assertAlmostEqual(option_collateral_usd(15, 1), 1500)
        self.assertEqual(format_strike(180.0), "180")
        self.assertEqual(normalize_right("C"), "call")
        self.assertEqual(normalize_right("puts"), "put")

    def test_session_dte_skips_weekend(self):
        friday = date(2026, 8, 14)
        self.assertEqual(next_session_date(friday), date(2026, 8, 17))
        self.assertEqual(session_dte("2026-08-14", today=friday), 0)
        self.assertEqual(session_dte("2026-08-17", today=friday), 1)
        self.assertGreater(session_dte("2026-08-21", today=friday), 1)
