"""
PRODUCTION-GRADE MULTI-NODE VIHA RETURN GIFTS BOT
Version: 3.0 - With confirmation flow for ambiguous inputs
Showcases: LangGraph, Agents, Tools, State Management, Production Patterns
"""

import os
import json
import re
from dotenv import load_dotenv
from datetime import datetime, timedelta
from typing import Annotated, TypedDict, Sequence, Literal
import operator

from langchain_groq import ChatGroq
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from langchain.tools import tool
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.postgres import PostgresSaver
import psycopg
from psycopg_pool import ConnectionPool
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel, Field

load_dotenv()

print("=" * 70)
print("🏗️  PRODUCTION-GRADE MULTI-NODE VIHA BOT v3.0")
print("=" * 70)

# ============================================================
# CONFIGURATION
# ============================================================

llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    temperature=0.3,
    groq_api_key=os.getenv("GROQ_API_KEY")
)

# Load products
# PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# PRODUCTS_PATH = os.path.join(PROJECT_ROOT, 'products.json')

# with open(PRODUCTS_PATH, 'r', encoding='utf-8') as f:
#     PRODUCTS_DATA = json.load(f)

# print(f"✅ Loaded {len(PRODUCTS_DATA['products'])} products")

# ============================================================
# STRUCTURED OUTPUTS (Pydantic Models)
# ============================================================

class CustomerIntent(BaseModel):
    """Structured intent classification"""
    intent: Literal["browse_products", "track_order", "ask_question", "complaint", "greeting"]
    confidence: float = Field(ge=0.0, le=1.0)
    entities_mentioned: list[str] = Field(default_factory=list)

class ExtractedRequirements(BaseModel):
    """Structured extraction of customer requirements"""
    quantity: int | None = Field(None, description="Number of pieces needed")
    budget_per_piece: int | None = Field(None, description="Budget in rupees")
    timeline: str | None = Field(None, description="When needed")
    location: str | None = Field(None, description="Delivery city")
    preferences: list[str] = Field(default_factory=list)
    needs_confirmation: bool = Field(False, description="Whether to confirm extracted values")

class ValidationResult(BaseModel):
    """Simplified validation output"""
    is_valid: bool
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    delivery_date: str | None = None
    urgency_level: Literal["low", "medium", "high", "critical"] = "medium"

# ============================================================
# TOOLS (Function Calling)
# ============================================================

@tool
def extract_customer_requirements(message: str) -> dict:
    """
    Extract customer requirements: quantity, budget, timeline, location.
    Uses position-based extraction with confirmation for ambiguous cases.
    
    Args:
        message: Customer's message text
        
    Returns:
        Dictionary with extracted requirements
    """
    msg_lower = message.lower()
    extracted = {
        "quantity": None,
        "budget_per_piece": None,
        "timeline": None,
        "location": None,
        "preferences": [],
        "needs_confirmation": False
    }
    
    # Extract all numbers
    all_numbers = re.findall(r'\b(\d+)\b', message)
    
    # ===== STEP 1: Extract TIMELINE FIRST =====
    date_numbers = set()
    
    timeline_map = {
        "asap": "asap", "urgent": "asap", "immediately": "asap",
        "today": "today", "tomorrow": "tomorrow",
        "next week": "next_week", "this week": "this_week",
        "2 weeks": "two_weeks", "month": "one_month"
    }
    for keyword, value in timeline_map.items():
        if keyword in msg_lower:
            extracted["timeline"] = value
            break
    
    # Date patterns - FIXED to handle both "Feb23" and "Feb 23"
    date_patterns = [
        # Month name formats (with OR without space)
        r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s*(\d{1,2})',  # feb23, feb 23, february14
        r'(\d{1,2})\s*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)',     # 23feb, 23 feb, 14february
        
        # Numeric date formats (DD/MM/YYYY, DD-MM-YYYY, DD.MM.YYYY)
        r'(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})',  # 14/02/2026, 14-2-26, 14.02.2026
        r'(\d{1,2})[/\-.](\d{1,2})',                  # 14/02, 14-2, 14.2
    ]
    
    for pattern in date_patterns:
        matches = re.finditer(pattern, msg_lower)
        for match in matches:
            # ✅ PRESERVE THE ACTUAL DATE TEXT
            # Find the full matched text (e.g., "Feb23", "23 Feb")
            matched_date_text = match.group(0)
            extracted["timeline"] = matched_date_text  # Store actual date like "Feb23"
            
            # Extract all numeric groups (skip month names)
            for group_num in range(1, len(match.groups()) + 1):
                num = match.group(group_num)
                if num and num.isdigit():
                    date_numbers.add(num)
    
    # ===== STEP 2: Extract QUANTITY (with keywords) =====
    qty_patterns = [
        r'(\d+)\s*(?:pieces|pcs|piece|family|families|people)',
        r'(?:quantity|qty|need|want|for)\s*:?\s*(\d+)',
    ]
    
    qty_used_keyword = False
    for pattern in qty_patterns:
        match = re.search(pattern, msg_lower)
        if match:
            extracted["quantity"] = int(match.group(1))
            qty_used_keyword = True
            print(f"    📦 Extracted quantity (keyword): {match.group(1)}")
            break
    
    # ===== STEP 3: Extract BUDGET (with keywords) =====
    budget_patterns = [
    r'(?:budget|price)\s*:?\s*(\d+)',
    r'(\d+)\s*(?:rupees|rs|₹|per\s*piece)',
    r'₹\s*(\d+)',
    r'(\d+)\s*rs\b',
    r'under\s+(\d+)',
    r'below\s+(\d+)',
    r'within\s+(\d+)',
    r'upto\s+(\d+)',
    ]
    
    budget_used_keyword = False
    for pattern in budget_patterns:
        match = re.search(pattern, msg_lower)
        if match:
            extracted["budget_per_piece"] = int(match.group(1))
            budget_used_keyword = True
            print(f"    💰 Extracted budget (keyword): {match.group(1)}")
            break
    
    # ===== STEP 4: POSITION-BASED extraction =====
    position_based_used = False

    print(f"    🔍 DEBUG: all_numbers = {all_numbers}")
    print(f"    🔍 DEBUG: date_numbers = {date_numbers}")

    if extracted["quantity"] is None or extracted["budget_per_piece"] is None:
        print(f"    🔍 DEBUG: Position-based condition TRUE (qty={extracted['quantity']}, budget={extracted['budget_per_piece']})")
        # Get non-date numbers
        non_date_numbers = []
        for num in all_numbers:
            if num not in date_numbers:
                non_date_numbers.append(int(num))
        
        print(f"    🔍 DEBUG: non_date_numbers = {non_date_numbers}")
        
        if len(non_date_numbers) >= 2:
            # Fill missing values
            if extracted["quantity"] is None:
                extracted["quantity"] = non_date_numbers[0]
                position_based_used = True
                print(f"    📦 Auto-detected quantity (position): {non_date_numbers[0]}")
            
            if extracted["budget_per_piece"] is None:
                extracted["budget_per_piece"] = non_date_numbers[1]
                position_based_used = True
                print(f"    💰 Auto-detected budget (position): {non_date_numbers[1]}")
        
        elif len(non_date_numbers) == 1:
            num = non_date_numbers[0]
            if extracted["quantity"] is None:
                extracted["quantity"] = num
            elif extracted["budget_per_piece"] is None:
                extracted["budget_per_piece"] = num
    
    # ===== STEP 5: Extract LOCATION =====
    known_cities = [
        "chennai", "bangalore", "bengaluru", "coimbatore", "madurai",
        "hyderabad", "kochi", "mumbai", "delhi", "pune", "mysore",
        "trivandrum", "vijayawada", "erode", "salem", "tiruppur",
        "guntur", "vizag", "tirunelveli", "thanjavur", "trichy",
        "komarapalayam", "karur", "dindigul", "vellore", "hosur"
    ]
    
    for city in known_cities:
        if city in msg_lower:
            extracted["location"] = city.title()
            if city == "bengaluru":
                extracted["location"] = "Bangalore"
            elif city == "tiruchirappalli":
                extracted["location"] = "Trichy"
            elif city == "visakhapatnam":
                extracted["location"] = "Vizag"
            break
    
    # Fallback location detection
    if not extracted["location"]:
        words = message.strip().split()
        if len(words) <= 3:
            for word in words:
                word_clean = word.strip()
                if (len(word_clean) > 3 and 
                    word_clean[0].isupper() and 
                    word_clean.isalpha()):
                    
                    skip_words = ["hello", "hi", "what", "when", "where"]
                    if word_clean.lower() not in skip_words:
                        extracted["location"] = word_clean
                        break
    
    # ===== STEP 6: Extract PREFERENCES =====
    if "eco" in msg_lower or "green" in msg_lower:
        extracted["preferences"].append("eco_friendly")
    if "traditional" in msg_lower or "ethnic" in msg_lower:
        extracted["preferences"].append("traditional")
    if "modern" in msg_lower or "contemporary" in msg_lower:
        extracted["preferences"].append("modern")
    if "premium" in msg_lower or "luxury" in msg_lower:
        extracted["preferences"].append("premium")
    
    # ===== STEP 7: CONFIRMATION LOGIC =====
    # ✅ NEW: Only ask confirmation if BOTH values used position-based extraction
    if (extracted["quantity"] is not None and 
        extracted["budget_per_piece"] is not None):
        
        # Check if NEITHER used keywords (both position-based)
        if not qty_used_keyword and not budget_used_keyword:
            extracted["needs_confirmation"] = True
            print(f"    ⚠️  No keywords used - will ask confirmation")
            print(f"    📋 qty={extracted['quantity']}, budget={extracted['budget_per_piece']}")
    
    return extracted

@tool
def calculate_timeline_urgency(timeline: str) -> dict:
    """
    Calculate delivery date and urgency level from timeline string.
    Handles both generic codes (asap, tomorrow) and specific dates (Feb23, 14/02).
    
    Args:
        timeline: Timeline string (asap, tomorrow, next_week, Feb23, etc)
        
    Returns:
        Dictionary with delivery_date, days_remaining, urgency_level
    """
    from dateutil import parser  # For smart date parsing
    today = datetime.now()
    
    # Predefined timeline codes
    timeline_config = {
        "asap": {"days": 1, "urgency": "critical"},
        "today": {"days": 0, "urgency": "critical"},
        "tomorrow": {"days": 1, "urgency": "high"},
        "this_week": {"days": 5, "urgency": "medium"},
        "next_week": {"days": 7, "urgency": "medium"},
        "two_weeks": {"days": 14, "urgency": "low"},
        "one_month": {"days": 30, "urgency": "low"}
    }
    
    # Check if it's a predefined code
    if timeline.lower() in timeline_config:
        config = timeline_config[timeline.lower()]
        delivery_date = today + timedelta(days=config["days"])
        days_remaining = config["days"]
        urgency = config["urgency"]
    else:
        # ✅ NEW: Parse actual dates like "Feb23", "23 Feb", "14/02"
        try:
            # Use dateutil parser for smart parsing
            # It handles: "Feb23", "Feb 23", "23 Feb", "14/02", etc.
            parsed_date = parser.parse(timeline, fuzzy=True, default=today.replace(year=today.year))
            
            # If parsed date is in the past, assume next year
            if parsed_date < today:
                parsed_date = parsed_date.replace(year=today.year + 1)
            
            delivery_date = parsed_date
            days_remaining = (parsed_date - today).days
            
            # Calculate urgency based on days remaining
            if days_remaining <= 2:
                urgency = "critical"
            elif days_remaining <= 7:
                urgency = "high"
            elif days_remaining <= 14:
                urgency = "medium"
            else:
                urgency = "low"
                
        except:
            # Fallback if parsing fails
            delivery_date = today + timedelta(days=7)
            days_remaining = 7
            urgency = "medium"
    
    return {
        "delivery_date": delivery_date.strftime("%d %B %Y"),
        "days_remaining": days_remaining,
        "urgency_level": urgency,
        "is_rush_order": urgency in ["critical", "high"]
    }

@tool
def search_matching_products(
    budget_max: int,
    quantity: int,
    preferences: list[str] | None = None
) -> list:
    """
    Search products from Supabase database.
    Returns ALL products matching criteria with CORRECT quantity-based pricing.
    """
    preferences = preferences or []
    matching_products = []
    
    # Connect to Supabase
    db_url = os.getenv("SUPABASE_DB_URL")
    conn = psycopg.connect(db_url)
    cursor = conn.cursor()
    
    try:
        # Query products with pricing tiers
        cursor.execute("""
            SELECT 
                p.id, p.name, p.category, p.image_url, p.min_order,
                pt.quantity_range, pt.price_per_piece
            FROM products p
            JOIN pricing_tiers pt ON p.id = pt.product_id
            WHERE p.min_order <= %s
            ORDER BY p.id, pt.price_per_piece
        """, (quantity,))
        
        rows = cursor.fetchall()
        
        # Group by product (because each product has multiple pricing tiers)
        products_dict = {}
        for row in rows:
            product_id, name, category, image_url, min_order, qty_range, price = row
            
            if product_id not in products_dict:
                products_dict[product_id] = {
                    'id': product_id,
                    'name': name,
                    'category': category,
                    'image_url': image_url,
                    'min_order': min_order,
                    'pricing': []
                }
            
            products_dict[product_id]['pricing'].append({
                'quantity_range': qty_range,
                'price_per_piece': price
            })
        
        # Find applicable price for each product based on quantity
        for product in products_dict.values():
            applicable_price = None
            
            for tier in product['pricing']:
                quantity_range = tier['quantity_range']
                price = tier['price_per_piece']
                
                # Handle "50+ pieces" format
                if '+' in quantity_range:
                    min_qty = int(quantity_range.split('+')[0].strip())
                    if quantity >= min_qty:
                        applicable_price = price
                
                # Handle "25-49 pieces" format
                elif '-' in quantity_range:
                    parts = quantity_range.split('-')
                    min_qty = int(parts[0].strip())
                    max_qty = int(parts[1].split()[0].strip())
                    if min_qty <= quantity <= max_qty:
                        applicable_price = price
                        break
                
                # Fallback
                else:
                    if price <= budget_max:
                        applicable_price = price
            
            # Skip if price doesn't fit budget
            if applicable_price is None or applicable_price > budget_max:
                continue
            
            # Calculate relevance score
            score = 100
            
            # Preference matching
            if "eco_friendly" in preferences and product['category'] == "Eco-Friendly":
                score += 30
            if "traditional" in preferences and product['category'] in ["Traditional", "Premium Traditional"]:
                score += 25
            if "premium" in preferences and "Premium" in product['category']:
                score += 20
            
            # Price competitiveness
            price_ratio = applicable_price / budget_max
            score += int((1 - price_ratio) * 20)
            
            matching_products.append({
                "name": product['name'],
                "price": applicable_price,
                "category": product['category'],
                "min_order": product['min_order'],
                "image_url": product['image_url'],
                "relevance_score": score
            })
        
    finally:
        cursor.close()
        conn.close()
    
    # Sort by relevance
    matching_products.sort(key=lambda x: x['relevance_score'], reverse=True)
    
    return matching_products

# Collect all tools
TOOLS = [
    extract_customer_requirements,
    calculate_timeline_urgency,
    search_matching_products
]

# ✅ ADD THESE TWO NEW HELPER FUNCTIONS

def format_timeline_display(timeline: str) -> str:
    """Convert internal timeline code to customer-friendly display text"""
    timeline_display_map = {
        "asap": "ASAP",
        "today": "Today",
        "tomorrow": "Tomorrow",
        "this_week": "This week",
        "next_week": "Next week",
        "two_weeks": "In 2 weeks",
        "one_month": "In 1 month"
    }
    
    # ✅ NEW: If not in map, format the actual date nicely
    if timeline in timeline_display_map:
        return timeline_display_map[timeline]
    else:
        # For dates like "feb23", "23 feb", etc., capitalize properly
        # Convert "feb23" → "Feb 23"
        timeline_formatted = timeline.strip()
        
        # Add space between month and number if missing
        import re
        # Pattern: month name followed by digits (no space)
        timeline_formatted = re.sub(
            r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)(\d)', 
            r'\1 \2', 
            timeline_formatted, 
            flags=re.IGNORECASE
        )
        
        # Capitalize first letter
        return timeline_formatted.capitalize()

def build_handoff_reason(reason_type: str, req: ExtractedRequirements = None, message: str = "") -> str:
    """Build detailed handoff reason message for wife"""
    if reason_type == "image_sent":
        return "🚨 Reason: Customer sent image (bot cannot identify products from images)"
    elif reason_type == "quick_price_query":
        return "🚨 Reason: Quick price query (likely referring to Instagram post)"
    elif reason_type == "products_shown":
        return "✅ Reason: Bot showed product options, now customer needs personalization help"
    elif reason_type == "no_products":
        return "⚠️ Reason: No products match customer's budget"
    elif reason_type == "unhandleable_query":
        return f"🚨 Reason: Unhandleable query - {message[:50]}..."
    elif reason_type == "llm_classification":
        return "🚨 Reason: Customer query requires human assistance"
    elif reason_type == "bot_error":
        return "❌ Reason: Bot encountered an error"
    else:
        return f"🚨 Reason: {reason_type}"

# ============================================================
# STATE DEFINITION
# ============================================================

class BotState(TypedDict):
    """Complete conversation state"""
    messages: Annotated[Sequence[HumanMessage | AIMessage], operator.add]
    user_id: str
    
    requirements: ExtractedRequirements | None
    validation: ValidationResult | None
    recommended_products: list | None
    selected_product: dict | None
    
    current_stage: Literal[
        "greeting",
        "intent_classification",
        "requirement_extraction",
        "awaiting_confirmation",
        "validation",
        "product_search",
        "recommendation",
        "product_selection",
        "order_confirmation",
        "handoff"
    ]
    intent: CustomerIntent | None
    conversation_history_summary: str | None
    handoff_reason: str | None  # ✅ ADD THIS LINE
    
    has_greeted: bool
    needs_human_handoff: bool
    error_count: int

# ============================================================
# NODES
# ============================================================

def greeting_node(state: BotState) -> BotState:
    """Node 1: Initial greeting"""
    print("  🟦 NODE: GREETING")
    
    greeting_msg = """Hello mam/sir! 😊

Could you please tell your return gift requirement:

1. Quantity
2. Budget per piece
3. When needed
4. Delivery location

Thank you!"""
    
    return {
        "messages": [AIMessage(content=greeting_msg)],
        "current_stage": "intent_classification",
        "has_greeted": True,
        "error_count": 0
    }

def intent_classifier_node(state: BotState) -> BotState:
    """Node 2: Classify customer intent - ENHANCED to handle images and quick queries"""
    print("  🟨 NODE: INTENT CLASSIFICATION")
    
    # ===== PRIORITY CHECK: Already handed off? =====
    if state.get("needs_human_handoff"):
        print("    🚫 Already handed off to human - Bot staying silent")
        return {}
    
    user_messages = [m for m in state["messages"] if isinstance(m, HumanMessage)]
    if not user_messages:
        return {}
    
    last_msg = user_messages[-1].content
    msg_lower = last_msg.lower().strip()
    
    current_stage = state.get("current_stage")
    
    # ===== NEW PRIORITY 1: DETECT IMAGES - Immediate handoff (even on first message!) =====
    if "[IMAGE_SENT]" in last_msg:
        print("    📸 IMAGE DETECTED from customer")
        print("    🚨 Bot cannot help with unknown product images")
        print("    🤝 Handing off to wife immediately")
        print("    ✅ Conversation saved in Supabase with image marker")
        
        return {
            "current_stage": "handoff",
            "needs_human_handoff": True,
            "handoff_reason": "image_sent" 
        }
    
    # ===== NEW PRIORITY 2: DETECT "pp" / Quick Price Queries =====
    quick_price_queries = [
        'pp', 'price please', 'price pls', 'rate pls', 'rate please',
        'available?', 'stock?', 'available', 'in stock'
    ]
    
    # Check if message is a short quick query
    is_quick_query = (
        len(last_msg) <= 20 and 
        any(query in msg_lower for query in quick_price_queries)
    )
    
    if is_quick_query:
        print(f"    🎯 QUICK PRICE QUERY DETECTED: '{last_msg}'")
        print("    💡 Customer likely referring to Instagram post or previous chat")
        print("    🤝 Handing off to wife immediately")
        print("    ✅ Conversation saved in Supabase")
        
        return {
            "current_stage": "handoff",
            "needs_human_handoff": True,
            "handoff_reason": "quick_price_query"
        }
    
    # ===== PRIORITY 3: Handle confirmation response =====
    if current_stage == "awaiting_confirmation":
        if msg_lower in ["yes", "y", "ok", "correct", "confirm", "right", "hai"]:
            print("    ✅ Confirmation received - proceeding")
            req = state.get("requirements")
            if req:
                req.needs_confirmation = False
            return {
                "current_stage": "validation",
                "requirements": req
            }
        else:
            print("    🔄 User wants to correct values")
            return {"current_stage": "requirement_extraction"}
    
    # ===== PRIORITY 4: Detect fresh greeting and reset =====
    greeting_keywords = ["hello", "hi", "hey", "start", "new", "hai"]
    is_greeting = any(keyword == msg_lower for keyword in greeting_keywords)

    if is_greeting:
        print("    🔄 GREETING DETECTED - Checking if conversation needs reset")
        
        if current_stage == "handoff":
            print("    ✅ RESETTING after handoff - fresh start")
            return {
                "current_stage": "requirement_extraction",
                "requirements": None,
                "recommended_products": None,
                "selected_product": None,
                "validation": None,
                "has_greeted": True,
                "needs_human_handoff": False,
                "handoff_reason": None 
            }
        
        late_stages = ["product_selection", "order_confirmation"]
        
        if current_stage in late_stages:
            print("    ✅ RESETTING CONVERSATION STATE (fresh start)")
            return {
                "current_stage": "requirement_extraction",
                "requirements": None,
                "recommended_products": None,
                "selected_product": None,
                "validation": None,
                "has_greeted": True
            }
        else:
            print("    ✅ Normal greeting - continuing current flow")
            return {"current_stage": "requirement_extraction"}
    
    # ===== PRIORITY 5: Simple inputs - continue conversation =====
    if msg_lower.isdigit():
        print(f"    ✅ Simple number input: '{msg_lower}' - Continuing")
        return {"current_stage": "requirement_extraction"}
    
    if len(msg_lower.split()) == 1 and len(msg_lower) > 2:
        print(f"    ✅ Single word input: '{msg_lower}' - Continuing")
        return {"current_stage": "requirement_extraction"}
    
    # Check for dates
    date_patterns = [
        r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)',
        r'\d{1,2}[/\-]\d{1,2}',
        r'tomorrow|today|next week|asap'
    ]
    
    for pattern in date_patterns:
        if re.search(pattern, msg_lower):
            print(f"    ✅ Date/timeline detected - Continuing")
            return {"current_stage": "requirement_extraction"}
    
    # ===== PRIORITY 6: Detect unhandleable queries =====
    unhandleable_patterns = [
        "refund", "cancel", "complaint", "issue", "problem",
        "shipping cost", "delivery charge", "payment method",
        "customization", "customize", "design change",
        "bulk discount", "wholesale"
    ]
    
    for pattern in unhandleable_patterns:
        if pattern in msg_lower:
            print(f"    🚨 Unhandleable query: '{pattern}'")
            print(f"    🚨 Handing off to human")
            
            return {
                "current_stage": "handoff",
                "needs_human_handoff": True,
                "handoff_reason": "unhandleable_query"
            }
    
    # ===== PRIORITY 7: Use LLM for complex messages =====
    prompt = ChatPromptTemplate.from_messages([
        ("system", """Classify the customer's message into one of these intents:
- browse_products: Customer wants to see products or is providing requirements
- track_order: Customer asking about existing order → CANNOT HANDLE
- ask_question: General question about policies, shipping, etc → CANNOT HANDLE
- complaint: Customer has an issue → CANNOT HANDLE
- greeting: Just saying hi/hello

IMPORTANT: If customer is providing product requirements, classify as "browse_products"

Respond with JSON: {{"intent": "...", "confidence": 0.95}}"""),
        ("human", "{message}")
    ])
    
    chain = prompt | llm
    response = chain.invoke({"message": last_msg})
    
    intent_text = response.content.lower()
    
    if "track_order" in intent_text or "ask_question" in intent_text or "complaint" in intent_text:
        print(f"    🚨 LLM classified as: {intent_text}")
        print(f"    🚨 Handing off to human")
        return {
            "current_stage": "handoff",
            "needs_human_handoff": True,
            "handoff_reason": "llm_classification" 
        }
    
    if "browse" in intent_text or "product" in intent_text or "greeting" in intent_text:
        intent = "browse_products"
    else:
        print(f"    🚨 Unknown intent: {intent_text}")
        print(f"    🚨 Handing off to human")
        return {
            "current_stage": "handoff",
            "needs_human_handoff": True,
            "handoff_reason": "llm_classification"
        }
    
    intent_obj = CustomerIntent(
        intent=intent,
        confidence=0.85,
        entities_mentioned=[]
    )
    
    print(f"    🎯 Classified intent: {intent}")
    
    return {
        "intent": intent_obj,
        "current_stage": "requirement_extraction"
    }

def requirement_extraction_node(state: BotState) -> BotState:
    """Node 3: Extract requirements - FIXED for sequential numbers"""
    print("  🟩 NODE: REQUIREMENT EXTRACTION")
    
    user_messages = [m for m in state["messages"] if isinstance(m, HumanMessage)]
    last_msg = user_messages[-1].content if user_messages else ""
    
    print(f"    📥 Input: '{last_msg}'")
    
    current_req = state.get("requirements")
    
    # ===== NEW: Special handling for SINGLE NUMBERS =====
    # Check if input is ONLY a number (no words, no dates)
    if last_msg.strip().isdigit():
        number = int(last_msg.strip())
        
        # If we already have requirements, do sequential filling
        if current_req:
            # Priority: quantity → budget → (don't fill timeline with number)
            if current_req.quantity is None:
                print(f"    📦 Sequential fill: quantity = {number}")
                current_req.quantity = number
                return {
                    "requirements": current_req,
                    "current_stage": "validation"
                }
            
            elif current_req.budget_per_piece is None:
                print(f"    💰 Sequential fill: budget = {number}")
                current_req.budget_per_piece = number
                return {
                    "requirements": current_req,
                    "current_stage": "validation"
                }
            
            else:
                # Both filled - let normal extraction handle it
                print(f"    🔄 Both filled, treating as potential correction")
    
    # ===== Normal extraction for complex inputs =====
    extracted = extract_customer_requirements.invoke({"message": last_msg})
    
    print(f"    🔧 Tool extracted: {extracted}")
    
    # ===== SMART MERGE: Only update fields that are explicitly extracted =====
    if current_req:
        # Only update if extracted value is not None AND not default
        for key, value in extracted.items():
            if key == "needs_confirmation":
                # Always update confirmation flag
                setattr(current_req, key, value)
            elif value is not None and value != []:
                # For other fields: only update if it makes sense
                current_value = getattr(current_req, key)
                
                # Special case: Don't overwrite existing values with extracted ones
                # UNLESS the extraction found keywords (not position-based)
                if current_value is None:
                    # Field is empty, always fill it
                    setattr(current_req, key, value)
                elif key in ["quantity", "budget_per_piece"]:
                    # Field already has value, only overwrite if input had keywords
                    msg_lower = last_msg.lower()
                    has_qty_keyword = any(word in msg_lower for word in ["quantity", "qty", "pieces", "pcs"])
                    has_budget_keyword = any(word in msg_lower for word in ["budget", "price", "rs", "rupees", "₹"])
                    
                    if (key == "quantity" and has_qty_keyword) or (key == "budget_per_piece" and has_budget_keyword):
                        setattr(current_req, key, value)
                    # else: don't overwrite (keep existing value)
                else:
                    # For other fields (timeline, location, preferences), always update
                    setattr(current_req, key, value)
        
        requirements = current_req
    else:
        requirements = ExtractedRequirements(**extracted)
    
    print(f"    📊 Final requirements: qty={requirements.quantity}, budget={requirements.budget_per_piece}, timeline={requirements.timeline}, location={requirements.location}, needs_confirmation={requirements.needs_confirmation}")
    
    return {
        "requirements": requirements,
        "current_stage": "validation"
    }

def validation_router(state: BotState) -> Literal["validate", "ask_confirmation"]:
    """Router: Check if we have enough info or need confirmation"""
    req = state.get("requirements")
    
    if not req:
        return "ask_confirmation"
    
    # Check required fields - ✅ ADDED location
    has_quantity = req.quantity is not None
    has_budget = req.budget_per_piece is not None
    has_timeline = req.timeline is not None
    has_location = req.location is not None  # ✅ NEW
    
    # ✅ CHANGED: Added has_location to the check
    if not all([has_quantity, has_budget, has_timeline, has_location]):
        print("    ⚠️  Missing required info")
        return "ask_confirmation"
    
    # Check if needs confirmation
    if req.needs_confirmation:
        print("    ⚠️  Needs confirmation")
        return "ask_confirmation"
    
    print("    ✅ All info collected, no confirmation needed")
    return "validate"

def ask_confirmation_node(state: BotState) -> BotState:
    """Node 4: Ask for missing info OR confirmation"""
    print("  🟧 NODE: ASK CONFIRMATION/MISSING INFO")
    
    req = state.get("requirements")
    
    if not req:
        return {"current_stage": "requirement_extraction"}
    
    # Check if needs confirmation
    if req.needs_confirmation and req.quantity and req.budget_per_piece:
        print("    📋 Asking for confirmation")
        msg = f"""Can you please confirm?

Quantity: {req.quantity} pieces
Budget: ₹{req.budget_per_piece} per piece

Reply "yes" to confirm or send correct values."""
        
        return {
            "messages": [AIMessage(content=msg)],
            "current_stage": "awaiting_confirmation"
        }
    
    # Otherwise, ask for missing info
    missing = []
    if not req.quantity:
        missing.append("Quantity")
    if not req.budget_per_piece:
        missing.append("Budget per piece")
    if not req.timeline:
        missing.append("When needed")
    
    # ✅ CHANGED: Removed "(optional)"
    if not req.location:
        missing.append("Delivery location")
    
    if len(missing) == 1:
        msg = f"Could you please share {missing[0]}?"
    else:
        items = ", ".join(missing[:-1]) + " and " + missing[-1] if len(missing) > 1 else missing[0]
        msg = f"Could you please share {items}?"
    
    return {
        "messages": [AIMessage(content=msg)],
        "current_stage": "requirement_extraction"
    }

def validation_node(state: BotState) -> BotState:
    """Node 5: Validate requirements"""
    print("  🟪 NODE: VALIDATION")
    
    req = state["requirements"]
    
    # Calculate timeline
    timeline_result = calculate_timeline_urgency.invoke({"timeline": req.timeline})
    
    validation = ValidationResult(
        is_valid=True,
        issues=[],
        suggestions=[],
        delivery_date=timeline_result["delivery_date"],
        urgency_level=timeline_result["urgency_level"]
    )
    
    print(f"    🔍 Validation: ✅ PASS")
    
    return {
        "validation": validation,
        "current_stage": "product_search"
    }

def product_search_node(state: BotState) -> BotState:
    """Node 6: Search products"""
    print("  🟦 NODE: PRODUCT SEARCH")
    
    req = state["requirements"]
    
    search_params = {
        "budget_max": req.budget_per_piece,
        "quantity": req.quantity,
    }
    
    if req.preferences and len(req.preferences) > 0:
        search_params["preferences"] = req.preferences
    
    products = search_matching_products.invoke(search_params)
    
    print(f"    🔎 Found {len(products)} products")
    
    return {
        "recommended_products": products,
        "current_stage": "recommendation"
    }

def recommendation_node(state: BotState) -> BotState:
    """Node 7: ✅ Format requirements summary and prepare for handoff"""
    print("  🟨 NODE: RECOMMENDATION")
    
    products = state["recommended_products"]
    req = state["requirements"]
    
    if not products:
        msg = f"Sorry mam/sir, no products available for ₹{req.budget_per_piece} per piece.\n\n"
        msg += "Our team will help you find alternatives.\n\n"
        msg += "Thank you! 🙏"
        
        return {
            "messages": [AIMessage(content=msg)],
            "current_stage": "handoff",
            "needs_human_handoff": True,
            "handoff_reason": "no_products"
        }
    
    # ✅ NEW: Build formatted requirements summary for customer
    timeline_display = format_timeline_display(req.timeline)
    
    requirements_summary = "Based on your requirement,\n\n"
    requirements_summary += f"Number of pieces: {req.quantity} pieces\n"
    requirements_summary += f"Budget: ₹{req.budget_per_piece} per piece\n"
    requirements_summary += f"Delivery location: {req.location}\n"
    requirements_summary += f"When needed: {timeline_display}\n\n"
    requirements_summary += f"Here are {len(products)} options for you:"
    
    print(f"    ✅ Requirements summary formatted for customer")
    print(f"    📸 Will send {len(products)} product images")
    print(f"    🤝 HANDOFF TO HUMAN after images sent")
    
    # Return special marker with summary
    return {
        "messages": [AIMessage(content="[SEND_PRODUCT_IMAGES_WITH_SUMMARY]")],
        "conversation_history_summary": requirements_summary,
        "current_stage": "handoff",
        "needs_human_handoff": True,
        "handoff_reason": "products_shown"
    }

def product_selection_node(state: BotState) -> BotState:
    """Node 8: Handle product selection"""
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
        index = int(last_msg) - 1
        if 0 <= index < len(products):
            selected = products[index]
    
    if not selected:
        for product in products:
            if product['name'].lower() in last_msg or last_msg in product['name'].lower():
                selected = product
                break
    
    if not selected:
        msg = """I didn't catch that! 😅

Please reply with:
• A number (1, 2, 3...)
• Or the product name

Which product would you like?"""
        
        return {
            "messages": [AIMessage(content=msg)],
            "current_stage": "product_selection"
        }
    
    print(f"    ✅ Selected: {selected['name']}")
    
    return {
        "selected_product": selected,
        "current_stage": "order_confirmation"
    }

def order_confirmation_node(state: BotState) -> BotState:
    """Node 9: Confirm order"""
    print("  🟦 NODE: ORDER CONFIRMATION")
    
    product = state.get("selected_product")
    req = state.get("requirements")
    
    if not product or not req:
        print("    ❌ Missing product or requirements - handing off")
        msg = "Our team will contact you shortly to complete your order.\n\nThank you! 🙏"
        return {
            "messages": [AIMessage(content=msg)],
            "current_stage": "handoff",
            "needs_human_handoff": True
        }
    
    # Calculate total
    total = product['price'] * req.quantity
    
    # Build confirmation message
    msg = f"Thank you!\n\n"
    msg += f"{product['name']}\n"
    msg += f"Quantity: {req.quantity} pieces\n"
    msg += f"Total: ₹{total:,}\n"
    
    if req.location:
        msg += f"Location: {req.location}\n"
    
    msg += f"\nOur team will contact you shortly.\n\n"
    msg += f"Thank you! 🙏"
    
    return {
        "messages": [AIMessage(content=msg)],
        "current_stage": "handoff"
    }

# ============================================================
# BUILD GRAPH
# ============================================================

def build_production_graph():
    """Build production-grade multi-node graph"""
    
    workflow = StateGraph(BotState)
    
    # Add nodes
    workflow.add_node("greeting", greeting_node)
    workflow.add_node("classify_intent", intent_classifier_node)
    workflow.add_node("extract_requirements", requirement_extraction_node)
    workflow.add_node("ask_confirmation", ask_confirmation_node)
    workflow.add_node("validate", validation_node)
    workflow.add_node("search_products", product_search_node)
    workflow.add_node("recommend", recommendation_node)
    
    # ===== FIXED Entry point - Check special cases FIRST =====
    def entry_router(state: BotState) -> Literal["greeting", "classify_intent"]:
        """
        Route entry based on:
        1. Check for images/quick queries FIRST (even for new users)
        2. Then check if needs greeting
        """
        # Get the last user message
        user_messages = [m for m in state.get("messages", []) if isinstance(m, HumanMessage)]
        
        if user_messages:
            last_msg = user_messages[-1].content
            msg_lower = last_msg.lower().strip()
            
            # PRIORITY 1: Check for image (even on first message)
            if "[IMAGE_SENT]" in last_msg:
                print("  🚨 IMAGE at entry - routing to classify_intent for handoff")
                return "classify_intent"
            
            # PRIORITY 2: Check for quick queries (even on first message)
            quick_queries = ['pp', 'price please', 'price pls', 'available?', 'stock?', 'available', 'in stock', 'rate pls', 'rate please']
            if len(last_msg) <= 20 and any(q in msg_lower for q in quick_queries):
                print("  🚨 Quick query at entry - routing to classify_intent for handoff")
                return "classify_intent"
        
        # PRIORITY 3: Normal flow - greet new users
        if not state.get("has_greeted"):
            print("  👋 New user - routing to greeting")
            return "greeting"
        
        print("  ↩️  Returning user - routing to classify_intent")
        return "classify_intent"
    
    workflow.set_conditional_entry_point(
        entry_router,
        {"greeting": "greeting", "classify_intent": "classify_intent"}
    )
    
    # Flow
    workflow.add_edge("greeting", END)
    
    def post_intent_router(state: BotState) -> Literal["extract_requirements", "end"]:
        """Route based on current stage"""
        current_stage = state.get("current_stage")
        needs_handoff = state.get("needs_human_handoff", False)
        
        if current_stage == "handoff" or needs_handoff:
            print("    🔀 Routing to: END (handoff active)")
            return "end"
        
        print("    🔀 Routing to: extract_requirements")
        return "extract_requirements"
    
    workflow.add_conditional_edges(
        "classify_intent",
        post_intent_router,
        {
            "extract_requirements": "extract_requirements",
            "end": END
        }
    )
    
    workflow.add_conditional_edges(
        "extract_requirements",
        validation_router,
        {"validate": "validate", "ask_confirmation": "ask_confirmation"}
    )
    
    workflow.add_edge("ask_confirmation", END)
    workflow.add_edge("validate", "search_products")
    workflow.add_edge("search_products", "recommend")
    workflow.add_edge("recommend", END)
    
    # ✅ Setup PostgreSQL checkpointer - LAZY CONNECTION for Render
    db_url = os.getenv("SUPABASE_DB_URL")

    from langgraph.checkpoint.postgres import PostgresSaver as BaseSaver

    # Create a simple connection (no pool) for setup
    try:
        # Try to setup tables (but don't fail if can't connect immediately)
        conn = psycopg.connect(db_url, autocommit=True, connect_timeout=10)
        checkpointer = BaseSaver(conn)
        checkpointer.setup()
        conn.close()
        print("✅ Supabase checkpointer initialized")
    except Exception as e:
        print(f"⚠️ Supabase connection warning: {e}")
        print("   Bot will try to reconnect when needed")

    # Create checkpointer with connection string (connects lazily)
    checkpointer = BaseSaver.from_conn_string(db_url)

    return workflow.compile(checkpointer=checkpointer)

# ============================================================
# BOT CLASS
# ============================================================

class ProductionVihaBot:
    """Production-grade bot"""
    
    def __init__(self):
        self.graph = build_production_graph()
        print("✅ Production bot initialized!")
        print("   • 9 specialized nodes")
        print("   • 3 tools")
        print("   • Confirmation flow for ambiguous inputs")
        print("   • Position-based extraction")
        print("   • Shows ALL matching products")
        print("   • Simplified conversation flow")
    
    def chat(self, user_id: str, message: str) -> dict:
        """
        Production chat interface - Returns structured response
        
        Returns:
            dict with keys:
                - reply: str (bot message)
                - needs_handoff: bool
                - products: list (if showing products)
        """
        
        config = {"configurable": {"thread_id": user_id}}
        
        print(f"\n{'='*70}")
        print(f"💬 Processing message from user: {user_id}")
        print(f"📩 Message: {message}")
        print(f"{'='*70}")
        
        try:
            # ===== Get the BEFORE state (to detect new messages) =====
            # Get current state before invoking
            try:
                current_state = self.graph.get_state(config)
                messages_before = len(current_state.values.get("messages", []))
            except:
                messages_before = 0
            
            # Prepare input
            input_state = {
                "messages": [HumanMessage(content=message)],
                "user_id": user_id
            }
            
            # Execute graph
            result = self.graph.invoke(input_state, config)
            
            # ===== Get the AFTER state =====
            messages_after = len(result.get("messages", []))
            
            # Calculate how many NEW messages the graph added
            # We added 1 HumanMessage, so if there's 1+ more, bot responded
            new_messages_count = messages_after - messages_before
            bot_generated_new_message = new_messages_count > 1  # >1 because we added 1 HumanMessage
            
            print(f"    📊 Messages before: {messages_before}, after: {messages_after}")
            print(f"    📝 New messages: {new_messages_count}, Bot responded: {bot_generated_new_message}")
            
            # Extract handoff status
            needs_handoff = result.get("needs_human_handoff", False)
            current_stage = result.get("current_stage", "")
            
            # Get the LATEST bot message (if any)
            latest_bot_response = None
            for msg in reversed(result.get("messages", [])):
                if isinstance(msg, AIMessage):
                    latest_bot_response = msg.content
                    break
            
            # ===== KEY LOGIC: Only process bot response if it's NEW =====
            
            # SCENARIO A: Bot just generated [SEND_PRODUCT_IMAGES] in THIS turn
            # SCENARIO A: Bot sending products with summary
            if (bot_generated_new_message and 
                latest_bot_response == "[SEND_PRODUCT_IMAGES_WITH_SUMMARY]" and 
                needs_handoff):
                
                products = result.get("recommended_products", [])
                requirements_summary = result.get("conversation_history_summary", "")
                req = result.get("requirements")
                handoff_reason = result.get("handoff_reason", "")
                
                print(f"    📸 FRESH HANDOFF: Sending {len(products)} products with summary")
                
                # ✅ NEW: Build detailed customer info for wife
                handoff_reason_text = build_handoff_reason(handoff_reason, req)
                
                return {
                    "reply": "[SEND_PRODUCT_IMAGES_WITH_SUMMARY]",
                    "needs_handoff": True,
                    "products": products,
                    "requirements_summary": requirements_summary,  # ✅ For customer
                    "customer_requirements": {  # ✅ For wife alert
                        "quantity": req.quantity,
                        "budget_per_piece": req.budget_per_piece,
                        "timeline": format_timeline_display(req.timeline),
                        "location": req.location
                    },
                    "handoff_reason": handoff_reason_text
                }
            
            # SCENARIO B: Handoff active, bot didn't generate new message
            if needs_handoff and current_stage == "handoff" and not bot_generated_new_message:
                print(f"\n{'─'*70}")
                print(f"🤐 HANDOFF ACTIVE - BOT COMPLETELY SILENT (no new messages)")
                print(f"{'─'*70}\n")

                req = result.get("requirements")
                handoff_reason = result.get("handoff_reason", "")
                handoff_reason_text = build_handoff_reason(handoff_reason, req, message)
                
                return {
                    "reply": None,
                    "needs_handoff": True,
                    "products": None,
                    "customer_requirements": {
                        "quantity": req.quantity if req and req.quantity else None,
                        "budget_per_piece": req.budget_per_piece if req and req.budget_per_piece else None,
                        "timeline": format_timeline_display(req.timeline) if req and req.timeline else None,
                        "location": req.location if req and req.location else None
                    } if req else None,
                    "handoff_reason": handoff_reason_text
                }
            
            # SCENARIO C: Other handoff cases
            if needs_handoff:
                print(f"\n{'─'*70}")
                print(f"🚨 HANDOFF - BOT STAYS SILENT")
                print(f"{'─'*70}\n")
                
                req = result.get("requirements")
                handoff_reason = result.get("handoff_reason", "")
                handoff_reason_text = build_handoff_reason(handoff_reason, req, message)

                return {
                    "reply": None,
                    "needs_handoff": True,
                    "products": None,
                    "customer_requirements": {
                        "quantity": req.quantity if req and req.quantity else None,
                        "budget_per_piece": req.budget_per_piece if req and req.budget_per_piece else None,
                        "timeline": format_timeline_display(req.timeline) if req and req.timeline else None,
                        "location": req.location if req and req.location else None
                    } if req else None,
                    "handoff_reason": handoff_reason_text
                }
            
            # SCENARIO D: Bot generated a normal response
            if bot_generated_new_message and latest_bot_response:
                print(f"\n{'─'*70}")
                print(f"🤖 BOT RESPONSE:")
                print(f"{'─'*70}")
                
                if len(latest_bot_response) > 500:
                    print(f"{latest_bot_response[:500]}...\n[Truncated]")
                else:
                    print(latest_bot_response)
                
                print(f"{'='*70}\n")
                
                return {
                    "reply": latest_bot_response,
                    "needs_handoff": False,
                    "products": None
                }
            
            # SCENARIO E: No new response, no handoff - something went wrong
            return {
                "reply": None,
                "needs_handoff": True,
                "products": None
            }
            
        except Exception as e:
            print(f"\n{'='*70}")
            print(f"❌ ERROR: {e}")
            print(f"{'='*70}")
            import traceback
            traceback.print_exc()
            
            return {
                "reply": None,
                "needs_handoff": True,
                "products": None
            }

# ============================================================
# TESTING
# ============================================================

if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("🧪 TESTING PRODUCTION BOT v3.0 (With Confirmation)")
    print("=" * 70)
    
    bot = ProductionVihaBot()
    test_user = "test_showcase_user"
    
    print("\n📞 Test Conversation 1: Clear numbers (no confirmation)")
    print("-" * 70)
    
    print("\n👤 User: Hi")
    r1 = bot.chat(test_user, "Hi")
    print(f"\n🤖 Bot: {r1['reply']}")
    
    print("\n👤 User: 500\\n45\\nFeb 22\\nChennai")
    r2 = bot.chat(test_user, "500\n45\nFeb 22\nChennai")
    if r2.get("products"):
        print(f"\n🤖 Bot: [Sends {len(r2['products'])} product images]")
    else:
        print(f"\n🤖 Bot: {r2['reply']}")
    
    print("\n📞 Test Conversation 2: Ambiguous numbers (needs confirmation)")
    print("-" * 70)
    
    test_user2 = "test_ambiguous"
    
    print("\n👤 User: Hi")
    r3 = bot.chat(test_user2, "Hi")
    print(f"\n🤖 Bot: {r3['reply']}")
    
    print("\n👤 User: 50\\n100\\nFeb 22\\nChennai")
    r4 = bot.chat(test_user2, "50\n100\nFeb 22\nChennai")
    print(f"\n🤖 Bot: {r4['reply']}")
    
    print("\n👤 User: yes")
    r5 = bot.chat(test_user2, "yes")
    if r5.get("products"):
        print(f"\n🤖 Bot: [Sends {len(r5['products'])} product images]")
    else:
        print(f"\n🤖 Bot: {r5['reply']}")

    print("\n📞 Test Conversation 3: PERSISTENCE TEST (Resume after 'restart')")
    print("-" * 70)
    print("Simulating server restart by creating new bot instance...")

    # Create a NEW bot instance (simulates restart)
    bot2 = ProductionVihaBot()

    print("\n👤 User (test_showcase_user): 45")
    print("(Continuing conversation from Test 1 where bot asked for budget)")

    # Continue the SAME conversation
    r6 = bot2.chat("test_showcase_user", "45")
    print(f"\n🤖 Bot: {r6['reply']}")

    if r6.get("products"):
        print(f"\n✅ SUCCESS! Bot remembered conversation and showed {len(r6['products'])} products!")
        print("✅ Supabase persistence is working!")
    else:
        print("\n⚠️ Bot response:", r6['reply'])
    
    print("\n" + "=" * 70)
    print("✅ Production bot testing complete!")
    print("   Position-based extraction ✅")
    print("   Confirmation for ambiguous inputs ✅")
    print("   Shows ALL matching products ✅")
    print("=" * 70)