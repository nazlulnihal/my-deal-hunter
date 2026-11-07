"""
Historical Price Tracking (7d, 30d, 90d, 180d), Volatility Metrics,
and Australian Retail Calendar Buy/Wait Lifecycle Intelligence Engine.
"""

import statistics
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional


AUSTRALIAN_SALE_CALENDAR = [
    {"name": "Click Frenzy Main Event", "month": 11, "day": 12, "typical_discount_pct": 20, "categories": ["All"]},
    {"name": "Black Friday Australia", "month": 11, "day": 27, "typical_discount_pct": 30, "categories": ["All"]},
    {"name": "Cyber Monday Australia", "month": 11, "day": 30, "typical_discount_pct": 28, "categories": ["Smartphones, Smartwatches & Tablets", "Computers & Electronics", "TVs, Audio & Gaming"]},
    {"name": "Christmas Pre-Holiday Clearance", "month": 12, "day": 18, "typical_discount_pct": 22, "categories": ["Groceries, Chocolates & Beverages", "Baby Products, Toys, Books & Gifts"]},
    {"name": "Boxing Day National Sales", "month": 12, "day": 26, "typical_discount_pct": 32, "categories": ["All"]},
    {"name": "Mother's Day Promotions", "month": 5, "day": 10, "typical_discount_pct": 20, "categories": ["Personal Care, Skincare & Cosmetics", "Home Appliances & Coffee Machines"]},
    {"name": "EOFY (End of Financial Year) Tax Time Sales", "month": 6, "day": 15, "typical_discount_pct": 30, "categories": ["Computers & Electronics", "Smartphones, Smartwatches & Tablets", "Hardware, Tools & Gardening", "Home Appliances & Coffee Machines"]},
    {"name": "Amazon Prime Day Australia", "month": 7, "day": 14, "typical_discount_pct": 28, "categories": ["All"]},
    {"name": "Father's Day Promotions", "month": 9, "day": 6, "typical_discount_pct": 18, "categories": ["Hardware, Tools & Gardening", "TVs, Audio & Gaming"]},
]


class PriceHistoryAndBuyWaitEngine:
    """
    Computes 7-day, 30-day, 90-day, and 180-day price history metrics,
    explicitly distinguishes observed historical records from estimated baselines,
    and generates an explainable Buy / Consider / Wait recommendation grounded in
    Australian promotional cycles and product lifecycle stage.
    """

    def compute_history_summary(
        self,
        observations: List[Dict[str, Any]],
        normal_market_price_aud: float,
        reference_now: Optional[datetime] = None
    ) -> Dict[str, Any]:
        now = reference_now or datetime.now(timezone.utc)
        parsed_obs = []
        for obs in observations:
            try:
                ts_str = obs["observed_at"]
                dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                parsed_obs.append((dt, float(obs["listed_price_aud"]), obs))
            except Exception:
                continue

        parsed_obs.sort(key=lambda x: x[0])

        def window_prices(days: int) -> List[float]:
            cutoff = now - timedelta(days=days)
            return [p for dt, p, _ in parsed_obs if dt >= cutoff]

        p7 = window_prices(7)
        p30 = window_prices(30)
        p90 = window_prices(90)
        p180 = window_prices(180)
        all_prices = [p for _, p, _ in parsed_obs]

        has_sufficient_observed = len(all_prices) >= 3
        data_origin = "observed_historical" if has_sufficient_observed else "limited_observed_with_market_baseline"

        active_pool = p180 if p180 else (all_prices if all_prices else [normal_market_price_aud])
        lowest_obs = round(min(active_pool), 2)
        highest_obs = round(max(active_pool), 2)
        avg_obs = round(statistics.mean(active_pool), 2)
        median_obs = round(statistics.median(active_pool), 2)
        stdev_obs = round(statistics.stdev(active_pool), 2) if len(active_pool) >= 2 else 0.0
        volatility_pct = round((stdev_obs / avg_obs) * 100.0, 1) if avg_obs > 0 else 0.0

        # Trend analysis
        if len(parsed_obs) >= 2:
            latest_price = parsed_obs[-1][1]
            prev_price = parsed_obs[-2][1]
            if latest_price < prev_price * 0.96:
                trend = "falling"
            elif latest_price > prev_price * 1.04:
                trend = "rising"
            else:
                trend = "stable"
        else:
            trend = "stable"

        return {
            "observation_count": len(parsed_obs),
            "data_origin": data_origin,
            "has_estimated_baseline": not has_sufficient_observed,
            "lowest_7d_aud": round(min(p7), 2) if p7 else lowest_obs,
            "lowest_30d_aud": round(min(p30), 2) if p30 else lowest_obs,
            "lowest_90d_aud": round(min(p90), 2) if p90 else lowest_obs,
            "lowest_180d_aud": lowest_obs,
            "highest_180d_aud": highest_obs,
            "average_90d_aud": round(statistics.mean(p90), 2) if p90 else avg_obs,
            "average_180d_aud": avg_obs,
            "median_180d_aud": median_obs,
            "volatility_stdev_aud": stdev_obs,
            "volatility_pct": volatility_pct,
            "volatility_classification": "High" if volatility_pct >= 15.0 else ("Moderate" if volatility_pct >= 6.0 else "Low"),
            "current_trend": trend,
            "series": [
                {
                    "timestamp": dt.strftime("%Y-%m-%d"),
                    "price_aud": round(p, 2),
                    "retailer": o["retailer"],
                    "is_sample_data": bool(o.get("is_sample_data", 0))
                }
                for dt, p, o in parsed_obs
            ]
        }

    def evaluate_buy_or_wait(
        self,
        product: Dict[str, Any],
        current_price_aud: float,
        history_summary: Dict[str, Any],
        reference_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Determines whether the user should Buy Now, Consider, or Wait based on:
        - Distance from 90-day / 180-day observed low
        - Upcoming Australian retail sale events (e.g. Black Friday, Click Frenzy, Boxing Day, EOFY)
        - Product lifecycle stage (e.g., new model imminent vs previous-gen clearance sweet spot)
        Never presents a price prediction as a guarantee.
        """
        now = reference_date or datetime(2026, 11, 7, tzinfo=timezone.utc)
        normal_price = float(product["normal_market_price_aud"])
        lowest_90d = float(history_summary.get("lowest_90d_aud", normal_price))
        avg_90d = float(history_summary.get("average_90d_aud", normal_price))
        lifecycle = product.get("lifecycle_stage", "current")
        discount_pct = ((normal_price - current_price_aud) / normal_price) * 100.0 if normal_price > 0 else 0.0

        # Check upcoming Australian sale events within the next 30 days
        upcoming_events = []
        for ev in AUSTRALIAN_SALE_CALENDAR:
            try:
                ev_date = datetime(now.year, ev["month"], ev["day"], tzinfo=timezone.utc)
                if ev_date < now:
                    ev_date = datetime(now.year + 1, ev["month"], ev["day"], tzinfo=timezone.utc)
                days_away = (ev_date - now).days
                if 0 <= days_away <= 35:
                    if "All" in ev["categories"] or product["category"] in ev["categories"]:
                        upcoming_events.append({
                            "name": ev["name"],
                            "days_away": days_away,
                            "typical_discount_pct": ev["typical_discount_pct"]
                        })
            except ValueError:
                continue

        upcoming_events.sort(key=lambda x: x["days_away"])
        nearest_event = upcoming_events[0] if upcoming_events else None

        if current_price_aud <= lowest_90d * 1.02 and discount_pct >= 25.0:
            decision = "Buy"
            confidence = "High (88%)"
            reasoning = (
                f"BUY NOW: Current price (AUD {current_price_aud:.2f}) is at or below the 90-day observed floor "
                f"(AUD {lowest_90d:.2f}) and {discount_pct:.0f}% under typical Australian retail value (AUD {normal_price:.0f}). "
                f"Even with {nearest_event['name'] if nearest_event else 'seasonal sales'} approaching, historical data shows "
                f"this tier of markdown rarely drops further before stock sells out. (Note: historical analysis is probabilistic, not a guarantee.)"
            )
        elif discount_pct >= 15.0 or (lifecycle == "previous_gen_value" and current_price_aud < avg_90d):
            decision = "Consider"
            confidence = "Moderate-High (76%)"
            event_note = (
                f" {nearest_event['name']} is in {nearest_event['days_away']} days, which historically brings "
                f"~{nearest_event['typical_discount_pct']}% category promotions, though stock on clearance lines may tighten."
                if nearest_event else ""
            )
            reasoning = (
                f"CONSIDER BUYING: Solid {discount_pct:.0f}% discount below market (90-day average: AUD {avg_90d:.2f})."
                f"{event_note} Worth purchasing now if needed immediately, or setting a target alert at AUD {lowest_90d:.2f}."
            )
        else:
            decision = "Wait"
            confidence = "High (84%)"
            event_note = (
                f"Wait for {nearest_event['name']} ({nearest_event['days_away']} days away) where typical category reductions reach ~{nearest_event['typical_discount_pct']}%."
                if nearest_event else "Wait for the next promotional cycle; current price is near full retail."
            )
            reasoning = (
                f"WAIT: Current price (AUD {current_price_aud:.2f}) is above the 90-day observed low of AUD {lowest_90d:.2f} "
                f"(only {max(0.0, discount_pct):.0f}% off RRP). {event_note} (Historical patterns are estimates, not guaranteed future prices.)"
            )

        return {
            "recommendation": decision,
            "confidence": confidence,
            "reasoning": reasoning,
            "nearest_sale_event": nearest_event,
            "lifecycle_stage": lifecycle,
            "successor_note": (
                f"Successor model ({product.get('successor_model')}) is active, driving end-of-line markdowns on this model."
                if product.get("successor_model") else "Current generation line."
            )
        }
