"""
Chat endpoint
POST /chat — main bot interaction endpoint
"""

from fastapi import APIRouter
from models.schemas import ChatRequest
from services.lock_service import (
    locked_conversations_cache,
    is_conversation_locked
)
from services.lead_service import save_or_update_lead

router = APIRouter()

# Bot instance is passed in from main.py to keep it singleton
# Accessed via router.bot (set in main.py after include_router)
_bot = None


def set_bot(bot_instance):
    """Called from main.py to inject the singleton bot instance"""
    global _bot
    _bot = bot_instance


@router.post("/chat")
async def chat(request: ChatRequest):
    """
    Chat endpoint:
    1. Check if conversation is locked → silent if yes
    2. Process message through LangGraph bot
    3. Save lead if requirements exist
    4. Return response
    """
    try:
        # ── PRIORITY CHECK: Is conversation locked? ──────────────────
        lock_info = locked_conversations_cache.get(request.user_id)
        if not lock_info:
            # Fallback: check Supabase (catches post-restart state)
            lock_info = is_conversation_locked(request.user_id)
            if lock_info:
                # Restore to cache
                locked_conversations_cache[request.user_id] = lock_info

        if lock_info:
            print(f"\n{'='*70}")
            print(f"🔒 LOCKED - BOT SILENT for {request.user_id}")
            print(f"{'='*70}\n")

            return {
                "status":        "locked",
                "reply":         None,
                "needs_handoff": False,
                "products":      None,
                "locked":        True,
                "locked_at":     lock_info["locked_at"],
                "locked_by":     lock_info["locked_by"]
            }

        # ── Normal chat flow ─────────────────────────────────────────
        print(f"\n{'='*70}")
        print(f"💬 API Request from: {request.user_id}")
        print(f"📩 Message: {request.message}")
        print(f"{'='*70}")

        response = _bot.chat(request.user_id, request.message)

        # ── Save lead if requirements exist ──────────────────────────
        has_requirements = (
            response.get("customer_requirements") and
            any(v for v in response["customer_requirements"].values() if v is not None)
        )

        if has_requirements:
            if response.get("reply") == "[SEND_PRODUCT_IMAGES_WITH_SUMMARY]":
                lead_status = "products_shown"
            elif response.get("needs_handoff"):
                lead_status = "follow_up"
            else:
                lead_status = "requirements_collecting"

            response["last_message"] = request.message
            save_or_update_lead(request.user_id, response, lead_status, request.push_name)

        return {
            "status":               "success",
            "reply":                response["reply"],
            "needs_handoff":        response["needs_handoff"],
            "products":             response.get("products"),
            "requirements_summary": response.get("requirements_summary"),
            "customer_requirements":response.get("customer_requirements"),
            "handoff_reason":       response.get("handoff_reason"),
            "locked":               False,
            "customer_number":      request.user_id,
            "last_message":         request.message
        }

    except Exception as e:
        print(f"❌ ERROR in chat endpoint: {e}")
        import traceback
        traceback.print_exc()

        return {
            "status":          "error",
            "reply":           None,
            "needs_handoff":   True,
            "products":        None,
            "locked":          False,
            "customer_number": request.user_id,
            "last_message":    request.message
        }