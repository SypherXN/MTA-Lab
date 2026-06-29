import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

TEST_DB = Path(tempfile.gettempdir()) / "mta_lab_test.db"
os.environ["MTA_DATABASE_PATH"] = str(TEST_DB)
os.environ["MTA_WRITE_API_KEY"] = "test-key"
os.environ["MTA_RATE_LIMIT_ENABLED"] = "false"

if TEST_DB.exists():
    TEST_DB.unlink()

from app.database import init_db  # noqa: E402
from app.main import app  # noqa: E402

init_db()
client = TestClient(app)


class ApiTests(unittest.TestCase):
    def test_health(self):
        response = client.get("/health")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["database"], "ok")

    def test_context_research_mode(self):
        response = client.get("/api/automation/context")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["strategy"]["mode"], "research")
        self.assertFalse(body["strategy"]["trading_enabled"])
        self.assertFalse(body["safety"]["trading_allowed"])
        self.assertIn("daily_trades_used", body["safety"])
        self.assertIn("daily_trades_remaining", body["safety"])
        self.assertIn("allowed_actions", body["safety"])
        self.assertIn("simulated_buy", body["safety"]["allowed_actions"])
        self.assertNotIn("buy", body["safety"]["allowed_actions"])

    def test_agent_plan_endpoint(self):
        response = client.get("/api/automation/plan")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["version"], "v1")
        self.assertEqual(body["name"], "Default Research Agent Plan")
        self.assertEqual(body["change_source"], "seed")
        self.assertIsNotNone(body["content_hash"])
        self.assertGreater(len(body["run_order"]), 0)
        self.assertGreater(len(body["required_inputs"]), 0)
        self.assertGreater(len(body["scoring_rules"]), 0)
        self.assertGreater(len(body["data_sources"]), 0)
        self.assertGreater(len(body["stop_conditions"]), 0)
        first_step = body["run_order"][0]
        self.assertEqual(first_step["action"], "fetch_plan")
        self.assertIn("fetch_context", [s["action"] for s in body["run_order"]])
        self.assertTrue(any(r["id"] == "respect_safety" for r in body["scoring_rules"]))
        self.assertTrue(any(s["condition"] == "context_or_plan_unavailable" for s in body["stop_conditions"]))

    def test_context_safety_budget_after_trade(self):
        payload = {
            "cursor_run_id": "budget-test-1",
            "decisions": [
                {
                    "symbol": "SPY",
                    "action": "simulated_buy",
                    "reason": "Test budget tracking.",
                    "amount_usd": 250,
                    "fill_price": 500,
                }
            ],
        }
        client.post(
            "/api/automation/runs",
            json=payload,
            headers={"X-API-Key": "test-key"},
        )
        context = client.get("/api/automation/context").json()
        self.assertEqual(context["safety"]["daily_trades_used"], 1)
        self.assertEqual(context["safety"]["daily_notional_used"], 250)
        self.assertEqual(context["safety"]["daily_trades_remaining"], 2)

    def test_idempotent_run_by_cursor_run_id(self):
        payload = {
            "cursor_run_id": "idem-test-1",
            "market_summary": "First submission.",
            "decisions": [
                {"symbol": "SPY", "action": "hold", "reason": "No action."},
            ],
        }
        first = client.post(
            "/api/automation/runs",
            json=payload,
            headers={"X-API-Key": "test-key"},
        )
        second = client.post(
            "/api/automation/runs",
            json={**payload, "market_summary": "Duplicate submission."},
            headers={"X-API-Key": "test-key"},
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertFalse(first.json()["duplicate"])
        self.assertTrue(second.json()["duplicate"])
        self.assertEqual(first.json()["run_id"], second.json()["run_id"])

    def test_get_run_by_id(self):
        create = client.post(
            "/api/automation/runs",
            json={
                "cursor_run_id": "detail-test-1",
                "market_summary": "Detail check.",
                "decisions": [
                    {"symbol": "QQQ", "action": "skip", "reason": "No signal."},
                ],
            },
            headers={"X-API-Key": "test-key"},
        )
        run_id = create.json()["run_id"]
        detail = client.get(f"/api/automation/runs/{run_id}")
        self.assertEqual(detail.status_code, 200)
        body = detail.json()
        self.assertEqual(body["id"], run_id)
        self.assertEqual(body["market_summary"], "Detail check.")
        self.assertEqual(len(body["decisions"]), 1)
        self.assertEqual(body["decisions"][0]["symbol"], "QQQ")

    def test_get_run_not_found(self):
        response = client.get("/api/automation/runs/999999")
        self.assertEqual(response.status_code, 404)

    def test_transaction_rolls_back_on_simulated_trade_failure(self):
        runs_before = client.get("/api/dashboard/stats").json()["total_runs"]
        response = client.post(
            "/api/automation/runs",
            json={
                "cursor_run_id": "rollback-test-1",
                "decisions": [
                    {
                        "symbol": "SPY",
                        "action": "simulated_buy",
                        "reason": "Too large for paper cash.",
                        "amount_usd": 50000,
                        "fill_price": 500,
                    }
                ],
            },
            headers={"X-API-Key": "test-key"},
        )
        self.assertEqual(response.status_code, 400)
        runs_after = client.get("/api/dashboard/stats").json()["total_runs"]
        self.assertEqual(runs_before, runs_after)

    def test_simulated_trade_blocked_on_rule_violation(self):
        response = client.post(
            "/api/automation/runs",
            json={
                "cursor_run_id": "sim-block-test-1",
                "decisions": [
                    {
                        "symbol": "SPY",
                        "action": "simulated_buy",
                        "reason": "Exceeds per-order cap.",
                        "amount_usd": 9999,
                        "fill_price": 500,
                    }
                ],
            },
            headers={"X-API-Key": "test-key"},
        )
        self.assertEqual(response.status_code, 400)

    def test_failed_run_logged(self):
        response = client.post(
            "/api/automation/runs",
            json={
                "cursor_run_id": "failed-run-1",
                "status": "failed",
                "errors": ["Robinhood MCP: connection timeout"],
                "market_summary": "Run aborted before analysis.",
            },
            headers={"X-API-Key": "test-key"},
        )
        self.assertEqual(response.status_code, 200)
        run_id = response.json()["run_id"]
        detail = client.get(f"/api/automation/runs/{run_id}").json()
        self.assertEqual(detail["status"], "failed")
        self.assertEqual(detail["errors"], ["Robinhood MCP: connection timeout"])
        self.assertEqual(len(detail["decisions"]), 0)

    def test_failed_run_requires_errors(self):
        response = client.post(
            "/api/automation/runs",
            json={"status": "failed", "cursor_run_id": "failed-run-2"},
            headers={"X-API-Key": "test-key"},
        )
        self.assertEqual(response.status_code, 400)

    def test_failed_run_rejects_trade_decisions(self):
        response = client.post(
            "/api/automation/runs",
            json={
                "status": "failed",
                "errors": ["Context fetch failed"],
                "decisions": [
                    {"symbol": "SPY", "action": "simulated_buy", "reason": "n/a", "amount_usd": 100},
                ],
            },
            headers={"X-API-Key": "test-key"},
        )
        self.assertEqual(response.status_code, 400)

    def test_portfolio_reset(self):
        client.post(
            "/api/automation/runs",
            json={
                "cursor_run_id": "reset-prep-1",
                "decisions": [
                    {
                        "symbol": "SPY",
                        "action": "simulated_buy",
                        "reason": "Setup position before reset.",
                        "amount_usd": 100,
                        "fill_price": 500,
                    }
                ],
            },
            headers={"X-API-Key": "test-key"},
        )
        response = client.post(
            "/api/admin/portfolio/reset",
            headers={"X-API-Key": "test-key"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["cash_usd"], 10000.0)
        portfolio = client.get("/api/dashboard/portfolio").json()
        self.assertEqual(portfolio["cash_usd"], 10000.0)
        self.assertEqual(len(portfolio["positions"]), 0)

    def test_strategy_version_bump_on_material_change(self):
        before = client.get("/api/automation/context").json()["strategy"]["version"]
        response = client.patch(
            "/api/automation/strategy",
            json={"rules": {"max_order_usd": 400, "max_daily_trades": 3, "max_daily_notional_usd": 1500,
                           "require_review_before_place": True,
                           "allowed_symbols": ["SPY", "QQQ"], "watchlist": ["SPY", "QQQ"]}},
            headers={"X-API-Key": "test-key"},
        )
        self.assertEqual(response.status_code, 200)
        after = response.json()["version"]
        self.assertNotEqual(before, after)

    def test_deactivate_manual_note(self):
        create = client.post(
            "/api/automation/notes",
            json={"content": "Temporary note to deactivate."},
            headers={"X-API-Key": "test-key"},
        )
        note_id = create.json()["id"]
        deactivate = client.patch(
            f"/api/automation/notes/{note_id}",
            json={"active": False},
            headers={"X-API-Key": "test-key"},
        )
        self.assertEqual(deactivate.status_code, 200)
        notes = [n["content"] for n in client.get("/api/automation/context").json()["manual_notes"]]
        self.assertNotIn("Temporary note to deactivate.", notes)

    def test_dashboard_stats_include_failed_runs(self):
        client.post(
            "/api/automation/runs",
            json={
                "cursor_run_id": "stats-failed-run-1",
                "status": "failed",
                "errors": ["Stats test setup failure."],
            },
            headers={"X-API-Key": "test-key"},
        )
        stats = client.get("/api/dashboard/stats").json()
        self.assertIn("failed_runs", stats)
        self.assertIn("completed_runs", stats)
        self.assertGreaterEqual(stats["failed_runs"], 1)

    def test_create_research_run(self):
        payload = {
            "automation_name": "mta-research",
            "market_summary": "Markets mixed; no action taken.",
            "decisions": [
                {
                    "symbol": "SPY",
                    "action": "hold",
                    "reason": "No dip trigger met.",
                },
                {
                    "symbol": "QQQ",
                    "action": "simulated_buy",
                    "reason": "Would add on pullback.",
                    "amount_usd": 250,
                    "fill_price": 500,
                },
            ],
            "usage": {"model": "composer-2.5", "cost_usd": 0.08},
        }
        response = client.post(
            "/api/automation/runs",
            json=payload,
            headers={"X-API-Key": "test-key"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertGreater(body["run_id"], 0)
        self.assertEqual(body["mode"], "research")

    def test_live_trade_blocked_in_research(self):
        payload = {
            "decisions": [
                {
                    "symbol": "SPY",
                    "action": "buy",
                    "reason": "Should be blocked.",
                    "amount_usd": 100,
                    "review_output": "simulated",
                }
            ]
        }
        response = client.post(
            "/api/automation/runs",
            json=payload,
            headers={"X-API-Key": "test-key"},
        )
        self.assertEqual(response.status_code, 400)

    def test_dashboard_endpoints(self):
        self.assertEqual(client.get("/api/dashboard/stats").status_code, 200)
        self.assertEqual(client.get("/api/dashboard/runs").status_code, 200)
        self.assertEqual(client.get("/api/dashboard/decisions").status_code, 200)
        self.assertEqual(client.get("/api/dashboard/portfolio").status_code, 200)
        self.assertEqual(client.get("/api/dashboard/usage").status_code, 200)

    def test_strategy_kill_switch_update(self):
        response = client.patch(
            "/api/automation/strategy",
            json={"kill_switch": True},
            headers={"X-API-Key": "test-key"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["kill_switch"])

    def test_add_manual_note(self):
        response = client.post(
            "/api/automation/notes",
            json={"content": "Fed meeting this week — stay flat."},
            headers={"X-API-Key": "test-key"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Fed meeting", response.json()["content"])

    def test_cursor_usage_import(self):
        response = client.post(
            "/api/admin/cursor-usage/import",
            json={
                "rows": [
                    {
                        "cursor_run_id": "bc-test-1",
                        "model": "composer-2.5",
                        "cost_usd": 0.12,
                        "input_tokens": 1000,
                        "output_tokens": 200,
                    }
                ]
            },
            headers={"X-API-Key": "test-key"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["inserted"], 1)
        self.assertIn("linked", body)


class PlanVersionHistoryTests(unittest.TestCase):
    def test_plan_update_noop_does_not_create_version(self):
        active = client.get("/api/automation/plan").json()
        response = client.patch(
            "/api/automation/plan",
            json={"change_source": "test-noop"},
            headers={"X-API-Key": "test-key"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["unchanged"])
        self.assertEqual(body["plan"]["version"], active["version"])

        history = client.get("/api/automation/plans").json()
        versions = [row["version"] for row in history]
        self.assertEqual(versions.count(active["version"]), 1)

    def test_plan_update_creates_new_version(self):
        active = client.get("/api/automation/plan").json()
        rules = active["scoring_rules"]
        rules[0] = {**rules[0], "rule": "Updated scoring rule for version bump test."}
        response = client.patch(
            "/api/automation/plan",
            json={
                "change_source": "unit-test",
                "plan": {
                    "run_order": active["run_order"],
                    "required_inputs": active["required_inputs"],
                    "scoring_rules": rules,
                    "data_sources": active["data_sources"],
                    "stop_conditions": active["stop_conditions"],
                },
            },
            headers={"X-API-Key": "test-key"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["unchanged"])
        self.assertNotEqual(body["plan"]["version"], active["version"])
        self.assertEqual(body["plan"]["change_source"], "unit-test")

        fetched = client.get(f"/api/automation/plans/{body['plan']['version']}").json()
        self.assertEqual(fetched["scoring_rules"][0]["rule"], rules[0]["rule"])

    def test_plan_content_deduplication(self):
        first = client.patch(
            "/api/automation/plan",
            json={"name": "Renamed Plan A", "change_source": "rename-a"},
            headers={"X-API-Key": "test-key"},
        )
        self.assertEqual(first.status_code, 200)
        content_hash = first.json()["plan"]["content_hash"]

        second = client.patch(
            "/api/automation/plan",
            json={"name": "Renamed Plan B", "change_source": "rename-b"},
            headers={"X-API-Key": "test-key"},
        )
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["plan"]["content_hash"], content_hash)

    def test_run_records_plan_version(self):
        plan = client.get("/api/automation/plan").json()
        run = client.post(
            "/api/automation/runs",
            json={
                "cursor_run_id": "plan-version-run-1",
                "decisions": [{"symbol": "SPY", "action": "hold", "reason": "Plan version test."}],
            },
            headers={"X-API-Key": "test-key"},
        )
        self.assertEqual(run.status_code, 200)
        run_id = run.json()["run_id"]
        detail = client.get(f"/api/automation/runs/{run_id}").json()
        self.assertEqual(detail["plan_version"], plan["version"])


class DecisionScoringTests(unittest.TestCase):
    def test_decision_with_scores_persisted(self):
        response = client.post(
            "/api/automation/runs",
            json={
                "cursor_run_id": "decision-scores-1",
                "decisions": [
                    {
                        "symbol": "SPY",
                        "action": "hold",
                        "reason": "Neutral setup.",
                        "scores": {
                            "technical": 0.45,
                            "news": 0.5,
                            "risk": 0.35,
                            "confidence": 0.55,
                        },
                        "action_rationale": "No clear edge; scores are mixed.",
                    }
                ],
            },
            headers={"X-API-Key": "test-key"},
        )
        self.assertEqual(response.status_code, 200)
        run_id = response.json()["run_id"]
        detail = client.get(f"/api/automation/runs/{run_id}").json()
        decision = detail["decisions"][0]
        self.assertEqual(decision["scores"]["technical"], 0.45)
        self.assertEqual(decision["scores"]["news"], 0.5)
        self.assertEqual(decision["scores"]["risk"], 0.35)
        self.assertEqual(decision["scores"]["confidence"], 0.55)
        self.assertEqual(decision["action_rationale"], "No clear edge; scores are mixed.")

        dashboard = client.get("/api/dashboard/decisions").json()
        scored = next(row for row in dashboard if row["run_id"] == run_id)
        self.assertEqual(scored["scores"]["confidence"], 0.55)

    def test_decision_without_scores_backward_compatible(self):
        response = client.post(
            "/api/automation/runs",
            json={
                "cursor_run_id": "decision-no-scores-1",
                "decisions": [
                    {
                        "symbol": "QQQ",
                        "action": "skip",
                        "reason": "Legacy shape.",
                        "confidence": 0.4,
                    }
                ],
            },
            headers={"X-API-Key": "test-key"},
        )
        self.assertEqual(response.status_code, 200)
        run_id = response.json()["run_id"]
        decision = client.get(f"/api/automation/runs/{run_id}").json()["decisions"][0]
        self.assertEqual(decision["confidence"], 0.4)
        self.assertIsNone(decision["scores"])
        self.assertIsNone(decision["action_rationale"])

    def test_invalid_score_rejected(self):
        response = client.post(
            "/api/automation/runs",
            json={
                "cursor_run_id": "decision-bad-score-1",
                "decisions": [
                    {
                        "symbol": "SPY",
                        "action": "hold",
                        "reason": "Bad score.",
                        "scores": {"technical": 1.5},
                    }
                ],
            },
            headers={"X-API-Key": "test-key"},
        )
        self.assertEqual(response.status_code, 422)

    def test_agent_plan_includes_decision_scoring_rule(self):
        body = client.get("/api/automation/plan").json()
        self.assertTrue(any(rule["id"] == "decision_scoring" for rule in body["scoring_rules"]))


class Tier3Tests(unittest.TestCase):
    def test_context_includes_symbol_cooldowns_after_buy(self):
        client.post(
            "/api/automation/runs",
            json={
                "cursor_run_id": "cooldown-context-1",
                "decisions": [
                    {
                        "symbol": "SPY",
                        "action": "simulated_buy",
                        "reason": "Open position for cooldown test.",
                        "amount_usd": 100,
                        "fill_price": 500,
                    }
                ],
            },
            headers={"X-API-Key": "test-key"},
        )
        context = client.get("/api/automation/context").json()
        self.assertIn("cooldowns", context)
        self.assertIn("SPY", context["cooldowns"])
        self.assertIn("blocked_until", context["cooldowns"]["SPY"])

    def test_simulated_buy_blocked_on_symbol_cooldown(self):
        client.post(
            "/api/automation/runs",
            json={
                "cursor_run_id": "cooldown-block-1",
                "decisions": [
                    {
                        "symbol": "QQQ",
                        "action": "simulated_buy",
                        "reason": "First buy.",
                        "amount_usd": 100,
                        "fill_price": 400,
                    }
                ],
            },
            headers={"X-API-Key": "test-key"},
        )
        response = client.post(
            "/api/automation/runs",
            json={
                "cursor_run_id": "cooldown-block-2",
                "decisions": [
                    {
                        "symbol": "QQQ",
                        "action": "simulated_buy",
                        "reason": "Repeat buy during cooldown.",
                        "amount_usd": 100,
                        "fill_price": 400,
                    }
                ],
            },
            headers={"X-API-Key": "test-key"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("cooldown", response.json()["detail"].lower())

    def test_read_auth_blocks_dashboard_without_key(self):
        from app.config import settings

        previous = settings.read_api_key
        settings.read_api_key = "read-key"
        try:
            response = client.get("/api/dashboard/stats")
            self.assertEqual(response.status_code, 401)
            authed = client.get(
                "/api/dashboard/stats",
                headers={"X-API-Key": "read-key"},
            )
            self.assertEqual(authed.status_code, 200)
            write_key = client.get(
                "/api/dashboard/stats",
                headers={"X-API-Key": "test-key"},
            )
            self.assertEqual(write_key.status_code, 200)
        finally:
            settings.read_api_key = previous

    def test_health_stays_public_when_read_auth_enabled(self):
        from app.config import settings

        previous = settings.read_api_key
        settings.read_api_key = "read-key"
        try:
            response = client.get("/health")
            self.assertEqual(response.status_code, 200)
        finally:
            settings.read_api_key = previous


class Tier4Tests(unittest.TestCase):
    def setUp(self):
        client.post("/api/admin/portfolio/reset", headers={"X-API-Key": "test-key"})
        client.patch(
            "/api/automation/strategy",
            json={
                "rules": {
                    "allowed_symbols": ["SPY", "QQQ", "AAPL", "MSFT"],
                    "max_order_usd": 500,
                    "max_daily_trades": 50,
                    "max_daily_notional_usd": 50000,
                    "require_review_before_place": True,
                    "watchlist": ["SPY", "QQQ", "AAPL", "MSFT"],
                    "symbol_cooldown_hours": 0,
                }
            },
            headers={"X-API-Key": "test-key"},
        )

    def test_quotes_import_marks_portfolio(self):
        buy = client.post(
            "/api/automation/runs",
            json={
                "cursor_run_id": "quote-portfolio-1",
                "decisions": [
                    {
                        "symbol": "AAPL",
                        "action": "simulated_buy",
                        "reason": "Open AAPL position.",
                        "amount_usd": 500,
                        "fill_price": 200,
                    }
                ],
            },
            headers={"X-API-Key": "test-key"},
        )
        self.assertEqual(buy.status_code, 200)
        client.post(
            "/api/admin/quotes/import",
            json={"quotes": [{"symbol": "AAPL", "price_usd": 220, "source": "test"}]},
            headers={"X-API-Key": "test-key"},
        )
        portfolio = client.get("/api/dashboard/portfolio").json()
        aapl = next(p for p in portfolio["positions"] if p["symbol"] == "AAPL")
        self.assertEqual(aapl["last_price"], 220)
        self.assertGreater(aapl["unrealized_pnl"], 0)
        self.assertIsNotNone(portfolio["total_unrealized_pnl"])

    def test_run_quotes_update_cache(self):
        buy = client.post(
            "/api/automation/runs",
            json={
                "cursor_run_id": "quote-run-buy-1",
                "decisions": [
                    {
                        "symbol": "MSFT",
                        "action": "simulated_buy",
                        "reason": "Position for quote mark.",
                        "amount_usd": 200,
                        "fill_price": 400,
                    }
                ],
            },
            headers={"X-API-Key": "test-key"},
        )
        self.assertEqual(buy.status_code, 200)
        client.post(
            "/api/automation/runs",
            json={
                "cursor_run_id": "quote-run-1",
                "quotes": [{"symbol": "MSFT", "price_usd": 420, "source": "mcp"}],
                "decisions": [{"symbol": "MSFT", "action": "hold", "reason": "Quote refresh only."}],
            },
            headers={"X-API-Key": "test-key"},
        )
        portfolio = client.get("/api/dashboard/portfolio").json()
        msft = next(p for p in portfolio["positions"] if p["symbol"] == "MSFT")
        self.assertEqual(msft["last_price"], 420)

    def test_robinhood_orders_import_and_reconcile(self):
        client.post(
            "/api/automation/runs",
            json={
                "cursor_run_id": "rh-order-decision-1",
                "decisions": [
                    {
                        "symbol": "SPY",
                        "action": "hold",
                        "reason": "Logged alongside Robinhood order id.",
                        "order_id": "rh-order-abc",
                    }
                ],
            },
            headers={"X-API-Key": "test-key"},
        )
        imported = client.post(
            "/api/admin/robinhood-orders/import",
            json={
                "orders": [
                    {
                        "robinhood_order_id": "rh-order-abc",
                        "symbol": "SPY",
                        "side": "buy",
                        "status": "filled",
                        "filled_quantity": 1,
                        "average_fill_price": 500,
                        "notional_usd": 500,
                    }
                ]
            },
            headers={"X-API-Key": "test-key"},
        )
        self.assertEqual(imported.status_code, 200)
        self.assertEqual(imported.json()["linked"], 1)

        orders = client.get("/api/dashboard/orders").json()
        self.assertEqual(orders[0]["reconciliation_status"], "linked")

        summary = client.get("/api/dashboard/reconciliation").json()
        self.assertGreaterEqual(summary["linked_orders"], 1)

    def test_webhook_sets_check_needed_and_run_consumes(self):
        webhook = client.post(
            "/api/admin/webhooks/price-alert",
            json={"symbol": "SPY", "message": "SPY crossed 200-day MA"},
            headers={"X-API-Key": "test-key"},
        )
        self.assertEqual(webhook.status_code, 200)
        context = client.get("/api/automation/context").json()
        self.assertTrue(context["check_needed"])
        self.assertEqual(len(context["market_signals"]), 1)

        client.post(
            "/api/automation/runs",
            json={
                "cursor_run_id": "signal-consume-1",
                "decisions": [{"symbol": "SPY", "action": "hold", "reason": "Reviewed alert."}],
            },
            headers={"X-API-Key": "test-key"},
        )
        context_after = client.get("/api/automation/context").json()
        self.assertFalse(context_after["check_needed"])
        self.assertEqual(len(context_after["market_signals"]), 0)


class Tier5Tests(unittest.TestCase):
    def test_preflight_endpoint(self):
        response = client.get("/api/automation/preflight")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("ready_for_live", body)
        self.assertGreater(len(body["checks"]), 0)
        names = {c["name"] for c in body["checks"]}
        self.assertIn("database", names)
        self.assertIn("reconciliation_clean", names)

    def test_dashboard_export_csv(self):
        response = client.get("/api/dashboard/export?format=csv&type=runs")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response.headers.get("content-type", ""))
        self.assertIn("run_id", response.text)

    def test_cursor_usage_auto_links_run(self):
        client.post(
            "/api/automation/runs",
            json={
                "cursor_run_id": "usage-link-1",
                "decisions": [{"symbol": "SPY", "action": "hold", "reason": "Usage link test."}],
            },
            headers={"X-API-Key": "test-key"},
        )
        response = client.post(
            "/api/admin/cursor-usage/import",
            json={
                "rows": [
                    {
                        "cursor_run_id": "usage-link-1",
                        "model": "composer-2.5",
                        "cost_usd": 0.05,
                    }
                ]
            },
            headers={"X-API-Key": "test-key"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.json()["linked"], 1)
        usage = client.get("/api/dashboard/usage").json()
        linked_row = next(r for r in usage if r["cursor_run_id"] == "usage-link-1")
        self.assertIsNotNone(linked_row["run_id"])

    def test_reconciliation_alert_without_webhook(self):
        client.post(
            "/api/automation/runs",
            json={
                "cursor_run_id": "alert-decision-1",
                "decisions": [
                    {
                        "symbol": "SPY",
                        "action": "hold",
                        "reason": "Unmatched order id.",
                        "order_id": "orphan-order-1",
                    }
                ],
            },
            headers={"X-API-Key": "test-key"},
        )
        response = client.post(
            "/api/admin/alerts/reconciliation-check",
            headers={"X-API-Key": "test-key"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["dispatched"])
        self.assertEqual(body["reason"], "webhook_not_configured")

    def test_dashboard_quotes_endpoint(self):
        client.post(
            "/api/admin/quotes/import",
            json={"quotes": [{"symbol": "SPY", "price_usd": 510, "source": "test"}]},
            headers={"X-API-Key": "test-key"},
        )
        quotes = client.get("/api/dashboard/quotes").json()
        self.assertTrue(any(q["symbol"] == "SPY" for q in quotes))

    def test_rate_limit_disabled_in_tests(self):
        for _ in range(5):
            response = client.get("/health")
            self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
