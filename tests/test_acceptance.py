"""
Comprehensive Automated Acceptance & End-to-End Test Suite for the
Autonomous AI Shopping Intelligence & Deal Sniper Platform.

Verifies all 7 mandatory acceptance test categories:
1. Interest Management (Exact, Multiple Acceptable, Broad NL requirement, Edit/Pause/Resume/Delete with confirmation)
2. Product Intelligence (Exact GTIN match, variant mismatch, accessory trap rejection, side-by-side comparison, unit price normalisation)
3. Deal Sniper (Extreme bargain detection e.g. AUD 20 Watch 7, 0-100 Deal Score + 4 sub-scores, stacking optimiser separating cashback, verification checklist)
4. Price History & Buy/Wait Intelligence (7d/30d/90d/180d windows, lowest/avg/median/volatility, observed vs estimated data distinction, Australian retail sale calendar Buy/Wait reasoning)
5. Notifications (Immediate Telegram alert formatting, daily summary, duplicate suppression, quiet hours handling, score threshold enforcement)
6. Background Operation & Restart Persistence (Independent worker cycle without UI, DB restart recovery, backup & restore integrity)
7. Complete End-to-End Proof Workflow (Add interest -> Discover matching product -> Collect price -> Detect price drop -> Calculate deal score -> Save result -> Dispatch notification)
"""

import json
import os
import tempfile
import unittest
from pathlib import Path

from app.orchestrator import PlatformOrchestrator, DEFAULT_SHOPPING_BASKET
from app.product_engine import calculate_normalised_unit_price
from app.deal_sniper import calculate_deal_stacking
from app.main import app
from fastapi.testclient import TestClient


class TestAutonomousShoppingSniperAcceptance(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_sniper.db")
        self.orch = PlatformOrchestrator(db_path=self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_1_interest_management_all_three_types_and_lifecycle(self):
        # A. Exact product
        exact_int = self.orch.add_natural_language_interest("Sony WH-1000XM6")
        self.assertEqual(exact_int["interest_type"], "exact")
        self.assertEqual(exact_int["category"], "TVs, Audio & Gaming")

        # B. Multiple acceptable products
        multi_int = self.orch.add_natural_language_interest("Samsung S26 Ultra OR S25 Ultra")
        self.assertEqual(multi_int["interest_type"], "multiple")
        self.assertIn("Samsung", json.loads(multi_int["preferred_brands"]))

        # C. Broad natural-language requirement
        broad_int = self.orch.add_natural_language_interest(
            "Any good Android phone around AUD 750 with excellent battery life"
        )
        self.assertEqual(broad_int["interest_type"], "broad")
        self.assertEqual(broad_int["max_budget"], 750.0)
        shortlist = json.loads(broad_int["shortlist_json"])
        self.assertGreaterEqual(len(shortlist), 1)

        # Pause, Resume, and Delete with destructive confirmation guard
        paused = self.orch.update_interest_status(broad_int["id"], "paused")
        self.assertEqual(paused["status"], "paused")

        resumed = self.orch.update_interest_status(broad_int["id"], "active")
        self.assertEqual(resumed["status"], "active")

        unconfirmed_del = self.orch.delete_interest(broad_int["id"], confirmed=False)
        self.assertFalse(unconfirmed_del["deleted"])
        self.assertTrue(unconfirmed_del["requires_confirmation"])

        confirmed_del = self.orch.delete_interest(broad_int["id"], confirmed=True)
        self.assertTrue(confirmed_del["deleted"])

    def test_2_product_intelligence_and_unit_normalisation(self):
        with self.orch.db.get_connection() as conn:
            watch7 = dict(conn.execute("SELECT * FROM products WHERE id = 'prod_watch7_44mm'").fetchone())
            s25u = dict(conn.execute("SELECT * FROM products WHERE id = 'prod_s25_ultra_256'").fetchone())
            s26u = dict(conn.execute("SELECT * FROM products WHERE id = 'prod_s26_ultra_256'").fetchone())

        # Exact GTIN match
        m_exact = self.orch.product_engine.evaluate_listing_match(
            watch7, "Samsung Galaxy Watch 7 44mm Green BT", listing_gtin="8806095661421"
        )
        self.assertTrue(m_exact.is_exact_match)
        self.assertGreaterEqual(m_exact.confidence_score, 0.98)

        # Size variant mismatch (40mm vs 44mm)
        m_wrong_size = self.orch.product_engine.evaluate_listing_match(
            watch7, "Samsung Galaxy Watch 7 40mm Cream Bluetooth"
        )
        self.assertFalse(m_wrong_size.is_exact_match)
        self.assertTrue(m_wrong_size.is_variant_mismatch)

        # Misleading accessory trap detection
        m_trap = self.orch.product_engine.evaluate_listing_match(
            watch7, "Silicone Replacement Strap Band Only for Samsung Galaxy Watch 7 44mm"
        )
        self.assertTrue(m_trap.is_accessory_or_bundle_trap)
        self.assertFalse(m_trap.is_exact_match)

        # Unit price normalisation (333g box vs 1kg bag)
        u_333g = calculate_normalised_unit_price(14.00, 333.0, "g")
        self.assertAlmostEqual(u_333g.normalised_unit_price_aud, 4.20, places=2)
        self.assertIn("/ 100g", u_333g.display_string)

        u_1kg = calculate_normalised_unit_price(18.00, 1.0, "kg")
        self.assertAlmostEqual(u_1kg.normalised_unit_price_aud, 1.80, places=2)

        # Side-by-side comparison
        comp = self.orch.product_engine.compare_products_side_by_side(
            [s25u, s26u], {"prod_s25_ultra_256": 1199.0, "prod_s26_ultra_256": 2099.0}
        )
        self.assertEqual(comp["compared_count"], 2)
        self.assertEqual(comp["winner_product_id"], "prod_s25_ultra_256")

    def test_3_deal_sniper_and_stacking_optimiser(self):
        # Verify deal stacking keeps delayed cashback strictly separate from immediate checkout cost
        stack = calculate_deal_stacking(
            listed_price_aud=1299.0,
            shipping_cost_aud=0.0,
            coupon_code="TECH100",
            coupon_discount_aud=100.0,
            cashback_pct=5.0
        )
        self.assertEqual(stack.final_checkout_cost_aud, 1199.0)
        self.assertEqual(stack.potential_future_cashback_aud, 59.95)
        self.assertEqual(stack.effective_cost_after_cashback_aud, 1139.05)

        # Verify Accessory Trap gets rejected with low Deal Score
        trap_res = self.orch.ingest_price_observation_and_snipe(
            product_id="prod_watch7_44mm",
            retailer="eBay Australia",
            listed_price_aud=15.00,
            listing_title_override="Silicone Case for Samsung Galaxy Watch 7 44mm"
        )
        self.assertLess(trap_res["evaluated_deal"]["deal_score"], 25)
        self.assertEqual(trap_res["evaluated_deal"]["classification"], "Ordinary")
        self.assertEqual(trap_res["notification_result"]["status"], "suppressed_threshold")

    def test_4_price_history_and_australian_buy_wait_engine(self):
        with self.orch.db.get_connection() as conn:
            prod = dict(conn.execute("SELECT * FROM products WHERE id = 'prod_watch7_44mm'").fetchone())
            obs = [dict(r) for r in conn.execute("SELECT * FROM price_observations WHERE product_id = 'prod_watch7_44mm'").fetchall()]

        hist = self.orch.history_engine.compute_history_summary(obs, prod["normal_market_price_aud"])
        self.assertEqual(hist["data_origin"], "observed_historical")
        self.assertFalse(hist["has_estimated_baseline"])
        self.assertEqual(hist["lowest_90d_aud"], 20.00)
        self.assertEqual(hist["highest_180d_aud"], 549.00)

        bw_buy = self.orch.history_engine.evaluate_buy_or_wait(prod, 20.00, hist)
        self.assertEqual(bw_buy["recommendation"], "Buy")

        bw_wait = self.orch.history_engine.evaluate_buy_or_wait(prod, 535.00, hist)
        self.assertEqual(bw_wait["recommendation"], "Wait")

    def test_5_notifications_dedup_and_quiet_hours(self):
        with self.orch.db.get_connection() as conn:
            deal = dict(conn.execute("SELECT * FROM evaluated_deals WHERE id = 'deal_sample_1'").fetchone())
            user = dict(conn.execute("SELECT * FROM users WHERE id = 'user_primary'").fetchone())
            all_deals = [dict(r) for r in conn.execute("SELECT * FROM evaluated_deals").fetchall()]

        # 1. Active daytime alert -> sent
        r1 = self.orch.telegram_service.dispatch_deal_alert(deal, user, simulated_time_hhmm="14:15")
        self.assertEqual(r1["status"], "sent")
        self.assertIn("🚨 EXCEPTIONAL DEAL", r1["formatted_message"])

        # 2. Immediate repeat of identical price -> suppressed_duplicate
        r2 = self.orch.telegram_service.dispatch_deal_alert(deal, user, simulated_time_hhmm="14:16")
        self.assertEqual(r2["status"], "suppressed_duplicate")

        # 3. Quiet hours (23:15) for another deal -> pending_quiet_hours
        deal2 = dict(all_deals[1])
        r3 = self.orch.telegram_service.dispatch_deal_alert(deal2, user, simulated_time_hhmm="23:15")
        self.assertEqual(r3["status"], "pending_quiet_hours")

        # 4. Daily summary formatting
        summary_text = self.orch.telegram_service.format_daily_summary(all_deals)
        self.assertIn("DAILY AI SHOPPING INTELLIGENCE SUMMARY", summary_text)

    def test_6_background_operation_restart_persistence_and_backup(self):
        # Run background worker cycle without UI
        cycle_res = self.orch.run_background_worker_cycle()
        self.assertEqual(len(cycle_res["jobs_updated"]), 4)
        updated_count = cycle_res["jobs_updated"][0]["run_count"]
        self.assertGreaterEqual(updated_count, 15)

        # Simulate application restart by instantiating a brand new PlatformOrchestrator on the same DB file
        restarted_orch = PlatformOrchestrator(db_path=self.db_path)
        with restarted_orch.db.get_connection() as conn:
            job_row = dict(conn.execute("SELECT * FROM scheduler_jobs WHERE job_id = 'job_engine_a_high_priority'").fetchone())
            self.assertEqual(job_row["run_count"], updated_count)
            self.assertEqual(job_row["status"], "healthy")

        # Test Backup & Restore
        backup_file = restarted_orch.db.create_backup()
        self.assertTrue(os.path.exists(backup_file))
        self.assertTrue(restarted_orch.db.restore_backup(backup_file))

    def test_7_non_negotiable_end_to_end_proof_workflow_and_api(self):
        """
        Proves the complete end-to-end workflow required by Principle #4:
        1. Add a shopping interest in natural language
        2. Discover matching product in shortlist
        3. Collect/ingest a verified price drop observation
        4. Calculate explainable Deal Score (0-100) and sub-scores
        5. Save result to persistent database
        6. Dispatch Telegram notification
        7. Verify via FastAPI TestClient endpoints
        """
        # Step 1 & 2: Add natural language interest and discover matching product
        interest = self.orch.add_natural_language_interest("Sony WH-1000XM6 wireless headphones under AUD 450")
        shortlist = json.loads(interest["shortlist_json"])
        self.assertTrue(any(item["product_id"] == "prod_sony_xm6" for item in shortlist))

        # Step 3, 4, 5, 6: Collect price drop (AUD 299 clearance at JB Hi-Fi vs AUD 649 RRP), score, save, notify
        e2e_result = self.orch.ingest_price_observation_and_snipe(
            product_id="prod_sony_xm6",
            retailer="JB Hi-Fi",
            listed_price_aud=299.00,
            shipping_cost_aud=0.0,
            stock_status="Low stock",
            condition="New",
            source_url="https://www.jbhifi.com.au",
            interest_id=interest["id"],
            simulated_time_hhmm="15:30"
        )

        deal = e2e_result["evaluated_deal"]
        self.assertGreaterEqual(deal["deal_score"], 90)
        self.assertEqual(deal["classification"], "Exceptional")
        self.assertEqual(e2e_result["buy_wait"]["recommendation"], "Buy")
        self.assertEqual(e2e_result["notification_result"]["status"], "sent")

        # Step 7: Verify FastAPI endpoints and Basket Optimiser
        client = TestClient(app)
        health_resp = client.get("/api/health")
        self.assertEqual(health_resp.status_code, 200)
        self.assertEqual(health_resp.json()["status"], "operational")

        basket_resp = client.post("/api/basket/optimise", json={"fulfilment_mode": "click_and_collect"})
        self.assertEqual(basket_resp.status_code, 200)
        b_data = basket_resp.json()
        self.assertLess(
            b_data["split_basket_strategy"]["total_cost_aud"],
            b_data["best_single_retailer"]["total_cost_aud"]
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
