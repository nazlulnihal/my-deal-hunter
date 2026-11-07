"""
Modular Australian Retailer & Discovery Connectors, plus Multi-Retailer
Shopping Basket Optimiser.

Respects robots.txt, rate limits, and retailer terms of service.
Never bypasses CAPTCHAs or authentication barriers.
Tracks source URL, collection method, and timestamp of every price observation.
"""

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from .product_engine import calculate_normalised_unit_price


AUSTRALIAN_RETAILER_CONNECTORS = [
    {"id": "officeworks", "name": "Officeworks", "domain": "https://www.officeworks.com.au", "category_focus": ["Tech", "Office", "Smartwatches", "Clearance"], "mode": "Structured JSON-LD / Permitted Feed", "supports_click_and_collect": True, "free_delivery_min_aud": 55.0, "standard_shipping_aud": 6.95, "rate_limit_rpm": 12},
    {"id": "jbhifi", "name": "JB Hi-Fi", "domain": "https://www.jbhifi.com.au", "category_focus": ["Electronics", "Phones", "Audio", "TVs", "Appliances"], "mode": "Structured Product Feed / Schema", "supports_click_and_collect": True, "free_delivery_min_aud": 99.0, "standard_shipping_aud": 7.99, "rate_limit_rpm": 12},
    {"id": "amazon_au", "name": "Amazon Australia", "domain": "https://www.amazon.com.au", "category_focus": ["All Categories", "Pantry", "Tech", "Home"], "mode": "PA-API / Permitted Product Feed", "supports_click_and_collect": False, "free_delivery_min_aud": 59.0, "standard_shipping_aud": 6.99, "rate_limit_rpm": 20},
    {"id": "thegoodguys", "name": "The Good Guys", "domain": "https://www.thegoodguys.com.au", "category_focus": ["Appliances", "TVs", "Coffee Machines", "Vacuums"], "mode": "Structured Schema / Price Watch", "supports_click_and_collect": True, "free_delivery_min_aud": 150.0, "standard_shipping_aud": 9.95, "rate_limit_rpm": 10},
    {"id": "harveynorman", "name": "Harvey Norman", "domain": "https://www.harveynorman.com.au", "category_focus": ["Computers", "Appliances", "Bedding", "Furniture"], "mode": "Structured Schema", "supports_click_and_collect": True, "free_delivery_min_aud": 200.0, "standard_shipping_aud": 11.95, "rate_limit_rpm": 10},
    {"id": "binglee", "name": "Bing Lee", "domain": "https://www.binglee.com.au", "category_focus": ["NSW/VIC Electronics", "Coffee Machines", "Appliances"], "mode": "Structured Schema", "supports_click_and_collect": True, "free_delivery_min_aud": 150.0, "standard_shipping_aud": 9.00, "rate_limit_rpm": 10},
    {"id": "appliancesonline", "name": "Appliances Online", "domain": "https://www.appliancesonline.com.au", "category_focus": ["Whitegoods", "Coffee Machines", "Vacuums"], "mode": "Permitted JSON Feed", "supports_click_and_collect": False, "free_delivery_min_aud": 0.0, "standard_shipping_aud": 0.0, "rate_limit_rpm": 12},
    {"id": "kogan", "name": "Kogan", "domain": "https://www.kogan.com/au", "category_focus": ["Electronics", "Home", "Pantry"], "mode": "RSS / Promotional Feed", "supports_click_and_collect": False, "free_delivery_min_aud": 99.0, "standard_shipping_aud": 8.99, "rate_limit_rpm": 10},
    {"id": "myer", "name": "Myer", "domain": "https://www.myer.com.au", "category_focus": ["Appliances", "Fashion", "Beauty", "Gifts", "Chocolates"], "mode": "Structured Schema", "supports_click_and_collect": True, "free_delivery_min_aud": 99.0, "standard_shipping_aud": 9.95, "rate_limit_rpm": 10},
    {"id": "davidjones", "name": "David Jones", "domain": "https://www.davidjones.com", "category_focus": ["Fashion", "Beauty", "Homewares", "Gourmet Gifts"], "mode": "Structured Schema", "supports_click_and_collect": True, "free_delivery_min_aud": 100.0, "standard_shipping_aud": 10.00, "rate_limit_rpm": 10},
    {"id": "bigw", "name": "Big W", "domain": "https://www.bigw.com.au", "category_focus": ["Home", "Toys", "Confectionery", "Small Appliances"], "mode": "Structured Catalog API", "supports_click_and_collect": True, "free_delivery_min_aud": 100.0, "standard_shipping_aud": 7.90, "rate_limit_rpm": 12},
    {"id": "target_au", "name": "Target", "domain": "https://www.target.com.au", "category_focus": ["Apparel", "Homewares", "Toys", "Bedding"], "mode": "Structured Catalog API", "supports_click_and_collect": True, "free_delivery_min_aud": 60.0, "standard_shipping_aud": 9.00, "rate_limit_rpm": 12},
    {"id": "bunnings", "name": "Bunnings", "domain": "https://www.bunnings.com.au", "category_focus": ["Hardware", "Tools", "Outdoor", "Cleaning"], "mode": "Store Stock & Price Feed", "supports_click_and_collect": True, "free_delivery_min_aud": 150.0, "standard_shipping_aud": 10.00, "rate_limit_rpm": 10},
    {"id": "chemistwarehouse", "name": "Chemist Warehouse", "domain": "https://www.chemistwarehouse.com.au", "category_focus": ["Personal Care", "Skincare", "Protein Bars", "Perfumes"], "mode": "Structured Schema", "supports_click_and_collect": True, "free_delivery_min_aud": 50.0, "standard_shipping_aud": 8.95, "rate_limit_rpm": 12},
    {"id": "priceline", "name": "Priceline", "domain": "https://www.priceline.com.au", "category_focus": ["Skincare", "Cosmetics", "Personal Care"], "mode": "Structured Schema", "supports_click_and_collect": True, "free_delivery_min_aud": 50.0, "standard_shipping_aud": 7.95, "rate_limit_rpm": 10},
    {"id": "woolworths", "name": "Woolworths", "domain": "https://www.woolworths.com.au", "category_focus": ["Groceries", "Chocolates", "Coffee", "Household"], "mode": "Half-Price Specials & Unit Catalog", "supports_click_and_collect": True, "free_delivery_min_aud": 150.0, "standard_shipping_aud": 11.00, "rate_limit_rpm": 15},
    {"id": "coles", "name": "Coles", "domain": "https://www.coles.com.au", "category_focus": ["Groceries", "Chocolates", "Coffee", "Household"], "mode": "Weekly Specials & Unit Catalog", "supports_click_and_collect": True, "free_delivery_min_aud": 150.0, "standard_shipping_aud": 11.00, "rate_limit_rpm": 15},
    {"id": "aldi", "name": "Aldi", "domain": "https://www.aldi.com.au", "category_focus": ["Special Buys", "Groceries", "Appliances"], "mode": "Special Buys Promotional Feed", "supports_click_and_collect": False, "free_delivery_min_aud": 0.0, "standard_shipping_aud": 0.0, "rate_limit_rpm": 10},
    {"id": "costco_au", "name": "Costco", "domain": "https://www.costco.com.au", "category_focus": ["Bulk Groceries", "Electronics", "Home"], "mode": "Warehouse & Online Feed", "supports_click_and_collect": True, "free_delivery_min_aud": 0.0, "standard_shipping_aud": 0.0, "rate_limit_rpm": 10},
    {"id": "ebay_au", "name": "eBay Australia", "domain": "https://www.ebay.com.au", "category_focus": ["Official Brand Outlets", "Plus Coupons", "Refurbished"], "mode": "Browse API / RSS", "supports_click_and_collect": True, "free_delivery_min_aud": 0.0, "standard_shipping_aud": 0.0, "rate_limit_rpm": 20},
    {"id": "ozbargain", "name": "OzBargain Community Feed", "domain": "https://www.ozbargain.com.au", "category_focus": ["Community Sniper Deals", "Pricing Errors", "Clearance"], "mode": "Public RSS / Frontpage & New Deals Feed", "supports_click_and_collect": False, "free_delivery_min_aud": 0.0, "standard_shipping_aud": 0.0, "rate_limit_rpm": 30},
]


class ShoppingBasketOptimiser:
    """
    Optimises a multi-item shopping basket (e.g., Chocolates, Coffee, Protein Bars,
    Shampoo, Laundry Detergent) across Australian supermarkets and retailers:
    - Woolworths
    - Coles
    - Amazon Australia
    - Chemist Warehouse
    - Big W
    Compares buying everything from a single retailer vs splitting the basket across
    multiple retailers, accounting for delivery fees, Click & Collect (free pickup),
    minimum order thresholds, pack sizes, and normalised unit prices.
    """

    RETAILER_DELIVERY_RULES = {
        "Woolworths": {"delivery_fee_aud": 11.00, "free_delivery_min_aud": 150.0, "click_and_collect_fee_aud": 0.0, "click_and_collect_min_aud": 30.0},
        "Coles": {"delivery_fee_aud": 11.00, "free_delivery_min_aud": 150.0, "click_and_collect_fee_aud": 0.0, "click_and_collect_min_aud": 30.0},
        "Amazon Australia": {"delivery_fee_aud": 6.99, "free_delivery_min_aud": 59.0, "click_and_collect_fee_aud": 0.0, "click_and_collect_min_aud": 0.0},
        "Chemist Warehouse": {"delivery_fee_aud": 8.95, "free_delivery_min_aud": 50.0, "click_and_collect_fee_aud": 0.0, "click_and_collect_min_aud": 0.0},
        "Big W": {"delivery_fee_aud": 7.90, "free_delivery_min_aud": 100.0, "click_and_collect_fee_aud": 0.0, "click_and_collect_min_aud": 20.0},
    }

    def optimise_basket(
        self,
        basket_items: List[Dict[str, Any]],
        fulfilment_mode: str = "click_and_collect"  # "click_and_collect" or "home_delivery"
    ) -> Dict[str, Any]:
        """
        Each item in basket_items has:
        {
          "item_id": str,
          "name": str,
          "category": str,
          "quantity": int,
          "pack_size": float,
          "unit_measure": str,
          "normal_price_aud": float,
          "retailer_offers": {
              "Woolworths": {"price_aud": float, "promo_note": str, "url": str},
              "Coles": {"price_aud": float, "promo_note": str, "url": str},
              ...
          }
        }
        """
        retailers = list(self.RETAILER_DELIVERY_RULES.keys())
        normal_total_aud = sum(float(i["normal_price_aud"]) * int(i.get("quantity", 1)) for i in basket_items)

        # 1. Single-retailer totals (for retailers stocking all or most items)
        single_retailer_results = []
        for r in retailers:
            subtotal = 0.0
            covered_count = 0
            item_breakdown = []
            for item in basket_items:
                qty = int(item.get("quantity", 1))
                offers = item.get("retailer_offers", {})
                if r in offers:
                    unit_p = float(offers[r]["price_aud"])
                    line_total = round(unit_p * qty, 2)
                    subtotal += line_total
                    covered_count += 1
                    u_norm = calculate_normalised_unit_price(unit_p, float(item["pack_size"]), item["unit_measure"])
                    item_breakdown.append({
                        "name": item["name"],
                        "quantity": qty,
                        "unit_price_aud": unit_p,
                        "line_total_aud": line_total,
                        "normalised_unit": u_norm.display_string,
                        "promo_note": offers[r].get("promo_note", "Standard price")
                    })

            if covered_count == len(basket_items):
                rules = self.RETAILER_DELIVERY_RULES[r]
                if fulfilment_mode == "click_and_collect":
                    fee = rules["click_and_collect_fee_aud"]
                else:
                    fee = 0.0 if subtotal >= rules["free_delivery_min_aud"] else rules["delivery_fee_aud"]
                grand_total = round(subtotal + fee, 2)
                single_retailer_results.append({
                    "retailer": r,
                    "items_subtotal_aud": round(subtotal, 2),
                    "fulfilment_fee_aud": round(fee, 2),
                    "total_cost_aud": grand_total,
                    "savings_vs_rrp_aud": round(normal_total_aud - grand_total, 2),
                    "items": item_breakdown
                })

        single_retailer_results.sort(key=lambda x: x["total_cost_aud"])
        best_single = single_retailer_results[0] if single_retailer_results else None

        # 2. Optimal Split-Basket Strategy (cherry-picking the lowest legitimate offer per item)
        split_allocations: Dict[str, List[Dict[str, Any]]] = {}
        split_items_subtotal = 0.0

        for item in basket_items:
            qty = int(item.get("quantity", 1))
            offers = item.get("retailer_offers", {})
            best_r = min(offers.keys(), key=lambda k: float(offers[k]["price_aud"]))
            best_offer = offers[best_r]
            unit_p = float(best_offer["price_aud"])
            line_total = round(unit_p * qty, 2)
            split_items_subtotal += line_total
            u_norm = calculate_normalised_unit_price(unit_p, float(item["pack_size"]), item["unit_measure"])

            split_allocations.setdefault(best_r, []).append({
                "name": item["name"],
                "quantity": qty,
                "unit_price_aud": unit_p,
                "line_total_aud": line_total,
                "normalised_unit": u_norm.display_string,
                "promo_note": best_offer.get("promo_note", "Best in-market price"),
                "url": best_offer.get("url", "")
            })

        # Calculate fulfilment fees for split retailers
        split_fulfilment_fee = 0.0
        for r, items_list in split_allocations.items():
            r_sub = sum(i["line_total_aud"] for i in items_list)
            rules = self.RETAILER_DELIVERY_RULES.get(r, {"delivery_fee_aud": 8.0, "free_delivery_min_aud": 100.0, "click_and_collect_fee_aud": 0.0})
            if fulfilment_mode == "click_and_collect":
                split_fulfilment_fee += rules["click_and_collect_fee_aud"]
            else:
                if r_sub < rules["free_delivery_min_aud"]:
                    split_fulfilment_fee += rules["delivery_fee_aud"]

        split_grand_total = round(split_items_subtotal + split_fulfilment_fee, 2)
        extra_savings_vs_best_single = round((best_single["total_cost_aud"] - split_grand_total), 2) if best_single else 0.0

        if fulfilment_mode == "home_delivery" and extra_savings_vs_best_single <= 0:
            tradeoff_explanation = (
                f"Under Home Delivery, splitting across {len(split_allocations)} retailers incurs multiple delivery fees "
                f"(AUD {split_fulfilment_fee:.2f} total), making a single order at {best_single['retailer']} "
                f"(AUD {best_single['total_cost_aud']:.2f}) cheaper overall. Switch to Click & Collect to unlock "
                f"AUD {round(best_single['items_subtotal_aud'] - split_items_subtotal, 2):.2f} in split-basket savings with $0 pickup fees."
            )
            recommended_strategy = f"Single Retailer ({best_single['retailer']})"
        else:
            tradeoff_explanation = (
                f"Splitting your basket across {', '.join(split_allocations.keys())} via free Click & Collect "
                f"reduces total basket cost to AUD {split_grand_total:.2f} — saving AUD {round(normal_total_aud - split_grand_total, 2):.2f} "
                f"({round(((normal_total_aud - split_grand_total) / normal_total_aud) * 100, 1)}%) off standard RRP and "
                f"an extra AUD {extra_savings_vs_best_single:.2f} compared with buying everything at {best_single['retailer'] if best_single else 'one store'}."
            )
            recommended_strategy = f"Split Basket ({len(split_allocations)} Retailers)"

        return {
            "fulfilment_mode": fulfilment_mode,
            "normal_rrp_total_aud": round(normal_total_aud, 2),
            "best_single_retailer": best_single,
            "all_single_retailers": single_retailer_results,
            "split_basket_strategy": {
                "retailer_count": len(split_allocations),
                "items_subtotal_aud": round(split_items_subtotal, 2),
                "fulfilment_fee_aud": round(split_fulfilment_fee, 2),
                "total_cost_aud": split_grand_total,
                "total_savings_vs_rrp_aud": round(normal_total_aud - split_grand_total, 2),
                "extra_savings_vs_single_aud": extra_savings_vs_best_single,
                "allocations": split_allocations,
            },
            "recommended_strategy": recommended_strategy,
            "tradeoff_explanation": tradeoff_explanation,
        }
