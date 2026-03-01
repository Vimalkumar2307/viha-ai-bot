"""
ProductionVihaBot — the public interface for the Viha WhatsApp AI bot.
Wraps the LangGraph workflow and returns structured responses to api/chat.py.
"""

from langchain_core.messages import AIMessage, HumanMessage

from bot.graph import build_production_graph
from bot.tools import format_timeline_display, build_handoff_reason


class ProductionVihaBot:
    """Production-grade bot — 9 nodes, 3 tools, Supabase persistence."""

    def __init__(self):
        self.graph = build_production_graph()
        print("✅ ProductionVihaBot ready!")
        print("   • 9 specialised nodes")
        print("   • 3 tools (extract / timeline / search)")
        print("   • Confirmation flow for ambiguous inputs")
        print("   • Supabase persistence across restarts")

    # ──────────────────────────────────────────────────────────────────────
    def chat(self, user_id: str, message: str) -> dict:
        """
        Process one customer message and return a structured response.

        Returns a dict with keys:
            reply               str | None
            needs_handoff       bool
            products            list | None
            requirements_summary str | None   (for product images message)
            customer_requirements dict | None  (for wife alert)
            handoff_reason      str | None
        """
        
        config = {
            "configurable": {"thread_id": user_id},
            "metadata": {
                "customer_number": user_id,
                "session": user_id
            },
            "tags": [f"customer:{user_id}"]
        }

        print(f"\n{'='*70}")
        print(f"💬 user={user_id}  msg={message[:80]}")
        print(f"{'='*70}")

        try:
            # Count messages before invocation so we can tell if bot replied
            try:
                before = len(self.graph.get_state(config).values.get("messages", []))
            except Exception:
                before = 0

            result = self.graph.invoke(
                {"messages": [HumanMessage(content=message)], "user_id": user_id},
                config,
            )

            after          = len(result.get("messages", []))
            new_count      = after - before
            bot_replied    = new_count > 1          # we added 1 HumanMessage
            needs_handoff  = result.get("needs_human_handoff", False)
            current_stage  = result.get("current_stage", "")

            print(f"    📊 messages: {before} → {after}  bot_replied={bot_replied}")

            # Latest AI message (if any)
            latest_reply = next(
                (m.content for m in reversed(result.get("messages", [])) if isinstance(m, AIMessage)),
                None,
            )

            req = result.get("requirements")

            # ── SCENARIO A: Products + summary to send ────────────────────
            if (bot_replied and
                    latest_reply == "[SEND_PRODUCT_IMAGES_WITH_SUMMARY]" and
                    needs_handoff):
                products     = result.get("recommended_products", [])
                summary      = result.get("conversation_history_summary", "")
                handoff_text = build_handoff_reason(result.get("handoff_reason", ""), req)
                print(f"    📸 Sending {len(products)} products with summary")
                return {
                    "reply":                 "[SEND_PRODUCT_IMAGES_WITH_SUMMARY]",
                    "needs_handoff":         True,
                    "products":              products,
                    "requirements_summary":  summary,
                    "customer_requirements": _req_dict(req),
                    "handoff_reason":        handoff_text,
                }

            # ── SCENARIO B: Handoff, bot silent ──────────────────────────
            if needs_handoff and current_stage == "handoff" and not bot_replied:
                print("    🤐 Handoff active — bot silent")
                handoff_text = build_handoff_reason(result.get("handoff_reason", ""), req, message)
                return {
                    "reply":                 None,
                    "needs_handoff":         True,
                    "products":              None,
                    "customer_requirements": _req_dict(req),
                    "handoff_reason":        handoff_text,
                }

            # ── SCENARIO C: Other handoff ─────────────────────────────────
            if needs_handoff:
                print("    🚨 Handoff — bot silent")
                handoff_text = build_handoff_reason(result.get("handoff_reason", ""), req, message)
                return {
                    "reply":                 None,
                    "needs_handoff":         True,
                    "products":              None,
                    "customer_requirements": _req_dict(req),
                    "handoff_reason":        handoff_text,
                }

            # ── SCENARIO D: Normal reply ──────────────────────────────────
            if bot_replied and latest_reply:
                print(f"    🤖 Bot reply: {latest_reply[:80]}{'...' if len(latest_reply) > 80 else ''}")
                return {"reply": latest_reply, "needs_handoff": False, "products": None}

            # ── SCENARIO E: No reply, no handoff — failsafe ───────────────
            return {"reply": None, "needs_handoff": True, "products": None}

        except Exception as exc:
            print(f"❌ ERROR: {exc}")
            import traceback
            traceback.print_exc()
            return {"reply": None, "needs_handoff": True, "products": None}


# ── Private helpers ────────────────────────────────────────────────────────

def _req_dict(req) -> dict | None:
    """Serialise ExtractedRequirements to a plain dict for wife alerts."""
    if not req:
        return None
    return {
        "quantity":    req.quantity,
        "budget":      req.budget_display,
        "budget_range": (
            f"₹{req.budget_min}-{req.budget_max}"
            if req.budget_min is not None and req.budget_max is not None else None
        ),
        "timeline":    format_timeline_display(req.timeline) if req.timeline else None,
        "location":    req.location,
    }