import unittest

from app.option_service import (
    format_strike,
    normalize_right,
    option_collateral_usd,
    option_debit_usd,
    option_display_symbol,
    option_quote_key,
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
