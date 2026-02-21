"""
LangGraph graph builder for the Viha bot.
Assembles all nodes, edges, and the PostgreSQL checkpointer.
"""

import os
from typing import Literal

import psycopg
from psycopg_pool import ConnectionPool
from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres import PostgresSaver

from models.bot_models import BotState
from bot.nodes import (
    greeting_node,
    intent_classifier_node,
    requirement_extraction_node,
    ask_confirmation_node,
    validation_node,
    validation_router,
    product_search_node,
    recommendation_node,
)


def build_production_graph():
    """Assemble the full LangGraph workflow with PostgreSQL persistence."""

    workflow = StateGraph(BotState)

    # ── Register nodes ────────────────────────────────────────────────────
    workflow.add_node("greeting",             greeting_node)
    workflow.add_node("classify_intent",      intent_classifier_node)
    workflow.add_node("extract_requirements", requirement_extraction_node)
    workflow.add_node("ask_confirmation",     ask_confirmation_node)
    workflow.add_node("validate",             validation_node)
    workflow.add_node("search_products",      product_search_node)
    workflow.add_node("recommend",            recommendation_node)

    # ── Entry point ───────────────────────────────────────────────────────
    def entry_router(state: BotState) -> Literal["greeting", "classify_intent"]:
        """
        Priority order:
        1. Images / quick price queries → classify_intent (for immediate handoff)
        2. New user with no greeting → greeting
        3. Returning user → classify_intent
        """
        user_messages = [m for m in state.get("messages", []) if isinstance(m, HumanMessage)]
        if user_messages:
            last_msg  = user_messages[-1].content
            msg_lower = last_msg.lower().strip()

            if "[IMAGE_SENT]" in last_msg:
                print("  🚨 IMAGE at entry → classify_intent")
                return "classify_intent"

            quick_queries = ['pp', 'price please', 'price pls', 'available?',
                             'stock?', 'available', 'in stock', 'rate pls', 'rate please']
            if len(last_msg) <= 20 and any(q in msg_lower for q in quick_queries):
                print("  🚨 Quick query at entry → classify_intent")
                return "classify_intent"

        if not state.get("has_greeted"):
            print("  👋 New user → greeting")
            return "greeting"

        print("  ↩️  Returning user → classify_intent")
        return "classify_intent"

    workflow.set_conditional_entry_point(
        entry_router,
        {"greeting": "greeting", "classify_intent": "classify_intent"},
    )

    # ── Edges ─────────────────────────────────────────────────────────────
    workflow.add_edge("greeting", END)

    def post_intent_router(state: BotState) -> Literal["extract_requirements", "end"]:
        if state.get("current_stage") == "handoff" or state.get("needs_human_handoff"):
            print("    🔀 → END (handoff)")
            return "end"
        print("    🔀 → extract_requirements")
        return "extract_requirements"

    workflow.add_conditional_edges(
        "classify_intent",
        post_intent_router,
        {"extract_requirements": "extract_requirements", "end": END},
    )

    workflow.add_conditional_edges(
        "extract_requirements",
        validation_router,
        {"validate": "validate", "ask_confirmation": "ask_confirmation"},
    )

    workflow.add_edge("ask_confirmation", END)
    workflow.add_edge("validate",         "search_products")
    workflow.add_edge("search_products",  "recommend")
    workflow.add_edge("recommend",        END)

    # ── PostgreSQL checkpointer ───────────────────────────────────────────
    db_url = os.getenv("SUPABASE_DB_URL")
    if not db_url:
        raise ValueError("❌ SUPABASE_DB_URL is required but not set")

    print("🔄 Connecting to Supabase PostgreSQL...")
    try:
        pool = ConnectionPool(
            conninfo=db_url,
            min_size=1,
            max_size=3,
            timeout=10,
            kwargs={"autocommit": True},
        )

        # One-time table setup
        with pool.connection() as conn:
            PostgresSaver(conn).setup()
            with conn.cursor() as cur:
                cur.execute("SELECT 1")

        print("✅ Supabase connected — conversations will persist across restarts")

    except Exception as e:
        print(f"❌ CRITICAL: Database connection failed — {str(e)[:200]}")
        raise

    checkpointer = PostgresSaver(pool)
    return workflow.compile(checkpointer=checkpointer)