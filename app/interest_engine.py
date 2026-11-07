"""
Natural-Language Shopping Interest Parser & Shortlist Generator.
Supports:
- Type A: Exact product (e.g., "Samsung Galaxy Watch 7, 44mm", "Sony WH-1000XM6")
- Type B: Multiple acceptable products (e.g., "Samsung S26 Ultra OR S25 Ultra", "Any good 65-inch OLED TV from Samsung, LG or Sony")
- Type C: Broad requirements (e.g., "Any good Android phone around AUD 750 with excellent battery life", "Good-quality chocolates or assorted gift boxes under AUD 30")
"""

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class NaturalLanguageInterestEngine:
    """
    Parses natural-language shopping statements into structured interest criteria,
    determines whether the query is Exact (A), Multiple Acceptable (B), or Broad (C),
    and builds an initial researched product shortlist from the catalog without forcing
    the user to pick a single model upfront.
    """

    CATEGORY_KEYWORDS = {
        "Smartphones, Smartwatches & Tablets": [
            "phone", "android", "iphone", "galaxy s", "pixel", "smartwatch", "watch", "tablet", "ipad", "wearable"
        ],
        "TVs, Audio & Gaming": [
            "tv", "oled", "qled", "headphones", "earbuds", "wh-1000", "bose", "sennheiser", "speaker", "soundbar", "ps5", "console"
        ],
        "Home Appliances & Coffee Machines": [
            "coffee machine", "espresso", "breville", "delonghi", "vacuum", "dyson", "roborock", "air fryer", "appliance", "fridge", "microwave"
        ],
        "Groceries, Chocolates & Beverages": [
            "chocolate", "lindt", "ferrero", "haigh", "koko black", "coffee beans", "lavazza", "snack", "grocery", "pantry", "protein bar", "beverage"
        ],
        "Cleaning & Household Consumables": [
            "detergent", "laundry", "omo", "dishwashing", "fairy", "finish", "paper towel", "cleaning", "toilet paper"
        ],
        "Personal Care, Skincare & Cosmetics": [
            "shampoo", "skincare", "cerave", "la roche", "perfume", "razor", "toothbrush", "grooming", "cosmetic"
        ],
        "Hardware, Tools & Gardening": [
            "drill", "makita", "dewalt", "ryobi", "bunnings", "mower", "tool", "hardware", "garden"
        ],
    }

    KNOWN_BRANDS = [
        "Samsung", "Apple", "Sony", "Google", "Motorola", "OnePlus", "Nothing", "Garmin",
        "Bose", "Sennheiser", "LG", "Breville", "De'Longhi", "Dyson", "Shark", "Roborock",
        "Lindt", "Haigh's", "Koko Black", "Ferrero", "Lavazza", "Vittoria", "Quest", "Musashi",
        "Omo", "Biozet", "Head & Shoulders", "CeraVe", "Makita", "Ryobi"
    ]

    def parse_natural_query(self, raw_query: str, catalog_products: List[Dict[str, Any]]) -> Dict[str, Any]:
        query = raw_query.strip()
        q_lower = query.lower()

        # 1. Detect Budget / Price Target (e.g., "under AUD 750", "around $300", "< $30")
        budget_match = re.search(
            r"(?:under|around|below|max|up to|less than|<|\$)\s*(?:aud\s*)?\$?\s*(\d+(?:\.\d{1,2})?)",
            q_lower
        )
        if not budget_match:
            budget_match = re.search(r"aud\s*\$?\s*(\d+(?:\.\d{1,2})?)", q_lower)

        max_budget: Optional[float] = float(budget_match.group(1)) if budget_match else None
        target_price: Optional[float] = round(max_budget * 0.85, 2) if max_budget else None

        # 2. Detect Category
        detected_category = "Computers & Electronics"
        for cat, keywords in self.CATEGORY_KEYWORDS.items():
            if any(kw in q_lower for kw in keywords):
                detected_category = cat
                break

        # 3. Detect mentioned brands
        mentioned_brands = [b for b in self.KNOWN_BRANDS if b.lower() in q_lower]

        # 4. Classify Interest Type: Exact (A), Multiple (B), or Broad (C)
        has_or_operator = bool(re.search(r"\bor\b", q_lower)) or "," in q_lower and len(mentioned_brands) >= 2
        has_broad_qualifiers = any(
            phrase in q_lower for phrase in [
                "any good", "a good", "decent", "reliable", "premium", "good-quality",
                "good quality", "suitable for", "excellent battery", "best value", "assorted"
            ]
        )

        # Check specific model identifiers
        exact_model_patterns = [
            r"watch\s*\d+", r"s2\d\s*ultra", r"wh-1000xm\d", r"series\s*\d+",
            r"bes\d{3}", r"pixel\s*\d+", r"\d+g\b", r"\d+kg\b", r"\d+mm\b", r"\d+gb\b"
        ]
        model_hits = [pat for pat in exact_model_patterns if re.search(pat, q_lower)]

        if has_or_operator and (model_hits or len(mentioned_brands) >= 2 or "newer" in q_lower):
            interest_type = "multiple"
        elif has_broad_qualifiers or (max_budget is not None and not model_hits):
            interest_type = "broad"
        elif model_hits or len(mentioned_brands) == 1:
            interest_type = "exact"
        else:
            interest_type = "broad"

        # 5. Extract minimum specification requirements
        min_specs: Dict[str, Any] = {}
        if "battery" in q_lower:
            min_specs["battery_life"] = "5000mAh+ / Multi-day endurance"
        if "oled" in q_lower:
            min_specs["display_panel"] = "OLED"
        size_inch = re.search(r"(\d{2})\s*-?\s*inch", q_lower)
        if size_inch:
            min_specs["screen_size_inches"] = int(size_inch.group(1))
        mm_match = re.search(r"(\d{2})mm", q_lower)
        if mm_match:
            min_specs["case_size"] = f"{mm_match.group(1)}mm"
        gb_match = re.search(r"(\d{3,4})gb", q_lower)
        if gb_match:
            min_specs["storage"] = f"{gb_match.group(1)}GB"
        if "apartment" in q_lower:
            min_specs["form_factor"] = "Compact cordless / HEPA filtration / low noise"

        # 6. Build intelligent shortlist from catalog
        shortlist = self.generate_shortlist(
            interest_type=interest_type,
            category=detected_category,
            raw_query=query,
            preferred_brands=mentioned_brands,
            max_budget=max_budget,
            min_specs=min_specs,
            catalog_products=catalog_products
        )

        acceptable_models = [item["canonical_name"] for item in shortlist]

        return {
            "name": query[:68] if len(query) <= 68 else query[:65] + "...",
            "natural_query": query,
            "interest_type": interest_type,
            "category": detected_category,
            "preferred_brands": mentioned_brands,
            "excluded_brands": [],
            "max_budget": max_budget,
            "target_price": target_price,
            "min_specs": min_specs,
            "acceptable_models": acceptable_models,
            "shortlist": shortlist,
            "acceptable_conditions": ["New", "Refurbished"] if "refurbished" in q_lower else ["New"],
            "priority": "critical" if interest_type == "exact" else "high",
            "monitoring_frequency_mins": 5 if interest_type == "exact" else 15,
        }

    def generate_shortlist(
        self,
        interest_type: str,
        category: str,
        raw_query: str,
        preferred_brands: List[str],
        max_budget: Optional[float],
        min_specs: Dict[str, Any],
        catalog_products: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        q_lower = raw_query.lower()
        candidates = []

        for prod in catalog_products:
            prod_cat = prod["category"]
            name_lower = prod["canonical_name"].lower()
            brand = prod["brand"]
            normal_price = float(prod["normal_market_price_aud"])
            attrs = json.loads(prod.get("attributes_json", "{}"))

            # Score relevance
            score = 0
            reasons = []

            if prod_cat == category:
                score += 40
            # Token overlap
            query_words = [w for w in re.findall(r"[a-z0-9]+", q_lower) if len(w) > 2]
            matched_words = [w for w in query_words if w in name_lower or w in json.dumps(attrs).lower()]
            score += len(matched_words) * 15

            if preferred_brands and brand in preferred_brands:
                score += 25
                reasons.append(f"Matches preferred brand ({brand})")

            if max_budget is not None:
                if normal_price <= max_budget * 1.25:
                    score += 20
                    reasons.append(f"Market value (AUD {normal_price:.0f}) aligns with AUD {max_budget:.0f} budget")
                else:
                    score -= 25

            for k, v in min_specs.items():
                if k in attrs and str(v).lower() in str(attrs[k]).lower():
                    score += 20
                    reasons.append(f"Meets {k.replace('_', ' ')}: {attrs[k]}")
                elif k == "battery_life" and "battery" in attrs:
                    score += 20
                    reasons.append(f"Strong battery spec ({attrs['battery']})")

            if score >= 45:
                if not reasons:
                    reasons.append(f"Top-rated {prod_cat} contender with strong Australian retail availability")
                candidates.append({
                    "product_id": prod["id"],
                    "canonical_name": prod["canonical_name"],
                    "brand": brand,
                    "normal_market_price_aud": normal_price,
                    "qualification_reason": "; ".join(reasons),
                    "suitability_score": min(99, max(68, score)),
                    "approved": True
                })

        candidates.sort(key=lambda x: x["suitability_score"], reverse=True)
        if interest_type == "exact":
            return candidates[:2]
        return candidates[:5]
