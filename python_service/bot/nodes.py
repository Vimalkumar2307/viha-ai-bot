"""
LangGraph node functions and routers for the Viha bot.

Nodes:
    1. greeting_node
    2. intent_classifier_node
    3. requirement_extraction_node
    4. ask_confirmation_node
    5. validation_node
    6. product_search_node
    7. recommendation_node
    8. product_selection_node
    9. order_confirmation_node

Routers:
    - validation_router
    - post_intent_router (defined inline in graph.py)
"""

import re
from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate

from bot.config import llm
from bot.tools import (
    extract_customer_requirements,
    calculate_timeline_urgency,
    search_matching_products,
    format_timeline_display,
    build_handoff_reason,
)
from models.bot_models import (
    BotState,
    CustomerIntent,
    ExtractedRequirements,
    ValidationResult,
)


# ============================================================
# NODE 1 — Greeting
# ============================================================

def greeting_node(state: BotState) -> dict:
    print("  🟦 NODE: GREETING")
    return {
        "messages": [AIMessage(content=(
            "Hello mam/sir! 😊\n\n"
            "Could you please tell your return gift requirement:\n\n"
            "1. Quantity\n"
            "2. Budget per piece\n"
            "3. When needed\n"
            "4. Delivery location\n\n"
            "Thank you!"
        ))],
        "current_stage": "intent_classification",
        "has_greeted":   True,
        "error_count":   0,
    }


# ============================================================
# NODE 2 — Intent Classifier
# ============================================================

def intent_classifier_node(state: BotState) -> dict:
    print("  🟨 NODE: INTENT CLASSIFICATION")

    # Already handed off — stay silent
    if state.get("needs_human_handoff"):
        print("    🚫 Already handed off — bot silent")
        return {"current_stage": "handoff"}

    user_messages = [m for m in state["messages"] if isinstance(m, HumanMessage)]
    if not user_messages:
        return {}

    last_msg      = user_messages[-1].content
    msg_lower     = last_msg.lower().strip()
    current_stage = state.get("current_stage")

    # PRIORITY 1: Image → immediate handoff
    if "[IMAGE_SENT]" in last_msg:
        print("    📸 IMAGE — handing off")
        return {"current_stage": "handoff", "needs_human_handoff": True, "handoff_reason": "image_sent"}

    # PRIORITY 2: Quick price query
    quick_queries = ['pp', 'price please', 'price pls', 'rate pls', 'rate please',
                     'available?', 'stock?', 'available', 'in stock']
    if len(last_msg) <= 20 and any(q in msg_lower for q in quick_queries):
        print(f"    🎯 Quick price query: '{last_msg}' — handing off")
        return {"current_stage": "handoff", "needs_human_handoff": True, "handoff_reason": "quick_price_query"}

    # PRIORITY 3: Confirmation response
    if current_stage == "awaiting_confirmation":
        if msg_lower in ["yes", "y", "ok", "correct", "confirm", "right", "hai"]:
            print("    ✅ Confirmed")
            req = state.get("requirements")
            if req:
                req.needs_confirmation = False
            return {"current_stage": "validation", "requirements": req}
        else:
            print("    🔄 Correction requested")
            return {"current_stage": "requirement_extraction"}

    # PRIORITY 4: Greeting / reset
    greeting_keywords = ["hello", "hi", "hey", "start", "new", "hai"]
    if any(kw == msg_lower for kw in greeting_keywords):
        print("    🔄 Greeting detected")
        if current_stage == "handoff":
            return {
                "current_stage": "requirement_extraction",
                "requirements": None, "recommended_products": None,
                "selected_product": None, "validation": None,
                "has_greeted": True, "needs_human_handoff": False, "handoff_reason": None,
            }
        if current_stage in ["product_selection", "order_confirmation"]:
            return {
                "current_stage": "requirement_extraction",
                "requirements": None, "recommended_products": None,
                "selected_product": None, "validation": None, "has_greeted": True,
            }
        return {"current_stage": "requirement_extraction"}

    # PRIORITY 5: Simple number or single word → continue
    if msg_lower.isdigit():
        return {"current_stage": "requirement_extraction"}
    if len(msg_lower.split()) == 1 and len(msg_lower) > 2:
        return {"current_stage": "requirement_extraction"}

    # Date patterns → continue
    for pat in [r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)', r'\d{1,2}[/\-]\d{1,2}', r'tomorrow|today|asap']:
        if re.search(pat, msg_lower):
            return {"current_stage": "requirement_extraction"}

    # PRIORITY 6: Unhandleable topics
    unhandleable = [
        "refund", "cancel", "complaint", "issue", "problem",
        "shipping cost", "delivery charge", "payment method",
        "customization", "customize", "design change",
        "bulk discount", "wholesale",
    ]
    for pattern in unhandleable:
        if pattern in msg_lower:
            print(f"    🚨 Unhandleable: '{pattern}'")
            return {"current_stage": "handoff", "needs_human_handoff": True, "handoff_reason": "unhandleable_query"}

    # PRIORITY 7: LLM classification for complex messages
    prompt = ChatPromptTemplate.from_messages([
        ("system", """Classify the customer's message:
- browse_products: wants products or is providing requirements
- track_order: asking about existing order → CANNOT HANDLE
- ask_question: general policy/shipping question → CANNOT HANDLE
- complaint: has an issue → CANNOT HANDLE
- greeting: saying hi

If providing requirements, classify as browse_products.
Respond with JSON only: {{"intent": "...", "confidence": 0.95}}"""),
        ("human", "{message}"),
    ])
    response   = (prompt | llm).invoke({"message": last_msg})
    intent_text = response.content.lower()

    if any(x in intent_text for x in ["track_order", "ask_question", "complaint"]):
        print(f"    🚨 LLM classified as non-product: {intent_text[:40]}")
        return {"current_stage": "handoff", "needs_human_handoff": True, "handoff_reason": "llm_classification"}

    intent = "browse_products"
    print(f"    🎯 Intent: {intent}")
    return {
        "intent": CustomerIntent(intent=intent, confidence=0.85, entities_mentioned=[]),
        "current_stage": "requirement_extraction",
    }


# ============================================================
# NODE 3 — Requirement Extraction
# ============================================================

def requirement_extraction_node(state: BotState) -> dict:
    print("  🟩 NODE: REQUIREMENT EXTRACTION")

    user_messages = [m for m in state["messages"] if isinstance(m, HumanMessage)]
    last_msg      = user_messages[-1].content if user_messages else ""
    print(f"    📥 Input: '{last_msg}'")

    current_req = state.get("requirements")

    # Special case: single number → sequential fill
    if last_msg.strip().isdigit() and current_req:
        number = int(last_msg.strip())
        if current_req.quantity is None:
            print(f"    📦 Sequential fill: quantity = {number}")
            current_req.quantity = number
            return {"requirements": current_req, "current_stage": "validation"}
        if current_req.budget_max is None:
            print(f"    💰 Sequential fill: budget = {number}")
            current_req.budget_min     = 0
            current_req.budget_max     = number + 20
            current_req.budget_display = f"₹{number}"
            return {"requirements": current_req, "current_stage": "validation"}

    # Normal extraction
    extracted = extract_customer_requirements.invoke({"message": last_msg})
    print(f"    🔧 Extracted: {extracted}")

    if current_req:
        msg_lower        = last_msg.lower()
        has_qty_kw       = any(w in msg_lower for w in ["quantity", "qty", "pieces", "pcs"])
        has_budget_kw    = any(w in msg_lower for w in ["budget", "price", "rs", "rupees", "₹"])

        for key, value in extracted.items():
            if key == "needs_confirmation":
                setattr(current_req, key, value)
                continue
            if value is None or value == []:
                continue
            current_value = getattr(current_req, key)
            if current_value is None:
                setattr(current_req, key, value)
            elif key in ["quantity", "budget_min", "budget_max"]:
                if (key == "quantity" and has_qty_kw) or (key in ["budget_min", "budget_max"] and has_budget_kw):
                    setattr(current_req, key, value)
            else:
                setattr(current_req, key, value)
        requirements = current_req
    else:
        requirements = ExtractedRequirements(**extracted)

    print(f"    📊 qty={requirements.quantity}  budget={requirements.budget_display}  "
          f"timeline={requirements.timeline}  location={requirements.location}  "
          f"confirm={requirements.needs_confirmation}")

    return {"requirements": requirements, "current_stage": "validation"}


# ============================================================
# ROUTER — Validation
# ============================================================

def validation_router(state: BotState) -> Literal["validate", "ask_confirmation"]:
    req = state.get("requirements")
    if not req:
        return "ask_confirmation"

    all_present = all([
        req.quantity  is not None,
        req.budget_max is not None,
        req.timeline  is not None and req.timeline != "NEEDS_EXACT_DATE",
        req.location  is not None,
    ])

    if not all_present:
        print("    ⚠️  Missing required info")
        return "ask_confirmation"
    if req.needs_confirmation:
        print("    ⚠️  Needs confirmation")
        return "ask_confirmation"

    print("    ✅ All info collected")
    return "validate"


# ============================================================
# NODE 4 — Ask Confirmation / Missing Info
# ============================================================

def ask_confirmation_node(state: BotState) -> dict:
    print("  🟧 NODE: ASK CONFIRMATION/MISSING INFO")

    req = state.get("requirements")
    if not req:
        return {"current_stage": "requirement_extraction"}

    # Exact date needed
    if req.timeline == "NEEDS_EXACT_DATE":
        return {
            "messages": [AIMessage(content=(
                "Could you please provide an exact date?\n"
                "This helps us plan your delivery better. Thank you! 😊"
            ))],
            "current_stage": "requirement_extraction",
        }

    # Confirmation needed
    if req.needs_confirmation and req.quantity and req.budget_max:
        return {
            "messages": [AIMessage(content=(
                f"Can you please confirm?\n\n"
                f"Quantity: {req.quantity} pieces\n"
                f"Budget: {req.budget_display} per piece\n\n"
                f'Reply "yes" to confirm.'
            ))],
            "current_stage": "awaiting_confirmation",
        }

    # Ask for missing fields
    missing = []
    if not req.quantity:    missing.append("Quantity")
    if not req.budget_max:  missing.append("Budget per piece")
    if not req.timeline:    missing.append("When needed")
    if not req.location:    missing.append("Delivery location")

    if len(missing) == 1:
        msg = f"Could you please share {missing[0]}?"
    else:
        items = ", ".join(missing[:-1]) + " and " + missing[-1]
        msg   = f"Could you please share {items}?"

    return {"messages": [AIMessage(content=msg)], "current_stage": "requirement_extraction"}


# ============================================================
# NODE 5 — Validation
# ============================================================

def validation_node(state: BotState) -> dict:
    print("  🟪 NODE: VALIDATION")
    req    = state["requirements"]
    result = calculate_timeline_urgency.invoke({"timeline": req.timeline})
    print("    🔍 Validation: ✅ PASS")
    return {
        "validation": ValidationResult(
            is_valid      = True,
            delivery_date = result["delivery_date"],
            urgency_level = result["urgency_level"],
        ),
        "current_stage": "product_search",
    }


# ============================================================
# NODE 6 — Product Search
# ============================================================

def product_search_node(state: BotState) -> dict:
    print("  🟦 NODE: PRODUCT SEARCH")
    req     = state["requirements"]
    params  = {
        "budget_min":  req.budget_min or 0,
        "budget_max":  req.budget_max or 10000,
        "quantity":    req.quantity,
    }
    if req.preferences:
        params["preferences"] = req.preferences

    products = search_matching_products.invoke(params)
    print(f"    🔎 Found {len(products)} products")
    return {"recommended_products": products, "current_stage": "recommendation"}


# ============================================================
# NODE 7 — Recommendation
# ============================================================

def recommendation_node(state: BotState) -> dict:
    print("  🟨 NODE: RECOMMENDATION")
    products = state["recommended_products"]
    req      = state["requirements"]

    if not products:
        return {
            "messages": [AIMessage(content=(
                f"Sorry mam/sir, no products available for {req.budget_display} per piece.\n\n"
                "Our team will help you find alternatives.\n\nThank you! 🙏"
            ))],
            "current_stage":       "handoff",
            "needs_human_handoff": True,
            "handoff_reason":      "no_products",
        }

    timeline_display     = format_timeline_display(req.timeline)
    requirements_summary = (
        "Based on your requirement,\n\n"
        f"Number of pieces: {req.quantity} pieces\n"
        f"Budget: {req.budget_display} per piece\n"
        f"Delivery location: {req.location}\n"
        f"When needed: {timeline_display}\n\n"
        f"Here are {len(products)} options for you:"
    )

    print(f"    📸 Will send {len(products)} product images → handoff")
    return {
        "messages":                      [AIMessage(content="[SEND_PRODUCT_IMAGES_WITH_SUMMARY]")],
        "conversation_history_summary":  requirements_summary,
        "current_stage":                 "handoff",
        "needs_human_handoff":           True,
        "handoff_reason":                "products_shown",
    }


# ============================================================
# NODE 8 — Product Selection
# ============================================================

def product_selection_node(state: BotState) -> dict:
    print("  🟩 NODE: PRODUCT SELECTION")
    user_messages = [m for m in state["messages"] if isinstance(m, HumanMessage)]
    if not user_messages:
        return {}

    last_msg = user_messages[-1].content.strip().lower()
    products = state["recommended_products"]
    if not products:
        return {"current_stage": "handoff", "needs_human_handoff": True}

    selected = None
    if last_msg.isdigit():
        idx = int(last_msg) - 1
        if 0 <= idx < len(products):
            selected = products[idx]
    if not selected:
        for p in products:
            if p["name"].lower() in last_msg or last_msg in p["name"].lower():
                selected = p
                break

    if not selected:
        return {
            "messages": [AIMessage(content=(
                "I didn't catch that! 😅\n\n"
                "Please reply with:\n• A number (1, 2, 3…)\n• Or the product name\n\n"
                "Which product would you like?"
            ))],
            "current_stage": "product_selection",
        }

    print(f"    ✅ Selected: {selected['name']}")
    return {"selected_product": selected, "current_stage": "order_confirmation"}


# ============================================================
# NODE 9 — Order Confirmation
# ============================================================

def order_confirmation_node(state: BotState) -> dict:
    print("  🟦 NODE: ORDER CONFIRMATION")
    product = state.get("selected_product")
    req     = state.get("requirements")

    if not product or not req:
        return {
            "messages": [AIMessage(content=(
                "Our team will contact you shortly to complete your order.\n\nThank you! 🙏"
            ))],
            "current_stage":       "handoff",
            "needs_human_handoff": True,
        }

    total = product["price"] * req.quantity
    msg   = (
        f"Thank you!\n\n{product['name']}\n"
        f"Quantity: {req.quantity} pieces\n"
        f"Total: ₹{total:,}\n"
    )
    if req.location:
        msg += f"Location: {req.location}\n"
    msg += "\nOur team will contact you shortly.\n\nThank you! 🙏"

    return {"messages": [AIMessage(content=msg)], "current_stage": "handoff"}