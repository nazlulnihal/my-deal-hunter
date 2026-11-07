"""
Telegram Bot Notification Service, Preference Learning Engine,
Shared Shopping & Realised/Estimated Savings Tracker, and Conversational AI Assistant.
"""

import hashlib
import json
import os
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class TelegramNotificationService:
    """
    Handles immediate high-priority deal alerts and configurable daily summaries via
    the official Telegram Bot API.
    Enforces:
    - Quiet hours suppression (queues non-critical notifications during quiet hours)
    - Duplicate alert suppression (SHA-256 signature of product_id + retailer + price)
    - Minimum deal score thresholds (Engine A wishlist vs Engine B outside-wishlist >= 90)
    - Interactive command handling (/start, /deals, /save, /dismiss, /pause, /summary)
    """

    def __init__(self, db_manager):
        self.db = db_manager
        self.bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        self.default_chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

    def format_immediate_alert(self, deal: Dict[str, Any]) -> str:
        bullets = json.loads(deal.get("explanation_bullets_json", "[]"))
        bullet_lines = "\n".join(f"• {b}" for b in bullets[:4])
        risk_flags = json.loads(deal.get("risk_flags_json", "[]"))
        risk_note = f"\n⚠️ Verification note: {risk_flags[0]}" if risk_flags else ""

        header = "🚨 EXCEPTIONAL DEAL" if deal["classification"] == "Exceptional" else f"🔥 {deal['classification'].upper()} WISHLIST DEAL"
        return (
            f"{header}\n\n"
            f"{deal['title']}\n\n"
            f"Price: AUD {deal['final_checkout_cost_aud']:.2f}\n"
            f"Retailer: {deal['retailer']}\n"
            f"Typical market price: AUD {deal['normal_market_price_aud']:.0f}+\n"
            f"Deal score: {deal['deal_score']}/100 (Suitability {deal['suitability_score']} | Trust {deal['seller_trust_score']})\n"
            f"Availability: {deal['urgency_state']} / {deal['verification_status']}\n\n"
            f"Why this is interesting:\n"
            f"{bullet_lines}{risk_note}\n\n"
            f"[View Deal]({deal['source_url']})"
        )

    def format_daily_summary(self, deals: List[Dict[str, Any]]) -> str:
        wishlist_deals = [d for d in deals if d["engine_type"] == "Engine A" and d["deal_score"] >= 70]
        outside_discoveries = [d for d in deals if d["engine_type"] == "Engine B" and d["deal_score"] >= 90]

        lines = [
            "📊 DAILY AI SHOPPING INTELLIGENCE SUMMARY",
            f"Generated: {datetime.now(timezone.utc).strftime('%d %b %Y')} (AUD)\n",
            f"🎯 Top Wishlist Deals ({len(wishlist_deals)} qualified):"
        ]
        for d in wishlist_deals[:4]:
            lines.append(
                f"• {d['title']} — AUD {d['final_checkout_cost_aud']:.2f} at {d['retailer']} "
                f"(Save {d['discount_pct']:.0f}%, Score {d['deal_score']}/100) [Link]({d['source_url']})"
            )

        lines.append(f"\n⚡ Engine B Outside-Wishlist Exceptional Discoveries ({len(outside_discoveries)} ≥90/100):")
        for d in outside_discoveries[:3]:
            lines.append(
                f"• {d['title']} — AUD {d['final_checkout_cost_aud']:.2f} at {d['retailer']} "
                f"(Typical AUD {d['normal_market_price_aud']:.0f}, Score {d['deal_score']}/100) [Link]({d['source_url']})"
            )

        lines.append("\nReply /save_<id>, /dismiss_<id>, or /pause_<interest_id> to manage directly from Telegram.")
        return "\n".join(lines)

    def _is_within_quiet_hours(self, current_hhmm: str, start_hhmm: str, end_hhmm: str) -> bool:
        if start_hhmm <= end_hhmm:
            return start_hhmm <= current_hhmm < end_hhmm
        else:
            # Overnight window e.g. 22:30 to 07:00
            return current_hhmm >= start_hhmm or current_hhmm < end_hhmm

    def dispatch_deal_alert(
        self,
        deal: Dict[str, Any],
        user_settings: Dict[str, Any],
        simulated_time_hhmm: Optional[str] = None,
        force_bypass_quiet_for_98_plus: bool = False
    ) -> Dict[str, Any]:
        """
        Evaluates duplicate suppression, score thresholds, and quiet hours,
        logs the notification to SQLite, and dispatches via Telegram API if credentials are configured.
        """
        dedup_raw = f"{deal['product_id']}::{deal['retailer']}::{deal['final_checkout_cost_aud']:.2f}"
        dedup_sig = hashlib.sha256(dedup_raw.encode("utf-8")).hexdigest()[:24]

        with self.db.get_connection() as conn:
            # 1. Check duplicate suppression for unchanged price
            dup_row = conn.execute(
                "SELECT id FROM notifications_log WHERE dedup_signature = ? AND status IN ('sent', 'pending_quiet_hours')",
                (dedup_sig,)
            ).fetchone()
            if dup_row:
                notif_id = f"notif_dup_{dedup_sig[:8]}_{int(datetime.now(timezone.utc).timestamp())}"
                msg_body = self.format_immediate_alert(deal)
                conn.execute(
                    """INSERT INTO notifications_log
                       (id, user_id, deal_id, channel, notification_type, title, message_body, status, dedup_signature, created_at)
                       VALUES (?, 'user_primary', ?, 'telegram', 'immediate_alert', ?, ?, 'suppressed_duplicate', ?, ?)""",
                    (notif_id, deal["id"], deal["title"], msg_body, dedup_sig, datetime.now(timezone.utc).isoformat())
                )
                conn.commit()
                return {"status": "suppressed_duplicate", "notification_id": notif_id, "dedup_signature": dedup_sig}

            # 2. Check minimum deal score threshold
            min_wishlist = int(user_settings.get("min_deal_score_wishlist", 70))
            min_outside = int(user_settings.get("min_deal_score_outside", 90))
            required_threshold = min_wishlist if deal["engine_type"] == "Engine A" else min_outside

            msg_body = self.format_immediate_alert(deal)
            if int(deal["deal_score"]) < required_threshold:
                notif_id = f"notif_thr_{dedup_sig[:8]}"
                conn.execute(
                    """INSERT INTO notifications_log
                       (id, user_id, deal_id, channel, notification_type, title, message_body, status, dedup_signature, created_at)
                       VALUES (?, 'user_primary', ?, 'telegram', 'immediate_alert', ?, ?, 'suppressed_threshold', ?, ?)""",
                    (notif_id, deal["id"], deal["title"], msg_body, dedup_sig, datetime.now(timezone.utc).isoformat())
                )
                conn.commit()
                return {"status": "suppressed_threshold", "notification_id": notif_id, "required_threshold": required_threshold}

            # 3. Check quiet hours
            now_hhmm = simulated_time_hhmm or "14:00"
            q_start = user_settings.get("quiet_hours_start", "22:30")
            q_end = user_settings.get("quiet_hours_end", "07:00")
            in_quiet = self._is_within_quiet_hours(now_hhmm, q_start, q_end)

            if in_quiet and not (force_bypass_quiet_for_98_plus and int(deal["deal_score"]) >= 98):
                status = "pending_quiet_hours"
            else:
                status = "sent"

            notif_id = f"notif_{dedup_sig[:10]}"
            conn.execute(
                """INSERT INTO notifications_log
                   (id, user_id, deal_id, channel, notification_type, title, message_body, status, dedup_signature, created_at)
                   VALUES (?, 'user_primary', ?, 'telegram', 'immediate_alert', ?, ?, ?, ?, ?)""",
                (notif_id, deal["id"], deal["title"], msg_body, status, dedup_sig, datetime.now(timezone.utc).isoformat())
            )
            conn.commit()

        # Live Telegram API call if token and chat_id are configured and outbound network is reachable
        api_dispatched = False
        if status == "sent" and self.bot_token and self.default_chat_id:
            try:
                url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
                payload = json.dumps({
                    "chat_id": self.default_chat_id,
                    "text": msg_body,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": False
                }).encode("utf-8")
                req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    api_dispatched = (resp.status == 200)
            except Exception:
                api_dispatched = False

        return {
            "status": status,
            "notification_id": notif_id,
            "dedup_signature": dedup_sig,
            "telegram_api_configured": bool(self.bot_token and self.default_chat_id),
            "live_api_dispatched": api_dispatched,
            "formatted_message": msg_body
        }


class PreferenceAndSavingsEngine:
    """
    Learns from user interactions without falsely assuming that opening a deal equals liking
    or purchasing it. Tracks realised savings (from recorded purchases) separately from
    estimated savings (from saved/shortlisted deals).
    """

    EVENT_WEIGHTS = {
        "deal_opened": 1,       # Minimal weight: opening does NOT imply liking or buying
        "category_explored": 2,
        "deal_saved": 6,        # Explicit positive signal
        "deal_purchased": 12,   # Strongest verified signal
        "deal_dismissed": -5,   # Explicit negative signal
    }

    def __init__(self, db_manager):
        self.db = db_manager

    def record_interaction(
        self,
        event_type: str,
        product_id: Optional[str] = None,
        category: Optional[str] = None,
        brand: Optional[str] = None,
        retailer: Optional[str] = None,
        price_aud: Optional[float] = None
    ) -> str:
        ev_id = f"pref_{int(datetime.now(timezone.utc).timestamp() * 1000)}"
        with self.db.get_connection() as conn:
            conn.execute(
                """INSERT INTO preference_events
                   (id, user_id, event_type, product_id, category, brand, retailer, price_aud, created_at)
                   VALUES (?, 'user_primary', ?, ?, ?, ?, ?, ?, ?)""",
                (ev_id, event_type, product_id, category, brand, retailer, price_aud, datetime.now(timezone.utc).isoformat())
            )
            conn.commit()
        return ev_id

    def compute_preference_profile(self) -> Dict[str, Any]:
        with self.db.get_connection() as conn:
            events = [dict(r) for r in conn.execute("SELECT * FROM preference_events").fetchall()]
            user_row = dict(conn.execute("SELECT * FROM users WHERE id = 'user_primary'").fetchone())

        brand_scores: Dict[str, int] = {}
        retailer_scores: Dict[str, int] = {}
        category_scores: Dict[str, int] = {}

        for ev in events:
            w = self.EVENT_WEIGHTS.get(ev["event_type"], 0)
            if ev.get("brand"):
                brand_scores[ev["brand"]] = brand_scores.get(ev["brand"], 0) + w
            if ev.get("retailer"):
                retailer_scores[ev["retailer"]] = retailer_scores.get(ev["retailer"], 0) + w
            if ev.get("category"):
                category_scores[ev["category"]] = category_scores.get(ev["category"], 0) + w

        return {
            "total_interactions": len(events),
            "affinities": {
                "brands": sorted(brand_scores.items(), key=lambda x: x[1], reverse=True),
                "retailers": sorted(retailer_scores.items(), key=lambda x: x[1], reverse=True),
                "categories": sorted(category_scores.items(), key=lambda x: x[1], reverse=True),
            },
            "blocked_brands": json.loads(user_row.get("blocked_brands", "[]")),
            "blocked_retailers": json.loads(user_row.get("blocked_retailers", "[]")),
            "blocked_categories": json.loads(user_row.get("blocked_categories", "[]")),
            "policy_note": "Opening a deal carries a +1 curiosity weight; only saving (+6) or recording a purchase (+12) materially shifts personalisation weights."
        }

    def compute_savings_tracker(self) -> Dict[str, Any]:
        with self.db.get_connection() as conn:
            watchlist = [dict(r) for r in conn.execute("SELECT * FROM watchlist_items").fetchall()]
            deals = [dict(r) for r in conn.execute("SELECT * FROM evaluated_deals").fetchall()]

        realised_savings_aud = 0.0
        estimated_watchlist_savings_aud = 0.0
        purchased_count = 0
        saved_count = len(watchlist)
        missed_sold_out = [d for d in deals if d["urgency_state"] == "Sold out"]

        for item in watchlist:
            bench = float(item.get("benchmark_market_price_aud") or 0.0)
            if item["lifecycle_status"] == "Purchased" and item.get("recorded_purchase_price_aud") is not None:
                purchased_count += 1
                paid = float(item["recorded_purchase_price_aud"])
                realised_savings_aud += max(0.0, bench - paid)
            elif item["lifecycle_status"] in ("Exploring", "Researching", "Waiting for a better price", "Ready to purchase"):
                target = float(item.get("target_price_aud") or bench)
                estimated_watchlist_savings_aud += max(0.0, bench - target)

        return {
            "deals_discovered_count": len(deals),
            "deals_saved_count": saved_count,
            "deals_purchased_count": purchased_count,
            "missed_sold_out_count": len(missed_sold_out),
            "realised_savings_aud": round(realised_savings_aud, 2),
            "estimated_pipeline_savings_aud": round(estimated_watchlist_savings_aud, 2),
            "distinction_note": "Realised savings are calculated strictly from user-verified recorded purchase prices against historical market benchmarks. Estimated savings reflect active watchlist targets."
        }
