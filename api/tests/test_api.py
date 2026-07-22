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

_TEST_SELF_CRITIQUE = (
    "Reviewed strategy, safety, cooldowns, freshness, symbol memory, and decision scores."
)
_client_post = client.post


def _post(path: str, **kwargs):
    if path == "/api/automation/runs" and kwargs.get("json"):
        payload = dict(kwargs["json"])
        if payload.get("decisions") and payload.get("status", "completed") != "failed":
            payload.setdefault("self_critique", _TEST_SELF_CRITIQUE)
        kwargs = {**kwargs, "json": payload}
    return _client_post(path, **kwargs)


client.post = _post  # type: ignore[method-assign]


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
        context = client.get("/api/automation/context").json()
        run = client.post(
            "/api/automation/runs",
            json={
                "cursor_run_id": "plan-version-run-1",
                "self_critique": "Hold while verifying plan version stamp.",
                "decisions": [{"symbol": "SPY", "action": "hold", "reason": "Plan version test."}],
            },
            headers={"X-API-Key": "test-key"},
        )
        self.assertEqual(run.status_code, 200)
        run_id = run.json()["run_id"]
        detail = client.get(f"/api/automation/runs/{run_id}").json()
        self.assertEqual(detail["plan_version"], context["plan_version"])

    def test_plan_by_lane_id(self):
        lanes = client.get("/api/dashboard/lanes").json()
        self.assertGreater(len(lanes), 0)
        lane = lanes[0]
        plan = client.get(f"/api/automation/plan?lane_id={lane['id']}").json()
        self.assertEqual(plan["version"], lane["plan_version"])

    def test_sync_plans_from_repo(self):
        response = client.post(
            "/api/admin/plans/sync-from-repo",
            headers={"X-API-Key": "test-key"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertGreaterEqual(body["imported"] + body["updated"] + body["unchanged"], 1)
        self.assertEqual(body["errors"], [])


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
        self.assertEqual(scored["lane_id"], 1)
        self.assertIsNotNone(scored["lane_name"])
        self.assertIsNotNone(scored["lane_role"])

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
    def setUp(self):
        strategy_resp = client.patch(
            "/api/automation/strategy",
            json={
                "rules": {
                    "allowed_symbols": ["SPY", "QQQ", "AAPL", "MSFT"],
                    "max_order_usd": 500,
                    "max_daily_trades": 500,
                    "max_daily_notional_usd": 500000,
                    "require_review_before_place": True,
                    "watchlist": ["SPY", "QQQ", "AAPL", "MSFT"],
                    "symbol_cooldown_hours": 24,
                }
            },
            headers={"X-API-Key": "test-key"},
        ).json()
        client.patch(
            "/api/admin/lanes/1",
            json={"strategy_version": strategy_resp["version"]},
            headers={"X-API-Key": "test-key"},
        )

    def test_context_includes_symbol_cooldowns_after_buy(self):
        client.post(
            "/api/automation/runs",
            json={
                "cursor_run_id": "cooldown-context-1",
                "self_critique": "SPY buy to test cooldown visibility.",
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
                "self_critique": "First QQQ buy for cooldown block test.",
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
                "self_critique": "Repeat buy should be blocked by cooldown.",
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
        strategy_resp = client.patch(
            "/api/automation/strategy",
            json={
                "rules": {
                    "allowed_symbols": ["SPY", "QQQ", "AAPL", "MSFT"],
                    "max_order_usd": 500,
                    "max_daily_trades": 500,
                    "max_daily_notional_usd": 500000,
                    "require_review_before_place": True,
                    "watchlist": ["SPY", "QQQ", "AAPL", "MSFT"],
                    "symbol_cooldown_hours": 0,
                }
            },
            headers={"X-API-Key": "test-key"},
        ).json()
        client.patch(
            "/api/admin/lanes/1",
            json={"strategy_version": strategy_resp["version"]},
            headers={"X-API-Key": "test-key"},
        )

    def test_quotes_import_marks_portfolio(self):
        buy = client.post(
            "/api/automation/runs",
            json={
                "cursor_run_id": "quote-portfolio-1",
                "self_critique": "AAPL simulated buy for quote mark test.",
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
                "self_critique": "MSFT buy to seed quote cache test.",
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

    def test_empty_robinhood_orders_import_unlocks_market_inputs(self):
        client.post(
            "/api/admin/quotes/import",
            json={
                "quotes": [
                    {"symbol": "SPY", "price_usd": 520, "source": "test"},
                    {"symbol": "QQQ", "price_usd": 450, "source": "test"},
                    {"symbol": "AAPL", "price_usd": 190, "source": "test"},
                    {"symbol": "MSFT", "price_usd": 420, "source": "test"},
                ]
            },
            headers={"X-API-Key": "test-key"},
        )
        before = client.get("/api/automation/market-inputs").json()
        orders_item = next(i for i in before["checklist"] if i["key"] == "recent_orders")
        self.assertFalse(orders_item["present"])

        imported = client.post(
            "/api/admin/robinhood-orders/import",
            json={"orders": []},
            headers={"X-API-Key": "test-key"},
        )
        self.assertEqual(imported.status_code, 200)
        self.assertEqual(imported.json()["upserted"], 0)

        client.post(
            "/api/automation/runs",
            json={
                "cursor_run_id": "empty-orders-sync-1",
                "self_critique": "Confirmed empty Robinhood order book after sync.",
                "decisions": [{"symbol": "SPY", "action": "hold", "reason": "Sync check."}],
            },
            headers={"X-API-Key": "test-key"},
        )

        after = client.get("/api/automation/market-inputs").json()
        orders_item = next(i for i in after["checklist"] if i["key"] == "recent_orders")
        self.assertTrue(orders_item["present"])
        self.assertIn("sync confirmed", orders_item["detail"])
        self.assertTrue(after["ready"])

    def test_symbol_discovery_candidates(self):
        strategy_resp = client.patch(
            "/api/automation/strategy",
            json={
                "rules": {
                    "allowed_symbols": ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "GOOGL"],
                    "max_order_usd": 500,
                    "max_daily_trades": 3,
                    "max_daily_notional_usd": 1500,
                    "require_review_before_place": True,
                    "watchlist": ["SPY", "QQQ", "AAPL", "MSFT"],
                    "symbol_cooldown_hours": 24,
                    "symbol_discovery_enabled": True,
                    "discovery_max_per_run": 2,
                    "discovery_pool": ["NVDA", "GOOGL"],
                }
            },
            headers={"X-API-Key": "test-key"},
        ).json()
        client.patch(
            "/api/admin/lanes/1",
            json={"strategy_version": strategy_resp["version"]},
            headers={"X-API-Key": "test-key"},
        )
        discovery = client.get("/api/automation/discovery/candidates").json()
        self.assertTrue(discovery["enabled"])
        self.assertEqual(discovery["candidate_pool"], ["NVDA", "GOOGL"])
        self.assertEqual(discovery["max_per_run"], 2)

        context = client.get("/api/automation/context").json()
        self.assertTrue(context["symbol_discovery"]["enabled"])
        self.assertIn("NVDA", context["symbol_discovery"]["candidate_pool"])

    def test_symbol_proposals_import_and_promote(self):
        imported = client.post(
            "/api/admin/symbol-proposals/import",
            json={
                "scout_run_id": "scout-test-1",
                "proposals": [
                    {
                        "symbol": "NVDA",
                        "source": "test",
                        "score": 0.8,
                        "tags": ["semiconductor"],
                        "thesis": "Strong momentum candidate for discovery.",
                    },
                    {
                        "symbol": "GOOGL",
                        "source": "test",
                        "score": 0.7,
                        "thesis": "Mega-cap with catalyst potential.",
                    },
                ],
            },
            headers={"X-API-Key": "test-key"},
        )
        self.assertEqual(imported.status_code, 200)
        self.assertEqual(imported.json()["inserted"], 2)
        pending = client.get(
            "/api/admin/symbol-proposals?status=pending",
            headers={"X-API-Key": "test-key"},
        ).json()
        self.assertGreaterEqual(len(pending), 2)
        ids = [p["id"] for p in pending if p["symbol"] in {"NVDA", "GOOGL"}]

        promoted = client.post(
            "/api/admin/symbol-proposals/promote",
            json={
                "proposal_ids": ids,
                "enable_discovery": True,
                "discovery_max_per_run": 2,
                "update_lanes": True,
            },
            headers={"X-API-Key": "test-key"},
        )
        self.assertEqual(promoted.status_code, 200, promoted.text)
        body = promoted.json()
        self.assertIn("NVDA", body["added_to_allowed"])
        self.assertIn("GOOGL", body["added_to_discovery_pool"])

        discovery = client.get("/api/automation/discovery/candidates").json()
        self.assertTrue(discovery["enabled"])
        self.assertIn("NVDA", discovery["candidate_pool"])

    def test_symbol_proposals_auto_promote(self):
        client.post(
            "/api/admin/symbol-proposals/import",
            json={
                "scout_run_id": "scout-auto-1",
                "proposals": [
                    {
                        "symbol": "AMD",
                        "source": "test",
                        "score": 0.9,
                        "thesis": "High score auto-promote candidate.",
                    },
                    {
                        "symbol": "INTC",
                        "source": "test",
                        "score": 0.4,
                        "thesis": "Below threshold — should stay pending.",
                    },
                ],
            },
            headers={"X-API-Key": "test-key"},
        )
        result = client.post(
            "/api/admin/symbol-proposals/auto-promote",
            json={"min_score": 0.65, "max_symbols": 5, "enable_discovery": True},
            headers={"X-API-Key": "test-key"},
        )
        self.assertEqual(result.status_code, 200, result.text)
        body = result.json()
        self.assertIn("AMD", body["added_to_allowed"])
        self.assertNotIn("INTC", body["added_to_allowed"])
        pending = client.get(
            "/api/admin/symbol-proposals?status=pending",
            headers={"X-API-Key": "test-key"},
        ).json()
        self.assertTrue(any(p["symbol"] == "INTC" for p in pending))

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
        self.assertIsNotNone(body.get("alert_id"))

        alerts = client.get("/api/dashboard/alerts?status=open").json()
        self.assertTrue(any(a["alert_type"] == "reconciliation_mismatch" for a in alerts))

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




class PriorityGroupBatchTests(unittest.TestCase):
    def setUp(self):
        client.post("/api/admin/portfolio/reset", headers={"X-API-Key": "test-key"})
        strategy_resp = client.patch(
            "/api/automation/strategy",
            json={
                "rules": {
                    "allowed_symbols": ["SPY", "QQQ", "AAPL", "MSFT"],
                    "max_order_usd": 500,
                    "max_daily_trades": 500,
                    "max_daily_notional_usd": 500000,
                    "require_review_before_place": True,
                    "watchlist": ["SPY", "QQQ", "AAPL", "MSFT"],
                    "symbol_cooldown_hours": 0,
                }
            },
            headers={"X-API-Key": "test-key"},
        ).json()
        client.patch(
            "/api/admin/lanes/1",
            json={"strategy_version": strategy_resp["version"]},
            headers={"X-API-Key": "test-key"},
        )

    def test_dashboard_login_and_session_auth(self):
        from app.config import settings

        previous_password = settings.dashboard_password
        settings.dashboard_password = "dashboard-test-password"
        try:
            unconfigured = client.post(
                "/api/auth/login",
                json={"password": "dashboard-test-password"},
            )
            self.assertEqual(unconfigured.status_code, 200)
            token = unconfigured.json()["token"]
            self.assertTrue(token)

            stats = client.get(
                "/api/dashboard/stats",
                headers={"Authorization": f"Bearer {token}"},
            )
            self.assertEqual(stats.status_code, 200)

            logout = client.post(
                "/api/auth/logout",
                headers={"Authorization": f"Bearer {token}"},
            )
            self.assertEqual(logout.status_code, 200)
            self.assertTrue(logout.json()["revoked"])

            after_logout = client.get(
                "/api/dashboard/stats",
                headers={"Authorization": f"Bearer {token}"},
            )
            self.assertEqual(after_logout.status_code, 401)
        finally:
            settings.dashboard_password = previous_password

    def test_run_type_persisted_and_validated(self):
        response = client.post(
            "/api/automation/runs",
            json={
                "cursor_run_id": "run-type-test-1",
                "run_type": "signal_response",
                "decisions": [{"symbol": "SPY", "action": "hold", "reason": "Run type test."}],
            },
            headers={"X-API-Key": "test-key"},
        )
        self.assertEqual(response.status_code, 200)
        run_id = response.json()["run_id"]
        detail = client.get(f"/api/automation/runs/{run_id}").json()
        self.assertEqual(detail["run_type"], "signal_response")

        context = client.get("/api/automation/context").json()
        self.assertIn("daily_research", context["valid_run_types"])
        self.assertIn("signal_response", context["valid_run_types"])

        bad = client.post(
            "/api/automation/runs",
            json={
                "cursor_run_id": "run-type-bad-1",
                "run_type": "invalid_type",
                "decisions": [{"symbol": "SPY", "action": "hold", "reason": "Bad type."}],
            },
            headers={"X-API-Key": "test-key"},
        )
        self.assertEqual(bad.status_code, 400)

    def test_portfolio_snapshot_on_completed_run(self):
        response = client.post(
            "/api/automation/runs",
            json={
                "cursor_run_id": "snapshot-test-1",
                "decisions": [{"symbol": "SPY", "action": "hold", "reason": "Snapshot test."}],
            },
            headers={"X-API-Key": "test-key"},
        )
        self.assertEqual(response.status_code, 200)
        snapshots = client.get("/api/dashboard/portfolio/snapshots").json()
        self.assertGreaterEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0]["source"], "run")
        self.assertIsNotNone(snapshots[0]["total_equity_usd"])

    def test_schema_migrations_applied(self):
        from app.database import get_connection

        conn = get_connection()
        try:
            rows = conn.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
            versions = [row["version"] for row in rows]
            self.assertIn("001_dashboard_sessions", versions)
            self.assertIn("003_portfolio_snapshots", versions)
            self.assertIn("004_symbol_memory_summaries", versions)
        finally:
            conn.close()

    def test_symbol_memory_endpoint(self):
        response = client.post(
            "/api/automation/runs",
            json={
                "cursor_run_id": "memory-endpoint-1",
                "self_critique": "MSFT buy within research limits.",
                "decisions": [
                    {
                        "symbol": "MSFT",
                        "action": "simulated_buy",
                        "reason": "Memory test buy.",
                        "amount_usd": 200,
                        "fill_price": 400,
                    }
                ],
            },
            headers={"X-API-Key": "test-key"},
        )
        self.assertEqual(response.status_code, 200)
        memory = client.get("/api/automation/symbols/MSFT/memory").json()
        self.assertEqual(memory["symbol"], "MSFT")
        self.assertIsNotNone(memory["summary"])
        self.assertEqual(memory["summary"]["last_action"], "simulated_buy")
        self.assertGreaterEqual(len(memory["recent_decisions"]), 1)
        self.assertIsNotNone(memory["position"])

    def test_symbol_memory_summary_table_updated(self):
        from app.database import get_connection

        response = client.post(
            "/api/automation/runs",
            json={
                "cursor_run_id": "memory-summary-table-1",
                "self_critique": "MSFT buy for summary table check.",
                "decisions": [
                    {
                        "symbol": "MSFT",
                        "action": "simulated_buy",
                        "reason": "Summary table test.",
                        "amount_usd": 200,
                        "fill_price": 400,
                    }
                ],
            },
            headers={"X-API-Key": "test-key"},
        )
        self.assertEqual(response.status_code, 200)

        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT last_action, trade_count FROM symbol_memory_summaries WHERE lane_id = 1 AND symbol = 'MSFT'"
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["last_action"], "simulated_buy")
            self.assertGreaterEqual(row["trade_count"], 1)
        finally:
            conn.close()


class PriorityGroupBatch2Tests(unittest.TestCase):
    def setUp(self):
        client.post("/api/admin/portfolio/reset", headers={"X-API-Key": "test-key"})

    def test_portfolio_snapshot_summary_api(self):
        client.post(
            "/api/automation/runs",
            json={
                "cursor_run_id": "summary-api-1",
                "decisions": [{"symbol": "SPY", "action": "hold", "reason": "Summary test."}],
            },
            headers={"X-API-Key": "test-key"},
        )
        summary = client.get("/api/dashboard/portfolio/snapshots/summary").json()
        self.assertGreaterEqual(summary["snapshot_count"], 1)
        self.assertIn("change_pct", summary)

        automation = client.get("/api/dashboard/portfolio/snapshots/summary").json()
        self.assertEqual(automation["snapshot_count"], summary["snapshot_count"])

    def test_data_freshness_table_and_endpoints(self):
        client.post(
            "/api/admin/quotes/import",
            json={"quotes": [{"symbol": "SPY", "price_usd": 500, "source": "test"}]},
            headers={"X-API-Key": "test-key"},
        )
        freshness = client.get("/api/dashboard/freshness/check").json()
        keys = {row["source_key"] for row in freshness["sources"]}
        self.assertIn("quotes", keys)
        quotes_row = next(r for r in freshness["sources"] if r["source_key"] == "quotes")
        self.assertIsNotNone(quotes_row["last_updated_at"])
        self.assertIn("is_stale", quotes_row)
        self.assertFalse(quotes_row["is_stale"])

        checks = client.get("/api/automation/freshness/check").json()
        self.assertIn("ready_for_analysis", checks)
        self.assertIn("stale_sources", checks)
        self.assertIn("warnings", checks)
        self.assertGreaterEqual(len(checks["sources"]), 1)

        context = client.get("/api/automation/context").json()
        self.assertIn("data_freshness", context)
        self.assertIn("freshness_checks", context)
        self.assertGreaterEqual(len(context["data_freshness"]), 1)
        self.assertTrue(context["freshness_checks"]["ready_for_analysis"])

    def test_market_input_bundle_endpoint(self):
        client.post(
            "/api/admin/quotes/import",
            json={
                "quotes": [
                    {"symbol": "SPY", "price_usd": 520, "source": "test"},
                    {"symbol": "QQQ", "price_usd": 450, "source": "test"},
                    {"symbol": "AAPL", "price_usd": 190, "source": "test"},
                    {"symbol": "MSFT", "price_usd": 420, "source": "test"},
                ]
            },
            headers={"X-API-Key": "test-key"},
        )
        bundle = client.get("/api/automation/market-inputs").json()
        self.assertIn("checklist", bundle)
        self.assertIn("watchlist_quotes", bundle)
        self.assertGreaterEqual(len(bundle["watchlist_quotes"]), 1)
        context = client.get("/api/automation/context").json()
        self.assertIn("market_input_bundle", context)

    def test_intervention_check_endpoint(self):
        status = client.get("/api/automation/intervention/check").json()
        self.assertIn("intervention_required", status)
        self.assertIn("triggers", status)
        self.assertIn("recommended_action", status)

        context = client.get("/api/automation/context").json()
        self.assertIn("intervention_status", context)

    def test_usage_summary_and_dashboard_strategy(self):
        client.post(
            "/api/admin/cursor-usage/import",
            json={
                "rows": [
                    {
                        "model": "composer-2.5",
                        "cost_usd": 1.25,
                        "input_tokens": 1000,
                        "output_tokens": 500,
                    }
                ]
            },
            headers={"X-API-Key": "test-key"},
        )
        summary = client.get("/api/dashboard/usage/summary").json()
        self.assertGreaterEqual(summary["total_cost_usd"], 1.25)
        self.assertGreaterEqual(summary["total_effective_cost_usd"], 1.25)
        self.assertIn("total_estimated_cost_usd", summary)
        self.assertIn("by_model", summary)
        self.assertIn("by_run_type", summary)

        updated = client.patch(
            "/api/dashboard/strategy",
            json={"kill_switch": True},
            headers={"X-API-Key": "test-key"},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertTrue(updated.json()["kill_switch"])

    def test_self_critique_required_on_completed_runs(self):
        missing = _client_post(
            "/api/automation/runs",
            json={
                "cursor_run_id": "critique-missing-1",
                "decisions": [{"symbol": "SPY", "action": "hold", "reason": "No critique."}],
            },
            headers={"X-API-Key": "test-key"},
        )
        self.assertEqual(missing.status_code, 400)

        ok = client.post(
            "/api/automation/runs",
            json={
                "cursor_run_id": "critique-ok-1",
                "decisions": [{"symbol": "SPY", "action": "hold", "reason": "With critique."}],
                "self_critique": "Reviewed safety and cooldowns; hold is appropriate.",
            },
            headers={"X-API-Key": "test-key"},
        )
        self.assertEqual(ok.status_code, 200)
        detail = client.get(f"/api/automation/runs/{ok.json()['run_id']}").json()
        self.assertIn("self_critique", detail)
        self.assertTrue(detail["self_critique"])

    def test_news_event_summaries_and_ingest(self):
        ingest = client.post(
            "/api/admin/news/import",
            json={
                "events": [
                    {
                        "symbol": "AAPL",
                        "source": "test-feed",
                        "event_at": "2026-06-29T12:00:00+00:00",
                        "event_type": "headline",
                        "importance": 0.8,
                        "summary": "Apple announces product update.",
                        "external_id": "test-news-1",
                    },
                    {
                        "source": "macro-cal",
                        "event_at": "2026-06-29T08:00:00+00:00",
                        "event_type": "macro",
                        "summary": "Fed meeting minutes released.",
                        "external_id": "test-macro-1",
                    },
                ]
            },
            headers={"X-API-Key": "test-key"},
        )
        self.assertEqual(ingest.status_code, 200)
        self.assertEqual(ingest.json()["inserted"], 2)

        dup = client.post(
            "/api/admin/news/import",
            json={
                "events": [
                    {
                        "symbol": "AAPL",
                        "source": "test-feed",
                        "event_at": "2026-06-29T12:00:00+00:00",
                        "summary": "Duplicate.",
                        "external_id": "test-news-1",
                    }
                ]
            },
            headers={"X-API-Key": "test-key"},
        )
        self.assertEqual(dup.json()["skipped"], 1)

        news = client.get("/api/automation/news?symbol=AAPL").json()
        self.assertGreaterEqual(len(news), 1)
        self.assertEqual(news[0]["symbol"], "AAPL")

        context = client.get("/api/automation/context").json()
        self.assertIn("recent_news", context)
        self.assertGreaterEqual(len(context["recent_news"]), 1)

        memory = client.get("/api/automation/symbols/AAPL/memory").json()
        self.assertIn("recent_news", memory)
        self.assertGreaterEqual(len(memory["recent_news"]), 1)

        checks = client.get("/api/dashboard/freshness/check").json()
        keys = {row["source_key"] for row in checks["sources"]}
        self.assertIn("news", keys)
        news_row = next(r for r in checks["sources"] if r["source_key"] == "news")
        self.assertFalse(news_row["is_stale"])

    def test_activity_timeline_endpoint(self):
        client.post(
            "/api/automation/runs",
            json={
                "cursor_run_id": "timeline-test-1",
                "decisions": [{"symbol": "QQQ", "action": "hold", "reason": "Timeline test."}],
            },
            headers={"X-API-Key": "test-key"},
        )
        timeline = client.get("/api/dashboard/timeline?limit=20").json()
        self.assertGreaterEqual(len(timeline), 1)
        types = {event["event_type"] for event in timeline}
        self.assertTrue(types.intersection({"run", "decision"}))

    def test_snapshot_filters(self):
        create = client.post(
            "/api/automation/runs",
            json={
                "cursor_run_id": "filter-test-1",
                "decisions": [{"symbol": "SPY", "action": "hold", "reason": "Filter test."}],
            },
            headers={"X-API-Key": "test-key"},
        )
        run_id = create.json()["run_id"]
        filtered = client.get(f"/api/dashboard/portfolio/snapshots?run_id={run_id}").json()
        self.assertGreaterEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["run_id"], run_id)


class PriorityGroupTop8Tests(unittest.TestCase):
    def setUp(self):
        client.patch(
            "/api/automation/strategy",
            json={"mode": "research", "trading_enabled": False, "kill_switch": False},
            headers={"X-API-Key": "test-key"},
        )

    def test_failed_run_creates_alert(self):
        response = _client_post(
            "/api/automation/runs",
            json={
                "status": "failed",
                "cursor_run_id": "failed-alert-test-1",
                "errors": ["MCP timeout during quote fetch."],
                "decisions": [],
            },
            headers={"X-API-Key": "test-key"},
        )
        self.assertEqual(response.status_code, 200)
        run_id = response.json()["run_id"]
        alerts = client.get("/api/dashboard/alerts").json()
        match = next((a for a in alerts if a["run_id"] == run_id), None)
        self.assertIsNotNone(match)
        self.assertEqual(match["alert_type"], "failed_run")
        self.assertEqual(match["status"], "open")

    def test_alert_ack_and_resolve(self):
        client.post(
            "/api/admin/alerts/reconciliation-check",
            headers={"X-API-Key": "test-key"},
        )
        alerts = client.get("/api/dashboard/alerts?status=open").json()
        self.assertGreaterEqual(len(alerts), 1)
        alert_id = alerts[0]["id"]
        ack = client.patch(
            f"/api/dashboard/alerts/{alert_id}",
            json={"status": "acknowledged"},
            headers={"X-API-Key": "test-key"},
        )
        self.assertEqual(ack.status_code, 200)
        self.assertEqual(ack.json()["status"], "acknowledged")
        resolved = client.patch(
            f"/api/dashboard/alerts/{alert_id}",
            json={"status": "resolved"},
            headers={"X-API-Key": "test-key"},
        )
        self.assertEqual(resolved.json()["status"], "resolved")

    def test_01_live_promotion_workflow(self):
        client.post(
            "/api/automation/runs",
            json={
                "cursor_run_id": "promotion-preflight-1",
                "decisions": [{"symbol": "SPY", "action": "hold", "reason": "Preflight seed."}],
            },
            headers={"X-API-Key": "test-key"},
        )
        request = client.post(
            "/api/admin/live-promotion/request",
            headers={"X-API-Key": "test-key"},
        )
        self.assertEqual(request.status_code, 200)
        token = request.json()["promotion_token"]
        self.assertTrue(token)

        status_before = client.get("/api/automation/live-promotion/status").json()
        self.assertEqual(status_before["latest_request"]["status"], "pending")

        preflight = client.get("/api/automation/preflight").json()
        approve = client.post(
            "/api/admin/live-promotion/approve",
            json={"promotion_token": token, "approved_by": "test-operator"},
            headers={"X-API-Key": "test-key"},
        )
        if not preflight["ready_for_live"]:
            self.assertEqual(approve.status_code, 400)
            return

        self.assertEqual(approve.status_code, 200)
        self.assertTrue(approve.json()["preflight_ready"])

        strategy = client.get("/api/automation/context").json()["strategy"]
        self.assertEqual(strategy["mode"], "live")
        self.assertTrue(strategy["trading_enabled"])

    def test_retention_run(self):
        response = client.post(
            "/api/admin/retention/run",
            json={"keep_runs_days": 90, "keep_snapshots_days": 180, "keep_usage_days": 180},
            headers={"X-API-Key": "test-key"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("runs_deleted", body)
        self.assertIn("message", body)

    def test_maintenance_and_db_snapshots(self):
        maintenance = client.post(
            "/api/admin/maintenance/run?vacuum=false&analyze=true",
            headers={"X-API-Key": "test-key"},
        )
        self.assertEqual(maintenance.status_code, 200)
        self.assertTrue(maintenance.json()["analyze_ran"])
        self.assertFalse(maintenance.json()["vacuum_ran"])
        self.assertGreater(maintenance.json()["snapshot_id"], 0)

    def test_strategy_performance_api(self):
        client.post(
            "/api/automation/runs",
            json={
                "cursor_run_id": "perf-test-1",
                "decisions": [
                    {
                        "symbol": "SPY",
                        "action": "simulated_buy",
                        "reason": "Performance test.",
                        "amount_usd": 100,
                        "fill_price": 500,
                        "scores": {"confidence": 0.7},
                    }
                ],
            },
            headers={"X-API-Key": "test-key"},
        )
        compare = client.get("/api/dashboard/strategy/compare").json()
        self.assertIn("strategy_versions", compare)
        self.assertGreaterEqual(len(compare["strategy_versions"]), 1)

    def test_simulation_discipline_in_plan(self):
        plan = client.get("/api/automation/plans/v1").json()
        rule_ids = {rule["id"] for rule in plan["scoring_rules"]}
        self.assertIn("simulation_discipline", rule_ids)


class PriorityGroupG1Tests(unittest.TestCase):
    def test_usage_budget_in_context(self):
        context = client.get("/api/automation/context").json()
        self.assertIn("usage_budget", context)
        budget = context["usage_budget"]
        self.assertIn("daily_budget_usd", budget)
        self.assertIn("budget_ok", budget)
        self.assertIn("run_type_budget_usd", budget)
        self.assertIn("daily_research", budget["run_type_budget_usd"])

    def test_run_budget_exceeded_on_post(self):
        response = client.post(
            "/api/automation/runs",
            json={
                "cursor_run_id": "budget-exceed-g1-1",
                "run_type": "signal_response",
                "decisions": [{"symbol": "SPY", "action": "hold", "reason": "Budget test."}],
                "usage": {
                    "model": "composer-2.5",
                    "cost_usd": 0.99,
                    "input_tokens": 5000,
                    "output_tokens": 1000,
                },
            },
            headers={"X-API-Key": "test-key"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["budget_check"]["budget_exceeded"])
        run = client.get(f"/api/automation/runs/{body['run_id']}").json()
        self.assertTrue(run["budget_exceeded"])
        self.assertAlmostEqual(run["expected_budget_usd"], 0.15)

    def test_strategy_compare(self):
        response = client.get("/api/dashboard/strategy/compare")
        self.assertEqual(response.status_code, 200)
        self.assertIn("strategy_versions", response.json())

    def test_metrics_endpoint(self):
        response = client.get("/metrics")
        self.assertEqual(response.status_code, 200)
        self.assertIn("mta_runs_total", response.text)

    def test_export_json(self):
        response = client.get("/api/dashboard/export?format=json&type=runs")
        self.assertEqual(response.status_code, 200)
        self.assertIn("application/json", response.headers.get("content-type", ""))

    def test_mobile_status(self):
        response = client.get("/api/dashboard/status/mobile")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("open_alerts", body)
        self.assertIn("total_equity_usd", body)

    def test_run_detail_includes_audit(self):
        create = client.post(
            "/api/automation/runs",
            json={
                "cursor_run_id": "audit-g1-1",
                "self_critique": "Hold for audit drill-down test.",
                "decisions": [{"symbol": "QQQ", "action": "hold", "reason": "Audit test."}],
            },
            headers={"X-API-Key": "test-key"},
        )
        run_id = create.json()["run_id"]
        detail = client.get(f"/api/automation/runs/{run_id}").json()
        self.assertIn("audit", detail)
        self.assertEqual(detail["audit"]["run_id"], run_id)


class SimulationLaneTests(unittest.TestCase):
    def setUp(self):
        strategy_resp = client.patch(
            "/api/automation/strategy",
            json={
                "rules": {
                    "allowed_symbols": ["SPY", "QQQ", "AAPL", "MSFT"],
                    "max_order_usd": 500,
                    "max_daily_trades": 500,
                    "max_daily_notional_usd": 500000,
                    "require_review_before_place": True,
                    "watchlist": ["SPY", "QQQ", "AAPL", "MSFT"],
                    "symbol_cooldown_hours": 0,
                }
            },
            headers={"X-API-Key": "test-key"},
        ).json()
        client.patch(
            "/api/admin/lanes/1",
            json={"strategy_version": strategy_resp["version"]},
            headers={"X-API-Key": "test-key"},
        )

    def test_primary_lane_in_context(self):
        context = client.get("/api/automation/context").json()
        self.assertEqual(context["lane_id"], 1)
        self.assertEqual(context["lane_name"], "primary")
        self.assertIn("agent_plan", context)

    def test_two_lanes_isolated_portfolios(self):
        strategy_version = client.get("/api/automation/context").json()["strategy"]["version"]
        lane_b = client.post(
            "/api/admin/lanes",
            json={
                "name": "challenger",
                "strategy_version": strategy_version,
                "plan_version": "v1",
                "lane_role": "shadow",
            },
            headers={"X-API-Key": "test-key"},
        )
        self.assertEqual(lane_b.status_code, 200)
        lane_b_id = lane_b.json()["id"]

        buy_a = client.post(
            "/api/automation/runs",
            json={
                "cursor_run_id": "lane-a-buy-1",
                "lane_id": 1,
                "self_critique": "Lane A buy.",
                "decisions": [
                    {
                        "symbol": "SPY",
                        "action": "simulated_buy",
                        "reason": "Lane A only.",
                        "amount_usd": 100,
                        "fill_price": 100,
                    }
                ],
            },
            headers={"X-API-Key": "test-key"},
        )
        self.assertEqual(buy_a.status_code, 200)

        portfolio_b = client.get(f"/api/automation/context?lane_id={lane_b_id}").json()
        self.assertEqual(portfolio_b["simulated_portfolio"]["cash_usd"], 10000.0)
        self.assertEqual(len(portfolio_b["simulated_portfolio"]["positions"]), 0)

        portfolio_a = client.get("/api/automation/context?lane_id=1").json()
        self.assertLess(portfolio_a["simulated_portfolio"]["cash_usd"], 10000.0)

    def test_lane_compare_equity(self):
        client.post(
            "/api/automation/runs",
            json={
                "cursor_run_id": "lane-compare-equity-1",
                "lane_id": 1,
                "self_critique": "Seed snapshot for compare.",
                "decisions": [
                    {
                        "symbol": "SPY",
                        "action": "simulated_buy",
                        "reason": "Compare equity seed.",
                        "amount_usd": 50,
                        "fill_price": 100,
                    }
                ],
            },
            headers={"X-API-Key": "test-key"},
        )
        compare = client.get("/api/dashboard/lanes/compare").json()
        self.assertGreaterEqual(len(compare["lanes"]), 1)
        primary = next(row for row in compare["lanes"] if row["lane_id"] == 1)
        self.assertIsNotNone(primary["equity_change_usd"])

    def test_lane_reset(self):
        reset = client.post(
            "/api/admin/lanes/1/reset",
            headers={"X-API-Key": "test-key"},
        )
        self.assertEqual(reset.status_code, 200)
        self.assertEqual(reset.json()["cash_usd"], 10000.0)

    def test_schema_migration_011(self):
        from app.database import get_connection

        conn = get_connection()
        try:
            versions = [
                row["version"]
                for row in conn.execute("SELECT version FROM schema_migrations ORDER BY version")
            ]
            self.assertIn("011_simulation_lanes", versions)
            lane_count = conn.execute("SELECT COUNT(*) AS c FROM simulation_lanes").fetchone()["c"]
            self.assertGreaterEqual(lane_count, 1)
        finally:
            conn.close()

    def test_live_history_endpoint(self):
        response = client.get("/api/dashboard/lanes/live-history")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("periods", body)
        self.assertIn("combined_snapshots", body)
        self.assertIn("description", body)

    def test_live_periods_preserved_when_promoting_new_lane(self):
        from unittest.mock import MagicMock, patch

        strategy_version = client.get("/api/automation/context").json()["strategy"]["version"]
        lane_b = client.post(
            "/api/admin/lanes",
            json={
                "name": "live-challenger",
                "strategy_version": strategy_version,
                "plan_version": "v1",
                "lane_role": "shadow",
            },
            headers={"X-API-Key": "test-key"},
        ).json()["id"]

        seed_a = client.post(
            "/api/automation/runs",
            json={
                "cursor_run_id": "live-period-a-1",
                "lane_id": 1,
                "self_critique": "Seed lane A snapshots.",
                "decisions": [
                    {
                        "symbol": "SPY",
                        "action": "simulated_buy",
                        "reason": "Lane A live stint seed.",
                        "amount_usd": 100,
                        "fill_price": 100,
                    }
                ],
            },
            headers={"X-API-Key": "test-key"},
        )
        self.assertEqual(seed_a.status_code, 200)

        seed_b = client.post(
            "/api/automation/runs",
            json={
                "cursor_run_id": "live-period-b-1",
                "lane_id": lane_b,
                "self_critique": "Seed lane B snapshots.",
                "decisions": [
                    {
                        "symbol": "QQQ",
                        "action": "simulated_buy",
                        "reason": "Lane B live stint seed.",
                        "amount_usd": 100,
                        "fill_price": 100,
                    }
                ],
            },
            headers={"X-API-Key": "test-key"},
        )
        self.assertEqual(seed_b.status_code, 200)

        ready = MagicMock(ready_for_live=True)
        with patch("app.preflight_service.get_live_preflight", return_value=ready):
            promote_a = client.post(
                "/api/admin/lanes/1/promote-to-live",
                headers={"X-API-Key": "test-key"},
            )
        self.assertEqual(promote_a.status_code, 200)
        self.assertEqual(promote_a.json()["lane"]["lane_role"], "live")

        with patch("app.preflight_service.get_live_preflight", return_value=ready):
            promote_b = client.post(
                f"/api/admin/lanes/{lane_b}/promote-to-live",
                headers={"X-API-Key": "test-key"},
            )
        self.assertEqual(promote_b.status_code, 200)
        self.assertEqual(promote_b.json()["previous_live_lane_id"], 1)

        lane_a = client.get("/api/dashboard/lanes").json()
        primary = next(row for row in lane_a if row["id"] == 1)
        challenger = next(row for row in lane_a if row["id"] == lane_b)
        self.assertEqual(primary["lane_role"], "shadow")
        self.assertEqual(challenger["lane_role"], "live")

        history = client.get("/api/dashboard/lanes/live-history").json()
        self.assertEqual(len(history["periods"]), 2)
        self.assertIsNone(history["periods"][-1]["ended_at"])
        self.assertIsNotNone(history["periods"][0]["ended_at"])
        self.assertEqual(history["current_live_lane_id"], lane_b)

        portfolio_a = client.get("/api/dashboard/portfolio?lane_id=1").json()
        # After promotion, lane 1 is synced to the new live lane's paper baseline.
        portfolio_b = client.get(f"/api/dashboard/portfolio?lane_id={lane_b}").json()
        self.assertAlmostEqual(portfolio_a["cash_usd"], portfolio_b["cash_usd"], places=2)
        promote_body = promote_b.json()
        self.assertIsNotNone(promote_body.get("live_strategy_version"))
        self.assertTrue(any(s["lane_id"] == 1 for s in promote_body.get("synced_lanes", [])))
        live_ctx = client.get(f"/api/automation/context?lane_id={lane_b}").json()
        self.assertTrue(live_ctx["safety"]["trading_allowed"])
        self.assertEqual(live_ctx["strategy"]["mode"], "live")
        compare = client.get("/api/dashboard/lanes/compare").json()
        row_a = next(row for row in compare["lanes"] if row["lane_id"] == 1)
        self.assertGreater(row_a["run_count"], 0)

    def test_schema_migration_012(self):
        from app.database import get_connection

        conn = get_connection()
        try:
            versions = [
                row["version"]
                for row in conn.execute("SELECT version FROM schema_migrations ORDER BY version")
            ]
            self.assertIn("012_lane_live_periods", versions)
            conn.execute("SELECT 1 FROM lane_live_periods LIMIT 1")
        finally:
            conn.close()

    def test_sequential_lane_turn(self):
        from unittest.mock import patch

        strategy_version = client.get("/api/automation/context").json()["strategy"]["version"]
        lane_b = client.post(
            "/api/admin/lanes",
            json={
                "name": "seq-b",
                "strategy_version": strategy_version,
                "plan_version": "v1",
                "lane_role": "shadow",
            },
            headers={"X-API-Key": "test-key"},
        ).json()["id"]

        with patch("app.config.settings.sequential_lanes", True):
            probe = client.get("/api/automation/context?lane_id=1").json()["lane_turn"]
            due_lane = 1 if probe["granted"] else probe["next_lane_id"]
            waiting_lane = lane_b if due_lane == 1 else 1

            due_ctx = client.get(f"/api/automation/context?lane_id={due_lane}").json()
            self.assertTrue(due_ctx["lane_turn"]["granted"])
            wait_ctx = client.get(f"/api/automation/context?lane_id={waiting_lane}").json()
            self.assertFalse(wait_ctx["lane_turn"]["granted"])

            run_due = client.post(
                "/api/automation/runs",
                json={
                    "cursor_run_id": "seq-lane-due-1",
                    "lane_id": due_lane,
                    "self_critique": "Sequential due lane.",
                    "decisions": [{"symbol": "SPY", "action": "hold", "reason": "Seq due."}],
                },
                headers={"X-API-Key": "test-key"},
            )
            self.assertEqual(run_due.status_code, 200)

            next_ctx = client.get(f"/api/automation/context?lane_id={waiting_lane}").json()
            self.assertTrue(next_ctx["lane_turn"]["granted"])

            post_due_without_turn = client.post(
                "/api/automation/runs",
                json={
                    "cursor_run_id": "seq-lane-wait-fail",
                    "lane_id": due_lane,
                    "self_critique": "Should fail without turn.",
                    "decisions": [{"symbol": "QQQ", "action": "hold", "reason": "No turn."}],
                },
                headers={"X-API-Key": "test-key"},
            )
            self.assertEqual(post_due_without_turn.status_code, 400)

    def test_schema_migration_013(self):
        from app.database import get_connection

        conn = get_connection()
        try:
            versions = [
                row["version"]
                for row in conn.execute("SELECT version FROM schema_migrations ORDER BY version")
            ]
            self.assertIn("013_lane_execution_lock", versions)
            conn.execute("SELECT 1 FROM lane_execution_lock LIMIT 1")
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
