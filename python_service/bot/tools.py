"""
LangChain tools and helper functions for the Viha bot.

Tools:
    - extract_customer_requirements
    - calculate_timeline_urgency
    - search_matching_products

Helpers:
    - format_timeline_display
    - build_handoff_reason
"""

import os
import re
from datetime import datetime, timedelta

import psycopg
from langchain.tools import tool

from bot.cities import KNOWN_CITIES, CITY_DISPLAY_OVERRIDES
from models.bot_models import ExtractedRequirements


# ============================================================
# TOOL 1 — Extract Customer Requirements
# ============================================================

@tool
def extract_customer_requirements(message: str) -> dict:
    """
    Extract customer requirements: quantity, budget (including ranges), timeline, location.
    Supports: single budget, ranges, below/above patterns.
    Auto-adds +20 Rs buffer to max budget for customer flexibility.
    """
    msg_lower = message.lower()
    extracted = {
        "quantity":           None,
        "budget_min":         None,
        "budget_max":         None,
        "budget_display":     None,
        "timeline":           None,
        "location":           None,
        "preferences":        [],
        "needs_confirmation": False,
    }

    all_numbers = re.findall(r'\b(\d+)\b', message)

    # ── STEP 1: Timeline ──────────────────────────────────────────────────
    date_numbers = set()

    vague_keywords = [
        "next week", "this week", "within this week", "by this week",
        "next month", "this month", "within this month", "by this month",
        "in 2 weeks", "in 3 weeks", "within 2 weeks",
        "in 3 days", "in 5 days", "in 10 days", "within 5 days",
        "end of week", "end of month", "month", "week",
    ]

    has_vague_timeline = any(kw in msg_lower for kw in vague_keywords)
    if has_vague_timeline:
        print(f"    ⚠️  Vague timeline detected — will ask for exact date")

    urgent_map = {
        "asap": "asap", "urgent": "asap", "immediately": "asap",
        "today": "today", "tomorrow": "tomorrow",
    }
    for kw, val in urgent_map.items():
        if kw in msg_lower:
            extracted["timeline"] = val
            print(f"    📅 Accepted urgent timeline: {kw}")
            break

    if not extracted["timeline"] and not has_vague_timeline:
        date_patterns = [
            r'\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s{0,2}(\d{1,2})(?:st|nd|rd|th)?\b',
            r'\b(\d{1,2})(?:st|nd|rd|th)?\s{0,2}(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\b',
            r'\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})\b',
            r'\b(\d{1,2})[/\-.](\d{1,2})\b',
        ]
        for pattern in date_patterns:
            for match in re.finditer(pattern, msg_lower, re.IGNORECASE):
                text = match.group(0).strip()
                if '\n' in text:
                    continue
                extracted["timeline"] = text
                print(f"    📅 Extracted exact date: {text}")
                for i in range(1, len(match.groups()) + 1):
                    g = match.group(i)
                    if g and g.isdigit():
                        date_numbers.add(g)
                break
            if extracted["timeline"]:
                break

    if has_vague_timeline and not extracted["timeline"]:
        extracted["timeline"] = "NEEDS_EXACT_DATE"
        print(f"    ⚠️  Timeline marked as NEEDS_EXACT_DATE")

    # ── STEP 2: Quantity ──────────────────────────────────────────────────
    qty_patterns = [
        r'(\d+)\s*(?:pieces|pcs|piece|family|families|people)',
        r'(?:quantity|qty|need|want|for)\s*:?\s*(\d+)',
    ]
    qty_used_keyword = False
    for pattern in qty_patterns:
        m = re.search(pattern, msg_lower)
        if m:
            extracted["quantity"] = int(m.group(1))
            qty_used_keyword = True
            print(f"    📦 Extracted quantity (keyword): {m.group(1)}")
            break

    # ── STEP 3: Budget ────────────────────────────────────────────────────
    budget_extracted    = False
    budget_used_keyword = False

    # below / under / upto
    m = re.search(r'(?:below|under|upto|up\s*to)\s*(\d+)', msg_lower)
    if m:
        mx = int(m.group(1))
        extracted.update(budget_min=0, budget_max=mx + 20, budget_display=f"below ₹{mx}")
        budget_extracted = True
        print(f"    💰 Budget (below): 0 to {mx} (showing up to {mx + 20})")

    # above / over
    if not budget_extracted:
        m = re.search(r'(?:above|over|more\s*than)\s*(\d+)', msg_lower)
        if m:
            mn = int(m.group(1))
            extracted.update(budget_min=mn, budget_max=10000, budget_display=f"above ₹{mn}")
            budget_extracted = True
            print(f"    💰 Budget (above): {mn} to 10000")

    # range  X to Y / X-Y
    if not budget_extracted:
        for pattern in [r'(\d+)\s*(?:to|-)\s*(\d+)\s*(?:rs|rupees)?', r'(\d+)\s*(?:to|-)\s*(\d+)']:
            m = re.search(pattern, msg_lower)
            if m:
                mn, mx = sorted([int(m.group(1)), int(m.group(2))])
                extracted.update(budget_min=mn, budget_max=mx + 20, budget_display=f"₹{mn} to ₹{mx}")
                budget_extracted = True
                print(f"    💰 Budget (range): {mn} to {mx} (showing up to {mx + 20})")
                break

    # single keyword budget
    if not budget_extracted:
        for pattern in [
            r'(?:budget|price)\s*:?\s*(\d+)',
            r'(\d+)\s*(?:rupees|rs|₹|per\s*piece)',
            r'₹\s*(\d+)',
            r'(\d+)\s*rs\b',
        ]:
            m = re.search(pattern, msg_lower)
            if m:
                b = int(m.group(1))
                extracted.update(budget_min=0, budget_max=b + 20, budget_display=f"₹{b}")
                budget_extracted    = True
                budget_used_keyword = True
                print(f"    💰 Budget (single): {b} (showing up to {b + 20})")
                break

    # ── STEP 4: Position-based fallback ───────────────────────────────────
    print(f"    🔍 all_numbers={all_numbers}  date_numbers={date_numbers}")

    if extracted["quantity"] is None or extracted["budget_max"] is None:
        non_date = [int(n) for n in all_numbers if n not in date_numbers]
        print(f"    🔍 non_date_numbers={non_date}")

        if len(non_date) >= 2:
            if extracted["quantity"] is None:
                extracted["quantity"] = non_date[0]
                print(f"    📦 Quantity (position): {non_date[0]}")
            if extracted["budget_max"] is None:
                b = non_date[1]
                extracted.update(budget_min=0, budget_max=b + 20, budget_display=f"₹{b}")
                print(f"    💰 Budget (position): {b} (showing up to {b + 20})")
        elif len(non_date) == 1:
            n = non_date[0]
            if extracted["quantity"] is None:
                extracted["quantity"] = n
            elif extracted["budget_max"] is None:
                extracted.update(budget_min=0, budget_max=n + 20, budget_display=f"₹{n}")

    # ── STEP 5: Location ──────────────────────────────────────────────────
    for city in KNOWN_CITIES:
        if city in msg_lower:
            display = CITY_DISPLAY_OVERRIDES.get(city, city.title())
            extracted["location"] = display
            break

    # Fallback: capitalised single word in short messages
    if not extracted["location"]:
        words = message.strip().split()
        if len(words) <= 3:
            skip = {"hello", "hi", "what", "when", "where"}
            for word in words:
                w = word.strip()
                if len(w) >= 3 and w[0].isupper() and w.isalpha() and w.lower() not in skip:
                    extracted["location"] = w
                    break

    # ── STEP 6: Preferences ───────────────────────────────────────────────
    pref_map = {
        "eco_friendly":  ["eco", "green"],
        "traditional":   ["traditional", "ethnic"],
        "modern":        ["modern", "contemporary"],
        "premium":       ["premium", "luxury"],
    }
    for pref, keywords in pref_map.items():
        if any(kw in msg_lower for kw in keywords):
            extracted["preferences"].append(pref)

    # ── STEP 7: Confirmation logic ────────────────────────────────────────
    if extracted["quantity"] is not None and extracted["budget_max"] is not None:
        if not qty_used_keyword and not budget_used_keyword:
            extracted["needs_confirmation"] = True
            print(f"    ⚠️  Position-based only — will ask confirmation")

    return extracted


# ============================================================
# TOOL 2 — Calculate Timeline Urgency
# ============================================================

@tool
def calculate_timeline_urgency(timeline: str) -> dict:
    """
    Calculate delivery date and urgency level from a timeline string.
    Validates that dates are in the future and within 1 year.
    """
    from dateutil import parser as date_parser

    today = datetime.now()

    instant = {
        "asap":      {"days": 1, "urgency": "critical"},
        "today":     {"days": 0, "urgency": "critical"},
        "tomorrow":  {"days": 1, "urgency": "high"},
    }

    if timeline.lower() in instant:
        cfg             = instant[timeline.lower()]
        delivery_date   = today + timedelta(days=cfg["days"])
        days_remaining  = cfg["days"]
        urgency         = cfg["urgency"]
    else:
        try:
            parsed = date_parser.parse(timeline, fuzzy=True, default=today.replace(year=today.year))
            if parsed < today:
                parsed = parsed.replace(year=today.year + 1)
            if parsed > today + timedelta(days=365):
                print(f"    ⚠️  Date too far in future — defaulting to 1 month")
                parsed = today + timedelta(days=30)

            delivery_date  = parsed
            days_remaining = (parsed - today).days
            if days_remaining <= 2:
                urgency = "critical"
            elif days_remaining <= 7:
                urgency = "high"
            elif days_remaining <= 14:
                urgency = "medium"
            else:
                urgency = "low"
        except Exception as e:
            print(f"    ❌ Date parse failed: {e} — defaulting to 1 week")
            delivery_date  = today + timedelta(days=7)
            days_remaining = 7
            urgency        = "medium"

    return {
        "delivery_date":  delivery_date.strftime("%d %B %Y"),
        "days_remaining": days_remaining,
        "urgency_level":  urgency,
        "is_rush_order":  urgency in ["critical", "high"],
    }


# ============================================================
# TOOL 3 — Search Matching Products
# ============================================================

@tool
def search_matching_products(
    budget_min:  int = 0,
    budget_max:  int = 10000,
    quantity:    int = 1,
    preferences: list[str] | None = None,
) -> list:
    """
    Search products from Supabase including size/type/design variants.
    Returns ALL matching products with correct quantity-based pricing.
    Only returns AVAILABLE variants.
    """
    preferences      = preferences or []
    matching_products = []

    conn   = psycopg.connect(os.getenv("SUPABASE_DB_URL"))
    cursor = conn.cursor()

    try:
        # ── Products WITH variants ────────────────────────────────────────
        cursor.execute("""
            SELECT p.id, p.name, p.category, p.min_order,
                   pv.size, pv.type, pv.design_name,
                   pv.quantity_range, pv.price_per_piece, pv.image_url
            FROM   products p
            JOIN   product_variants pv ON p.id = pv.product_id
            WHERE  p.min_order <= %s
              AND  pv.is_available = TRUE
              AND  p.has_variants  = TRUE
            ORDER  BY p.name, pv.size, pv.price_per_piece
        """, (quantity,))

        for row in cursor.fetchall():
            _, name, category, min_order, size, vtype, design, qty_range, price, img_url = row

            in_range = False
            if '+' in qty_range:
                in_range = quantity >= int(qty_range.split('+')[0].strip())
            elif '-' in qty_range:
                parts    = qty_range.split('-')
                in_range = int(parts[0].strip()) <= quantity <= int(parts[1].split()[0].strip())

            if not in_range or not (budget_min <= price <= budget_max):
                continue

            variant_name = name
            if size:   variant_name += f" - {size}"
            if vtype:  variant_name += f" ({vtype})"
            if design: variant_name += f" - {design}"

            score = _relevance_score(price, budget_max, category, preferences)
            matching_products.append({
                "name": variant_name, "price": price, "category": category,
                "min_order": min_order, "image_url": img_url, "relevance_score": score,
            })

        # ── Products WITHOUT variants ─────────────────────────────────────
        cursor.execute("""
            SELECT p.id, p.name, p.category, p.image_url, p.min_order,
                   pt.quantity_range, pt.price_per_piece
            FROM   products p
            JOIN   pricing_tiers pt ON p.id = pt.product_id
            WHERE  p.min_order <= %s
              AND  (p.has_variants = FALSE OR p.has_variants IS NULL)
            ORDER  BY p.id, pt.price_per_piece
        """, (quantity,))

        products_dict: dict = {}
        for row in cursor.fetchall():
            pid, name, category, image_url, min_order, qty_range, price = row
            if pid not in products_dict:
                products_dict[pid] = {
                    "id": pid, "name": name, "category": category,
                    "image_url": image_url, "min_order": min_order, "pricing": [],
                }
            products_dict[pid]["pricing"].append({"quantity_range": qty_range, "price_per_piece": price})

        for product in products_dict.values():
            applicable_price = None
            for tier in product["pricing"]:
                qr, price = tier["quantity_range"], tier["price_per_piece"]
                if '+' in qr:
                    if quantity >= int(qr.split('+')[0].strip()):
                        applicable_price = price
                elif '-' in qr:
                    parts = qr.split('-')
                    if int(parts[0].strip()) <= quantity <= int(parts[1].split()[0].strip()):
                        applicable_price = price
                        break

            if applicable_price is None or not (budget_min <= applicable_price <= budget_max):
                continue

            score = _relevance_score(applicable_price, budget_max, product["category"], preferences)
            matching_products.append({
                "name": product["name"], "price": applicable_price,
                "category": product["category"], "min_order": product["min_order"],
                "image_url": product["image_url"], "relevance_score": score,
            })

    finally:
        cursor.close()
        conn.close()

    matching_products.sort(key=lambda x: x["relevance_score"], reverse=True)
    return matching_products


def _relevance_score(price: float, budget_max: float, category: str, preferences: list[str]) -> int:
    """Calculate relevance score for product ranking."""
    score = 100
    if "eco_friendly" in preferences and category == "Eco-Friendly":
        score += 30
    if "traditional" in preferences and category in ["Traditional", "Premium Traditional"]:
        score += 25
    if "premium" in preferences and "Premium" in category:
        score += 20
    score += int((1 - price / budget_max) * 20)
    return score


# All tools exported as a list for LangGraph
TOOLS = [extract_customer_requirements, calculate_timeline_urgency, search_matching_products]


# ============================================================
# HELPERS
# ============================================================

def format_timeline_display(timeline: str) -> str:
    """Convert internal timeline code to customer-friendly text."""
    display_map = {
        "asap": "ASAP", "today": "Today", "tomorrow": "Tomorrow",
        "this_week": "This week", "next_week": "Next week",
        "two_weeks": "In 2 weeks", "one_month": "In 1 month",
    }
    if timeline in display_map:
        return display_map[timeline]

    # Format raw dates like "feb23" → "Feb 23"
    formatted = re.sub(
        r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)(\d)',
        r'\1 \2', timeline.strip(), flags=re.IGNORECASE,
    )
    return formatted.capitalize()


def build_handoff_reason(reason_type: str, req: ExtractedRequirements | None = None, message: str = "") -> str:
    """Build a clear handoff reason message for wife alerts."""
    reasons = {
        "image_sent":          "🚨 Reason: Customer sent image (bot cannot identify products from images)",
        "quick_price_query":   "🚨 Reason: Quick price query (likely referring to Instagram post)",
        "products_shown":      "✅ Reason: Bot showed product options, customer needs personalisation help",
        "no_products":         "⚠️ Reason: No products match customer's budget",
        "llm_classification":  "🚨 Reason: Customer query requires human assistance",
        "bot_error":           "❌ Reason: Bot encountered an error",
    }
    if reason_type == "unhandleable_query":
        return f"🚨 Reason: Unhandleable query — {message[:50]}..."
    return reasons.get(reason_type, f"🚨 Reason: {reason_type}")