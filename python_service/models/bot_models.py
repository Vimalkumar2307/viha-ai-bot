"""
Pydantic models and LangGraph state for the Viha bot.
"""

import operator
from typing import Annotated, TypedDict, Sequence, Literal

from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel, Field


# ============================================================
# STRUCTURED OUTPUTS
# ============================================================

class CustomerIntent(BaseModel):
    """Structured intent classification"""
    intent: Literal["browse_products", "track_order", "ask_question", "complaint", "greeting"]
    confidence: float = Field(ge=0.0, le=1.0)
    entities_mentioned: list[str] = Field(default_factory=list)


class ExtractedRequirements(BaseModel):
    """Structured extraction of customer requirements"""
    quantity:         int | None = Field(None, description="Number of pieces needed")
    budget_min:       int | None = Field(None, description="Minimum budget in rupees")
    budget_max:       int | None = Field(None, description="Maximum budget in rupees")
    budget_display:   str | None = Field(None, description="Budget as customer said it")
    timeline:         str | None = Field(None, description="When needed")
    location:         str | None = Field(None, description="Delivery city")
    preferences:      list[str]  = Field(default_factory=list)
    needs_confirmation: bool     = Field(False, description="Whether to confirm extracted values")


class ValidationResult(BaseModel):
    """Simplified validation output"""
    is_valid:       bool
    issues:         list[str] = Field(default_factory=list)
    suggestions:    list[str] = Field(default_factory=list)
    delivery_date:  str | None = None
    urgency_level:  Literal["low", "medium", "high", "critical"] = "medium"


# ============================================================
# LANGGRAPH STATE
# ============================================================

class BotState(TypedDict):
    """Complete conversation state — passed between all graph nodes"""
    messages:                    Annotated[Sequence[HumanMessage | AIMessage], operator.add]
    user_id:                     str

    requirements:                ExtractedRequirements | None
    validation:                  ValidationResult | None
    recommended_products:        list | None
    selected_product:            dict | None

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

    intent:                      CustomerIntent | None
    conversation_history_summary: str | None
    handoff_reason:              str | None

    has_greeted:                 bool
    needs_human_handoff:         bool
    error_count:                 int