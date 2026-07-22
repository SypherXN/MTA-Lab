import unittest

from app.cursor_pricing import (
    build_usage_import_key,
    effective_cost_usd,
    estimate_token_cost_usd,
    get_model_rates,
)


class CursorPricingTests(unittest.TestCase):
    def test_estimate_composer_cost(self):
        cost = estimate_token_cost_usd("composer-2.5", 343_421, 7_668)
        self.assertIsNotNone(cost)
        assert cost is not None
        self.assertGreater(cost, 0)
        # 343421 * 0.25/1e6 + 7668 * 1.00/1e6
        self.assertAlmostEqual(cost, 0.093523, places=5)

    def test_effective_cost_prefers_billed(self):
        self.assertEqual(effective_cost_usd(0.12, 0.50), 0.12)
        self.assertEqual(effective_cost_usd(0.0, 0.50), 0.50)
        self.assertEqual(effective_cost_usd(None, None), 0.0)

    def test_build_usage_import_key_for_cloud_row(self):
        key = build_usage_import_key(
            cursor_run_id="bc-abc",
            timestamp="2026-07-22T14:05:00.902Z",
            model="composer-2.5",
            input_tokens=1,
            output_tokens=2,
            cost_usd=0.0,
        )
        self.assertEqual(key, "cloud:bc-abc|2026-07-22T14:05:00.902Z")

    def test_unknown_model_uses_default_rates(self):
        rates = get_model_rates("some-unknown-model")
        self.assertEqual(rates.input_usd_per_million, 0.30)


if __name__ == "__main__":
    unittest.main()
