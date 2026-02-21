"""
Pydantic models for all API endpoints
"""

from pydantic import BaseModel


# ============================================================
# CHAT
# ============================================================

class ChatRequest(BaseModel):
    user_id: str
    message: str
    push_name: str = "" # WhatsApp display name


# ============================================================
# CONVERSATIONS
# ============================================================

class LockRequest(BaseModel):
    user_id: str


# ============================================================
# LEADS
# ============================================================

class LeadsRequest(BaseModel):
    days: int = 7  # Default: last 7 days


# ============================================================
# ANALYTICS
# ============================================================

class SummaryRequest(BaseModel):
    start_date: str | None = None  # "2026-02-19"
    end_date: str | None = None    # "2026-02-19"


class PendingRequest(BaseModel):
    start_date: str | None = None
    end_date: str | None = None


class FollowupRequest(BaseModel):
    start_date: str | None = None
    end_date: str | None = None
    silent_days: int = 1  # Default: silent for 1+ day


class HotleadsRequest(BaseModel):
    start_date: str | None = None
    end_date: str | None = None
    min_quantity: int = 100  # Default: 100+ pieces


class LockedRequest(BaseModel):
    start_date: str | None = None
    end_date: str | None = None


class UpcomingEventsRequest(BaseModel):
    days_ahead: int = 10