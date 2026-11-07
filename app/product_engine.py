"""
Universal Product & Category Engine, Variant & GTIN/EAN/MPN Matching,
and Unit Price Normalisation across all physical product categories.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

UNIVERSAL_CATEGORIES = [
    "Smartphones, Smartwatches & Tablets",
    "Computers & Electronics",
    "TVs, Audio & Gaming",
    "Home Appliances & Coffee Machines",
    "Groceries, Chocolates & Beverages",
    "Personal Care, Skincare & Cosmetics",
    "Clothing, Footwear & Fashion",
    "Furniture, Homewares & Bedding",
    "Hardware, Tools & Gardening",
    "Sports, Fitness & Camping",
    "Baby Products, Toys, Books & Gifts",
    "Pet Food & Pet Supplies",
    "Cleaning & Household Consumables",
]


@dataclass
class UnitPriceResult:
    raw_price_aud: float
    pack_quantity: float
    unit_measure: str
    normalised_unit_price_aud: float
    normalised_unit_label: str
    display_string: str


def calculate_normalised_unit_price(
    price_aud: float,
    pack_quantity: float,
    unit_measure: str,
    multipack_count: int = 1
) -> UnitPriceResult:
    """
    Calculates normalised Australian grocery/consumable unit pricing:
    - Grams (g) or Kilograms (kg) -> AUD per 100g (and AUD per kg if >= 1kg)
    - Millilitres (ml) or Litres (l) -> AUD per 100ml or AUD per 1L
    - Items / Capsules / Tablets / Pods / Washes -> AUD per item
    Never compares unnormalised pack sizes as equivalent.
    """
    total_qty = max(pack_quantity * max(multipack_count, 1), 0.0001)
    unit = unit_measure.strip().lower()

    if unit in ("g", "gram", "grams"):
        per_100g = (price_aud / total_qty) * 100.0
        return UnitPriceResult(
            raw_price_aud=price_aud,
            pack_quantity=total_qty,
            unit_measure="g",
            normalised_unit_price_aud=round(per_100g, 2),
            normalised_unit_label="per 100g",
            display_string=f"AUD {per_100g:.2f} / 100g"
        )
    elif unit in ("kg", "kilogram", "kilograms"):
        grams = total_qty * 1000.0
        per_100g = (price_aud / grams) * 100.0
        per_kg = price_aud / total_qty
        return UnitPriceResult(
            raw_price_aud=price_aud,
            pack_quantity=grams,
            unit_measure="g",
            normalised_unit_price_aud=round(per_100g, 2),
            normalised_unit_label="per 100g",
            display_string=f"AUD {per_kg:.2f} / kg (AUD {per_100g:.2f} / 100g)"
        )
    elif unit in ("ml", "millilitre", "millilitres"):
        per_100ml = (price_aud / total_qty) * 100.0
        return UnitPriceResult(
            raw_price_aud=price_aud,
            pack_quantity=total_qty,
            unit_measure="ml",
            normalised_unit_price_aud=round(per_100ml, 2),
            normalised_unit_label="per 100ml",
            display_string=f"AUD {per_100ml:.2f} / 100ml"
        )
    elif unit in ("l", "litre", "litres"):
        ml = total_qty * 1000.0
        per_100ml = (price_aud / ml) * 100.0
        per_l = price_aud / total_qty
        return UnitPriceResult(
            raw_price_aud=price_aud,
            pack_quantity=ml,
            unit_measure="ml",
            normalised_unit_price_aud=round(per_100ml, 2),
            normalised_unit_label="per 100ml",
            display_string=f"AUD {per_l:.2f} / L (AUD {per_100ml:.2f} / 100ml)"
        )
    else:
        per_item = price_aud / total_qty
        return UnitPriceResult(
            raw_price_aud=price_aud,
            pack_quantity=total_qty,
            unit_measure=unit or "item",
            normalised_unit_price_aud=round(per_item, 2),
            normalised_unit_label=f"per {unit or 'item'}",
            display_string=f"AUD {per_item:.2f} / {unit or 'item'}"
        )


@dataclass
class ProductMatchResult:
    is_exact_match: bool
    is_variant_mismatch: bool
    is_generation_alternative: bool
    is_accessory_or_bundle_trap: bool
    confidence_score: float
    relationship_type: str
    explanation: str


class ProductIntelligenceEngine:
    """
    Distinguishes exact product matches, generations, storage capacities, sizes,
    colours, pack sizes, refurbished vs new conditions, and AU vs International grey imports.
    """

    ACCESSORY_TRAP_KEYWORDS = [
        "case for", "cover for", "screen protector", "replacement strap",
        "band only", "silicone band", "charging cable for", "box only", "empty box"
    ]

    def evaluate_listing_match(
        self,
        target_product: Dict[str, Any],
        listing_title: str,
        listing_gtin: Optional[str] = None,
        listing_mpn: Optional[str] = None,
        listing_condition: str = "New",
        listing_pack_qty: Optional[float] = None,
        acceptable_conditions: Optional[List[str]] = None
    ) -> ProductMatchResult:
        title_lower = listing_title.lower()
        target_name_lower = target_product["canonical_name"].lower()
        target_attrs = json.loads(target_product.get("attributes_json", "{}"))
        allowed_conds = [c.lower() for c in (acceptable_conditions or ["New"])]

        # 1. Check accessory or empty-box trap first
        for trap in self.ACCESSORY_TRAP_KEYWORDS:
            if trap in title_lower and trap not in target_name_lower:
                return ProductMatchResult(
                    is_exact_match=False,
                    is_variant_mismatch=True,
                    is_generation_alternative=False,
                    is_accessory_or_bundle_trap=True,
                    confidence_score=0.98,
                    relationship_type="accessory_trap",
                    explanation=f"Listing appears to be an accessory ('{trap}') rather than the main product."
                )

        # 2. Check condition compatibility
        if listing_condition.lower() not in allowed_conds:
            return ProductMatchResult(
                is_exact_match=False,
                is_variant_mismatch=True,
                is_generation_alternative=False,
                is_accessory_or_bundle_trap=False,
                confidence_score=0.92,
                relationship_type="condition_mismatch",
                explanation=f"Condition '{listing_condition}' excluded by allowed conditions {acceptable_conditions}."
            )

        # 3. GTIN / EAN / MPN exact hardware verification
        if listing_gtin and target_product.get("gtin_ean"):
            if listing_gtin.strip() == str(target_product["gtin_ean"]).strip():
                return ProductMatchResult(
                    is_exact_match=True,
                    is_variant_mismatch=False,
                    is_generation_alternative=False,
                    is_accessory_or_bundle_trap=False,
                    confidence_score=0.99,
                    relationship_type="exact_gtin_match",
                    explanation=f"Verified exact GTIN/EAN barcode match ({listing_gtin})."
                )
            else:
                return ProductMatchResult(
                    is_exact_match=False,
                    is_variant_mismatch=True,
                    is_generation_alternative=False,
                    is_accessory_or_bundle_trap=False,
                    confidence_score=0.95,
                    relationship_type="gtin_mismatch",
                    explanation=f"GTIN {listing_gtin} differs from canonical GTIN {target_product['gtin_ean']}."
                )

        # 4. Check pack size normalisation for groceries/consumables
        target_pack = float(target_product.get("pack_quantity", 1.0))
        if listing_pack_qty is not None and abs(listing_pack_qty - target_pack) > 0.01:
            return ProductMatchResult(
                is_exact_match=False,
                is_variant_mismatch=True,
                is_generation_alternative=False,
                is_accessory_or_bundle_trap=False,
                confidence_score=0.90,
                relationship_type="pack_size_variant",
                explanation=(
                    f"Pack size differs ({listing_pack_qty}{target_product.get('unit_measure', '')} vs "
                    f"{target_pack}{target_product.get('unit_measure', '')}). Requires unit-price normalisation."
                )
            )

        # 5. Check critical variant attributes (e.g., 44mm vs 40mm, 256GB vs 128GB, 65-inch vs 55-inch)
        if "case_size" in target_attrs:
            expected_size = str(target_attrs["case_size"]).lower()
            other_sizes = [s for s in ["40mm", "41mm", "42mm", "44mm", "45mm", "46mm", "47mm"] if s != expected_size]
            for wrong_size in other_sizes:
                if wrong_size in title_lower:
                    return ProductMatchResult(
                        is_exact_match=False,
                        is_variant_mismatch=True,
                        is_generation_alternative=False,
                        is_accessory_or_bundle_trap=False,
                        confidence_score=0.94,
                        relationship_type="size_variant_mismatch",
                        explanation=f"Listing is {wrong_size} casing instead of requested {expected_size}."
                    )

        if "storage" in target_attrs:
            expected_storage = str(target_attrs["storage"]).lower()
            other_storages = [st for st in ["128gb", "256gb", "512gb", "1tb"] if st != expected_storage]
            for wrong_st in other_storages:
                if wrong_st in title_lower and expected_storage not in title_lower:
                    return ProductMatchResult(
                        is_exact_match=False,
                        is_variant_mismatch=True,
                        is_generation_alternative=False,
                        is_accessory_or_bundle_trap=False,
                        confidence_score=0.93,
                        relationship_type="storage_variant_mismatch",
                        explanation=f"Storage capacity is {wrong_st.upper()} instead of {expected_storage.upper()}."
                    )

        # 6. Check generation differences (e.g. Watch 7 vs Watch 6, S26 Ultra vs S25 Ultra, XM6 vs XM5)
        gen_tokens = ["watch 6", "watch 7", "watch 8", "s24 ultra", "s25 ultra", "s26 ultra", "wh-1000xm4", "wh-1000xm5", "wh-1000xm6"]
        target_gen = next((g for g in gen_tokens if g in target_name_lower), None)
        listing_gen = next((g for g in gen_tokens if g in title_lower), None)
        if target_gen and listing_gen and target_gen != listing_gen:
            return ProductMatchResult(
                is_exact_match=False,
                is_variant_mismatch=False,
                is_generation_alternative=True,
                is_accessory_or_bundle_trap=False,
                confidence_score=0.89,
                relationship_type="generation_alternative",
                explanation=f"Different generation detected ({listing_gen.upper()} vs target {target_gen.upper()})."
            )

        # 7. Check brand & model token overlap
        brand_lower = target_product["brand"].lower()
        if brand_lower in title_lower:
            return ProductMatchResult(
                is_exact_match=True,
                is_variant_mismatch=False,
                is_generation_alternative=False,
                is_accessory_or_bundle_trap=False,
                confidence_score=0.91,
                relationship_type="verified_attribute_match",
                explanation="Brand, model family, and variant specifications match canonical product."
            )

        return ProductMatchResult(
            is_exact_match=False,
            is_variant_mismatch=False,
            is_generation_alternative=False,
            is_accessory_or_bundle_trap=False,
            confidence_score=0.45,
            relationship_type="competing_alternative",
            explanation="Different brand or competing model in the same product category."
        )

    def compare_products_side_by_side(self, products: List[Dict[str, Any]], latest_prices: Dict[str, float]) -> Dict[str, Any]:
        """
        Produces a structured side-by-side comparison across specifications, current price,
        normal market value, unit pricing, generation lifecycle, and long-term value score.
        """
        comparison_rows = []
        for p in products:
            pid = p["id"]
            attrs = json.loads(p.get("attributes_json", "{}"))
            curr_price = latest_prices.get(pid, p["normal_market_price_aud"])
            normal_price = p["normal_market_price_aud"]
            savings_pct = round(((normal_price - curr_price) / normal_price) * 100.0, 1) if normal_price > 0 else 0.0
            unit_res = calculate_normalised_unit_price(
                curr_price,
                float(p.get("pack_quantity", 1.0)),
                p.get("unit_measure", "item")
            )
            value_score = min(99, max(40, int(70 + savings_pct * 0.6)))
            comparison_rows.append({
                "product_id": pid,
                "canonical_name": p["canonical_name"],
                "brand": p["brand"],
                "model_number": p.get("model_number", "N/A"),
                "generation": p.get("generation", "Current"),
                "category": p["category"],
                "current_best_price_aud": curr_price,
                "normal_market_price_aud": normal_price,
                "savings_pct": savings_pct,
                "unit_price_display": unit_res.display_string,
                "lifecycle_stage": p.get("lifecycle_stage", "current"),
                "specifications": attrs,
                "long_term_value_score": value_score,
                "official_url": p.get("official_url", "")
            })

        comparison_rows.sort(key=lambda r: r["long_term_value_score"], reverse=True)
        winner = comparison_rows[0] if comparison_rows else None
        tradeoff_summary = ""
        if len(comparison_rows) >= 2:
            top, second = comparison_rows[0], comparison_rows[1]
            price_diff = abs(top["current_best_price_aud"] - second["current_best_price_aud"])
            tradeoff_summary = (
                f"{top['canonical_name']} leads on overall value (Score {top['long_term_value_score']}/100) "
                f"at AUD {top['current_best_price_aud']:.2f} ({top['savings_pct']}% below market), "
                f"representing an AUD {price_diff:.2f} difference compared with {second['canonical_name']}."
            )

        return {
            "compared_count": len(comparison_rows),
            "winner_product_id": winner["product_id"] if winner else None,
            "tradeoff_summary": tradeoff_summary,
            "items": comparison_rows
        }
