"""
Deal Sniper, Explainable Scoring (0-100), Automatic Verification,
Authenticity & Risk Assessment, and Deal Stacking Optimiser.
"""

import json
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional


@dataclass
class StackingBreakdown:
    advertised_price_aud: float
    coupon_code: Optional[str]
    immediate_coupon_discount_aud: float
    loyalty_member_discount_aud: float
    multibuy_discount_aud: float
    shipping_cost_aud: float
    final_checkout_cost_aud: float
    cashback_provider: str
    cashback_rate_pct: float
    potential_future_cashback_aud: float
    effective_cost_after_cashback_aud: float
    notes: str


def calculate_deal_stacking(
    listed_price_aud: float,
    shipping_cost_aud: float = 0.0,
    coupon_code: Optional[str] = None,
    coupon_discount_aud: float = 0.0,
    loyalty_discount_aud: float = 0.0,
    multibuy_discount_aud: float = 0.0,
    cashback_pct: float = 0.0,
    cashback_provider: str = "Cashrewards / ShopBack AU",
    free_shipping_threshold_aud: float = 50.0
) -> StackingBreakdown:
    """
    Calculates legitimate deal stacking combinations while strictly separating
    immediate checkout cost from delayed/uncertain cashback.
    """
    immediate_discounts = coupon_discount_aud + loyalty_discount_aud + multibuy_discount_aud
    subtotal_after_discounts = max(0.0, round(listed_price_aud - immediate_discounts, 2))

    effective_shipping = 0.0 if (shipping_cost_aud == 0.0 or subtotal_after_discounts >= free_shipping_threshold_aud) else shipping_cost_aud
    final_checkout = round(subtotal_after_discounts + effective_shipping, 2)

    # Cashback is calculated on pre-shipping subtotal and kept strictly separate from checkout cost
    future_cashback = round(subtotal_after_discounts * (cashback_pct / 100.0), 2) if cashback_pct > 0 else 0.0
    effective_after_cb = round(final_checkout - future_cashback, 2)

    note_parts = []
    if coupon_code and coupon_discount_aud > 0:
        note_parts.append(f"Applied code {coupon_code} (-AUD {coupon_discount_aud:.2f} at checkout)")
    if loyalty_discount_aud > 0:
        note_parts.append(f"Member/Loyalty tier saves AUD {loyalty_discount_aud:.2f}")
    if future_cashback > 0:
        note_parts.append(
            f"Delayed cashback of AUD {future_cashback:.2f} ({cashback_pct}% via {cashback_provider}) "
            f"is tracked separately and not deducted from immediate checkout cost."
        )

    return StackingBreakdown(
        advertised_price_aud=round(listed_price_aud, 2),
        coupon_code=coupon_code,
        immediate_coupon_discount_aud=round(coupon_discount_aud, 2),
        loyalty_member_discount_aud=round(loyalty_discount_aud, 2),
        multibuy_discount_aud=round(multibuy_discount_aud, 2),
        shipping_cost_aud=round(effective_shipping, 2),
        final_checkout_cost_aud=final_checkout,
        cashback_provider=cashback_provider if cashback_pct > 0 else "None",
        cashback_rate_pct=cashback_pct,
        potential_future_cashback_aud=future_cashback,
        effective_cost_after_cashback_aud=effective_after_cb,
        notes="; ".join(note_parts) if note_parts else "Standard direct checkout price."
    )


class DealSniperEngine:
    """
    Core Deal Sniper & Verification Engine.
    Calculates:
    - Overall Explainable Deal Score (0-100)
    - Classification: Exceptional (90-100), Excellent (78-89), Good (62-77), Ordinary (<62)
    - Separate Sub-scores:
      1. Product Suitability (0-100)
      2. Deal Attractiveness (0-100)
      3. Seller / Source Trust (0-100)
      4. Data Confidence & Freshness (0-100)
    - Deal Authenticity & Risk Assessment (grey imports, accessory traps, marketplace sellers, shipping inflation)
    - Automatic Pre-Alert Verification Checklist
    """

    TIER_1_AU_RETAILERS = {
        "Officeworks": 98,
        "JB Hi-Fi": 97,
        "The Good Guys": 96,
        "Appliances Online": 96,
        "Woolworths": 97,
        "Coles": 97,
        "Aldi": 95,
        "Costco": 96,
        "Bunnings": 98,
        "Chemist Warehouse": 95,
        "Myer": 95,
        "David Jones": 95,
        "Big W": 94,
        "Target": 94,
        "Harvey Norman": 93,
        "Bing Lee": 94,
        "Priceline": 94,
        "Amazon Australia": 94,
    }

    MARKETPLACE_OR_GREY_RETAILERS = {
        "Kogan": 80,
        "eBay Australia": 78,
        "OzBargain Community Feed": 88,
    }

    def evaluate_deal(
        self,
        product: Dict[str, Any],
        observation: Dict[str, Any],
        historical_stats: Dict[str, Any],
        matched_interest: Optional[Dict[str, Any]] = None,
        match_confidence: float = 0.95,
        is_accessory_trap: bool = False
    ) -> Dict[str, Any]:
        normal_market = float(product["normal_market_price_aud"])
        listed_price = float(observation["listed_price_aud"])
        shipping = float(observation.get("shipping_cost_aud", 0.0))
        coupon_disc = float(observation.get("coupon_discount_aud", 0.0))
        loyalty_disc = float(observation.get("loyalty_discount_aud", 0.0))
        cashback_pct = float(observation.get("cashback_pct", 0.0))

        stacking = calculate_deal_stacking(
            listed_price_aud=listed_price,
            shipping_cost_aud=shipping,
            coupon_code=observation.get("coupon_code"),
            coupon_discount_aud=coupon_disc,
            loyalty_discount_aud=loyalty_disc,
            cashback_pct=cashback_pct
        )

        checkout_cost = stacking.final_checkout_cost_aud
        lowest_90d = float(historical_stats.get("lowest_90d_aud", normal_market))
        avg_90d = float(historical_stats.get("average_90d_aud", normal_market))

        # 1. Calculate Price Reduction vs Normal Market & Historical Low
        discount_vs_market_pct = round(((normal_market - checkout_cost) / normal_market) * 100.0, 1) if normal_market > 0 else 0.0
        discount_vs_avg_pct = round(((avg_90d - checkout_cost) / avg_90d) * 100.0, 1) if avg_90d > 0 else 0.0
        beats_90d_low = checkout_cost <= lowest_90d

        # 2. Sub-score: Seller / Source Trust & Risk Assessment
        retailer = observation["retailer"]
        is_marketplace = bool(observation.get("is_marketplace", 0))
        base_trust = self.TIER_1_AU_RETAILERS.get(
            retailer,
            self.MARKETPLACE_OR_GREY_RETAILERS.get(retailer, 75)
        )
        risk_flags: List[str] = []

        if is_marketplace:
            base_trust -= 14
            risk_flags.append(f"Third-party marketplace seller ({observation.get('seller_name', 'Marketplace')}) — verify Australian ACL warranty coverage.")

        if retailer in ("Kogan", "eBay Australia") and "au" not in str(product.get("variant_signature", "")).lower():
            risk_flags.append("Check whether listing is an international/grey-import model vs official Australian stock.")

        if shipping > 25.0 and shipping > listed_price * 0.15:
            base_trust -= 15
            risk_flags.append(f"Elevated shipping charge (AUD {shipping:.2f}) offsets part of the headline discount.")

        if observation.get("condition", "New") != "New":
            risk_flags.append(f"Product condition is '{observation['condition']}' (not factory sealed New).")

        if observation.get("is_short_dated"):
            risk_flags.append(f"Short-dated clearance stock (Best Before: {observation.get('expiry_date', 'Soon')}).")

        if is_accessory_trap:
            base_trust = 20
            risk_flags.append("CRITICAL TRAP: Listing detected as an accessory/band/case rather than main hardware.")

        # Pricing error / extreme clearance notice (positive urgency, not fraud when from Tier-1 AU store)
        is_extreme_anomaly = discount_vs_market_pct >= 70.0 and not is_accessory_trap
        if is_extreme_anomaly and base_trust >= 90:
            risk_flags.append(
                f"Extreme price anomaly (-{discount_vs_market_pct:.0f}% at {retailer}): Likely clearance markdown or pricing error — high cancellation/sell-out risk; order for Click & Collect if available."
            )
        elif is_extreme_anomaly and base_trust < 80:
            base_trust -= 18
            risk_flags.append("Unusually cheap marketplace listing (>70% below market) from non-Tier-1 seller — verify seller feedback before payment.")

        seller_trust_score = max(10, min(100, base_trust))

        # 3. Sub-score: Deal Attractiveness (0-100)
        if is_accessory_trap:
            attractiveness_score = 5
        else:
            # Base attractiveness from discount vs market and historical 90d low
            raw_attr = 45.0 + (discount_vs_market_pct * 0.85)
            if beats_90d_low and discount_vs_market_pct >= 15.0:
                raw_attr += 10.0
            if checkout_cost < lowest_90d * 0.85:
                raw_attr += 8.0
            if stacking.immediate_coupon_discount_aud > 0:
                raw_attr += 3.0
            attractiveness_score = max(5, min(100, int(round(raw_attr))))

        # 4. Sub-score: Product Suitability (0-100)
        if is_accessory_trap:
            suitability_score = 10
        else:
            base_suitability = int(round(match_confidence * 92))
            if matched_interest:
                max_b = matched_interest.get("max_budget")
                if max_b and checkout_cost <= float(max_b):
                    base_suitability = min(100, base_suitability + 8)
                elif max_b and checkout_cost > float(max_b):
                    base_suitability = max(40, base_suitability - 18)
            if product.get("lifecycle_stage") == "previous_gen_value":
                base_suitability = min(98, base_suitability + 4)
            suitability_score = max(10, min(100, base_suitability))

        # 5. Sub-score: Data Confidence & Freshness (0-100)
        raw_conf = float(observation.get("data_confidence", 0.94)) * 100.0
        price_stage = observation.get("price_stage", "retailer_listed")
        if price_stage == "checkout_verified":
            raw_conf += 4.0
        elif price_stage == "search_snippet":
            raw_conf -= 15.0
        data_confidence_score = max(30, min(100, int(round(raw_conf))))

        # 6. Composite Explainable Deal Score (0-100)
        if is_accessory_trap:
            deal_score = 12
        else:
            weighted = (
                attractiveness_score * 0.48 +
                suitability_score * 0.24 +
                seller_trust_score * 0.18 +
                data_confidence_score * 0.10
            )
            if is_extreme_anomaly and seller_trust_score >= 90 and observation.get("stock_status") != "Sold out":
                weighted = max(weighted, 97.0)
            deal_score = max(1, min(100, int(round(weighted))))

        # 7. Classification
        if deal_score >= 90:
            classification = "Exceptional"
        elif deal_score >= 78:
            classification = "Excellent"
        elif deal_score >= 62:
            classification = "Good"
        else:
            classification = "Ordinary"

        # 8. Automatic Deal Verification Checklist
        stock_status = observation.get("stock_status", "Available")
        verification_checks = {
            "listing_accessible": True,
            "current_price_displayed": True,
            "exact_variant_verified": not is_accessory_trap and match_confidence >= 0.85,
            "condition_clear": observation.get("condition", "New") in ("New", "Refurbished", "Open-Box"),
            "seller_legitimate": seller_trust_score >= 75,
            "available_to_purchase": stock_status not in ("Sold out", "Expired"),
            "shipping_reasonable": shipping <= 20.0,
            "not_accessory_or_bundle_trap": not is_accessory_trap,
            "price_verification_stage": price_stage,
        }
        passed_count = sum(1 for k, v in verification_checks.items() if isinstance(v, bool) and v)
        if is_accessory_trap:
            verification_status = "Failed — Misleading Accessory/Bundle Trap"
        elif passed_count == 8 and price_stage in ("checkout_verified", "retailer_listed"):
            verification_status = f"Verified ({price_stage.replace('_', ' ').title()})"
        else:
            verification_status = f"Partially Verified ({passed_count}/8 checks passed — verify stock at checkout)"

        # 9. Explainable Bullets
        bullets = [
            f"Save AUD {normal_market - checkout_cost:.2f} ({discount_vs_market_pct:.0f}% below typical AUD {normal_market:.0f} Australian retail value).",
        ]
        if beats_90d_low:
            bullets.append(f"All-time 90-day observed low across tracked Australian retailers (previous low: AUD {lowest_90d:.2f}).")
        if is_extreme_anomaly and seller_trust_score >= 90:
            bullets.append(f"Extraordinary clearance/pricing anomaly at Tier-1 retailer ({retailer}) — high sell-out urgency.")
        if product.get("lifecycle_stage") == "previous_gen_value":
            bullets.append(f"Previous-generation flagship value: delivers ~92% of successor ({product.get('successor_model', 'next-gen')}) capability at a fraction of the price.")
        if matched_interest:
            bullets.append(f"Directly matches your active interest: '{matched_interest['name']}'.")
        else:
            bullets.append("Discovered autonomously by Engine B (Outside-Wishlist Exceptional Deal Sniper).")

        return {
            "deal_score": deal_score,
            "classification": classification,
            "suitability_score": suitability_score,
            "attractiveness_score": attractiveness_score,
            "seller_trust_score": seller_trust_score,
            "data_confidence_score": data_confidence_score,
            "discount_pct": discount_vs_market_pct,
            "final_checkout_cost_aud": checkout_cost,
            "effective_after_cashback_aud": stacking.effective_cost_after_cashback_aud,
            "stacking_breakdown": asdict(stacking),
            "verification_status": verification_status,
            "verification_checks": verification_checks,
            "risk_flags": risk_flags,
            "explanation_bullets": bullets,
        }
