"""
FastAPI wrapper for complete bot with conversation locking
Version: 4.0 - Added leads tracking, persistent locks, LEADS/INFO endpoints
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from complete_bot import ProductionVihaBot
from datetime import datetime, timedelta
import os
import psycopg

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# DATABASE HELPER
# ============================================================

def get_db_connection():
    """Get a database connection"""
    db_url = os.getenv("SUPABASE_DB_URL")
    return psycopg.connect(db_url)


# ============================================================
# LEADS HELPER
# ============================================================

def save_or_update_lead(customer_number: str, response: dict, status: str = None):
    """
    Insert lead if new, update if exists.
    Called after every bot interaction that has requirements.
    """
    try:
        req = response.get("customer_requirements")

        # Determine status from response if not provided
        if not status:
            if response.get("reply") == "[SEND_PRODUCT_IMAGES_WITH_SUMMARY]":
                status = "products_shown"
            elif response.get("needs_handoff"):
                status = "follow_up"
            else:
                status = "requirements_collecting"

        # Extract fields safely
        quantity    = req.get("quantity")   if req else None
        budget      = req.get("budget")     if req else None
        location    = req.get("location")   if req else None
        timeline    = req.get("timeline")   if req else None
        last_msg    = response.get("last_message", "")

        # Parse budget string to numeric (e.g. "₹50" → 50.0)
        budget_numeric = None
        if budget:
            import re
            numbers = re.findall(r'\d+\.?\d*', str(budget))
            if numbers:
                budget_numeric = float(numbers[0])

        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # Check if lead exists
                cursor.execute(
                    "SELECT id FROM leads WHERE customer_number = %s",
                    (customer_number,)
                )
                existing = cursor.fetchone()

                if existing:
                    # UPDATE existing lead
                    cursor.execute("""
                        UPDATE leads SET
                            quantity         = COALESCE(%s, quantity),
                            budget_per_piece = COALESCE(%s, budget_per_piece),
                            location         = COALESCE(%s, location),
                            timeline         = COALESCE(%s, timeline),
                            status           = %s,
                            last_message     = COALESCE(%s, last_message),
                            updated_at       = NOW()
                        WHERE customer_number = %s
                    """, (
                        quantity, budget_numeric, location, timeline,
                        status, last_msg, customer_number
                    ))
                    print(f"    📝 Lead updated: {customer_number} → {status}")
                else:
                    # INSERT new lead
                    cursor.execute("""
                        INSERT INTO leads
                            (customer_number, quantity, budget_per_piece,
                             location, timeline, status, last_message)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (
                        customer_number, quantity, budget_numeric,
                        location, timeline, status, last_msg
                    ))
                    print(f"    📝 Lead created: {customer_number} → {status}")

                conn.commit()

    except Exception as e:
        print(f"    ⚠️  Lead save failed (non-critical): {e}")


# ============================================================
# LOCKED CONVERSATIONS - Supabase persistent
# ============================================================

def is_conversation_locked(user_id: str) -> dict | None:
    """Check if conversation is locked in Supabase. Returns lock info or None."""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT status, updated_at
                    FROM leads
                    WHERE customer_number = %s AND status = 'locked'
                """, (user_id,))
                row = cursor.fetchone()
                if row:
                    return {
                        "locked_at": row[1].isoformat() if row[1] else None,
                        "locked_by": "wife",
                        "reason": "wife_interrupted"
                    }
                return None
    except Exception as e:
        print(f"⚠️  Lock check failed: {e}")
        # Fallback to in-memory
        return locked_conversations_cache.get(user_id)


def set_conversation_lock(user_id: str):
    """Lock conversation in Supabase + memory cache."""
    lock_info = {
        "locked_at": datetime.now().isoformat(),
        "locked_by": "wife",
        "reason": "wife_interrupted"
    }
    # Memory cache (fast lookup)
    locked_conversations_cache[user_id] = lock_info

    # Supabase (persistent)
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT id FROM leads WHERE customer_number = %s",
                    (user_id,)
                )
                if cursor.fetchone():
                    cursor.execute("""
                        UPDATE leads SET status = 'locked', updated_at = NOW()
                        WHERE customer_number = %s
                    """, (user_id,))
                else:
                    cursor.execute("""
                        INSERT INTO leads (customer_number, status)
                        VALUES (%s, 'locked')
                    """, (user_id,))
                conn.commit()
    except Exception as e:
        print(f"⚠️  Lock persist failed: {e}")


def remove_conversation_lock(user_id: str):
    """Unlock conversation in Supabase + memory cache."""
    locked_conversations_cache.pop(user_id, None)

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE leads SET status = 'follow_up', updated_at = NOW()
                    WHERE customer_number = %s
                """, (user_id,))
                conn.commit()
    except Exception as e:
        print(f"⚠️  Unlock persist failed: {e}")


# ============================================================
# STARTUP
# ============================================================

# In-memory cache (fast lookup, lost on restart — Supabase is source of truth)
locked_conversations_cache = {}


@app.on_event("startup")
async def startup_event():
    """Validate environment and load locked conversations from Supabase"""
    print("\n" + "="*70)
    print("🔍 VALIDATING PRODUCTION ENVIRONMENT")
    print("="*70)

    db_url  = os.getenv("SUPABASE_DB_URL")
    groq_key = os.getenv("GROQ_API_KEY")

    if not db_url:
        raise ValueError("SUPABASE_DB_URL environment variable is required")
    if not groq_key:
        raise ValueError("GROQ_API_KEY environment variable is required")

    print(f"✅ Database URL: {db_url[:50]}...{db_url[-20:]}")
    print(f"✅ Groq API Key: {groq_key[:20]}...")

    # Load locked conversations from Supabase into memory cache
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT customer_number, updated_at
                    FROM leads WHERE status = 'locked'
                """)
                rows = cursor.fetchall()
                for row in rows:
                    locked_conversations_cache[row[0]] = {
                        "locked_at": row[1].isoformat() if row[1] else None,
                        "locked_by": "wife",
                        "reason": "wife_interrupted"
                    }
        print(f"✅ Loaded {len(locked_conversations_cache)} locked conversations from Supabase")
    except Exception as e:
        print(f"⚠️  Could not load locked conversations: {e}")

    print("="*70 + "\n")


# ============================================================
# BOT INITIALIZATION
# ============================================================

bot = ProductionVihaBot()


# ============================================================
# PYDANTIC MODELS
# ============================================================

class ChatRequest(BaseModel):
    user_id: str
    message: str

class LockRequest(BaseModel):
    user_id: str

class LeadsRequest(BaseModel):
    days: int = 7  # Default: last 7 days


# ============================================================
# ENDPOINTS
# ============================================================

@app.post("/lock_conversation")
async def lock_conversation(request: LockRequest):
    user_id = request.user_id

    set_conversation_lock(user_id)

    print(f"\n{'='*70}")
    print(f"🔒 CONVERSATION PERMANENTLY LOCKED")
    print(f"   Customer: {user_id}")
    print(f"   Locked at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}\n")

    return {
        "status": "success",
        "message": f"Conversation locked for {user_id}",
        "locked_at": locked_conversations_cache[user_id]["locked_at"]
    }


@app.post("/unlock_conversation")
async def unlock_conversation(request: LockRequest):
    user_id = request.user_id

    if user_id in locked_conversations_cache:
        lock_info = locked_conversations_cache[user_id].copy()
        remove_conversation_lock(user_id)

        print(f"\n{'='*70}")
        print(f"🔓 CONVERSATION UNLOCKED")
        print(f"   Customer: {user_id}")
        print(f"{'='*70}\n")

        return {
            "status": "success",
            "message": f"Conversation unlocked for {user_id}",
            "was_locked_at": lock_info["locked_at"]
        }
    else:
        # Check Supabase in case memory cache is stale
        lock_info = is_conversation_locked(user_id)
        if lock_info:
            remove_conversation_lock(user_id)
            return {
                "status": "success",
                "message": f"Conversation unlocked for {user_id}"
            }
        return {
            "status": "not_locked",
            "message": f"Conversation was not locked for {user_id}"
        }


@app.post("/reset_conversation")
async def reset_conversation(request: LockRequest):
    user_id = request.user_id

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:

                # Delete checkpoints
                cursor.execute(
                    "DELETE FROM checkpoints WHERE thread_id = %s", (user_id,)
                )
                deleted_checkpoints = cursor.rowcount

                cursor.execute(
                    "DELETE FROM checkpoint_writes WHERE thread_id = %s", (user_id,)
                )
                deleted_writes = cursor.rowcount

                # Delete lead entry so bot starts fresh
                cursor.execute(
                    "DELETE FROM leads WHERE customer_number = %s", (user_id,)
                )

                conn.commit()

        # Clear from memory cache
        was_locked = user_id in locked_conversations_cache
        locked_conversations_cache.pop(user_id, None)

        print(f"\n{'='*70}")
        print(f"🔄 CONVERSATION RESET COMPLETE")
        print(f"   Customer: {user_id}")
        print(f"   Deleted checkpoints: {deleted_checkpoints}")
        print(f"   Deleted writes: {deleted_writes}")
        print(f"{'='*70}\n")

        return {
            "status": "success",
            "message": f"Conversation reset for {user_id}. Bot will start fresh.",
            "reset_at": datetime.now().isoformat(),
            "deleted_checkpoints": deleted_checkpoints,
            "deleted_writes": deleted_writes,
            "was_locked": was_locked
        }

    except Exception as e:
        print(f"❌ Error resetting conversation: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": f"Failed to reset: {str(e)}"}


@app.get("/locked_conversations")
async def get_locked_conversations():
    return {
        "locked_conversations": [
            {
                "user_id": uid,
                "locked_at": info["locked_at"],
                "locked_by": info["locked_by"],
                "reason": info["reason"]
            }
            for uid, info in locked_conversations_cache.items()
        ],
        "total_locked": len(locked_conversations_cache)
    }


# ============================================================
# LEADS ENDPOINT
# ============================================================

@app.post("/leads")
async def get_leads(request: LeadsRequest):
    """
    Return leads for the last N days.
    Called by Node when wife sends: Leads 7
    """
    try:
        days = max(1, min(request.days, 365))  # Clamp between 1 and 365
        since = datetime.now() - timedelta(days=days)

        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT
                        customer_number,
                        quantity,
                        budget_per_piece,
                        location,
                        timeline,
                        status,
                        last_message,
                        created_at,
                        updated_at
                    FROM leads
                    WHERE created_at >= %s
                    ORDER BY updated_at DESC
                """, (since,))

                rows = cursor.fetchall()

        if not rows:
            return {
                "status": "success",
                "days": days,
                "total": 0,
                "leads": [],
                "message": f"No leads in the last {days} day(s)"
            }

        leads = []
        for row in rows:
            customer_number, quantity, budget, location, timeline, status, last_msg, created_at, updated_at = row

            # Format dates
            created_str  = created_at.strftime("%d %b %H:%M")  if created_at  else "-"
            updated_str  = updated_at.strftime("%d %b %H:%M")  if updated_at  else "-"

            leads.append({
                "customer_number": customer_number,
                "quantity":        quantity,
                "budget":          f"₹{budget}" if budget else None,
                "location":        location,
                "timeline":        timeline,
                "status":          status,
                "last_message":    last_msg,
                "created_at":      created_str,
                "updated_at":      updated_str
            })

        return {
            "status": "success",
            "days": days,
            "total": len(leads),
            "leads": leads
        }

    except Exception as e:
        print(f"❌ Leads fetch failed: {e}")
        return {"status": "error", "message": str(e), "leads": []}


# ============================================================
# LEAD INFO ENDPOINT
# ============================================================

@app.get("/lead_info/{customer_number}")
async def get_lead_info(customer_number: str):
    """
    Return full details for a single customer.
    Called by Node when wife sends: Info 919942463672
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT
                        customer_number,
                        quantity,
                        budget_per_piece,
                        location,
                        timeline,
                        status,
                        last_message,
                        created_at,
                        updated_at
                    FROM leads
                    WHERE customer_number = %s
                """, (customer_number,))
                row = cursor.fetchone()

        if not row:
            return {
                "status": "not_found",
                "message": f"No lead found for {customer_number}"
            }

        customer_number, quantity, budget, location, timeline, status, last_msg, created_at, updated_at = row

        return {
            "status": "success",
            "lead": {
                "customer_number": customer_number,
                "quantity":        quantity,
                "budget":          f"₹{budget}" if budget else None,
                "location":        location,
                "timeline":        timeline,
                "status":          status,
                "last_message":    last_msg,
                "created_at":      created_at.isoformat() if created_at else None,
                "updated_at":      updated_at.isoformat() if updated_at else None
            }
        }

    except Exception as e:
        print(f"❌ Lead info fetch failed: {e}")
        return {"status": "error", "message": str(e)}


# ============================================================
# SUMMARY ENDPOINT
# ============================================================

class SummaryRequest(BaseModel):
    start_date: str | None = None  # "2026-02-19"
    end_date: str | None = None    # "2026-02-19"

@app.post("/summary")
async def get_summary(request: SummaryRequest):
    """
    Return business summary for a date range.
    Default: today
    """
    try:
        # Parse dates
        if request.start_date:
            start = datetime.strptime(request.start_date, "%Y-%m-%d")
        else:
            start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        if request.end_date:
            end = datetime.strptime(request.end_date, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59
            )
        else:
            end = datetime.now().replace(hour=23, minute=59, second=59)

        with get_db_connection() as conn:
            with conn.cursor() as cursor:

                # ── Overview counts ──────────────────────────
                cursor.execute("""
                    SELECT
                        COUNT(*)                                            AS total,
                        COUNT(*) FILTER (WHERE status = 'products_shown')  AS products_shown,
                        COUNT(*) FILTER (WHERE status = 'locked')          AS locked,
                        COUNT(*) FILTER (WHERE status = 'requirements_collecting') AS incomplete,
                        COUNT(*) FILTER (
                            WHERE status = 'products_shown'
                            AND updated_at < NOW() - INTERVAL '1 day'
                        )                                                   AS followup_pending
                    FROM leads
                    WHERE created_at BETWEEN %s AND %s
                """, (start, end))
                overview = cursor.fetchone()
                total, products_shown, locked, incomplete, followup_pending = overview

                # ── Averages (quantity > 0 only) ─────────────
                cursor.execute("""
                    SELECT
                        ROUND(AVG(quantity))         AS avg_qty,
                        ROUND(AVG(budget_per_piece)) AS avg_budget
                    FROM leads
                    WHERE created_at BETWEEN %s AND %s
                      AND quantity > 0
                """, (start, end))
                avgs = cursor.fetchone()
                avg_qty, avg_budget = avgs if avgs else (None, None)

                # ── Top locations ────────────────────────────
                cursor.execute("""
                    SELECT location, COUNT(*) AS cnt
                    FROM leads
                    WHERE created_at BETWEEN %s AND %s
                      AND location IS NOT NULL
                    GROUP BY location
                    ORDER BY cnt DESC
                    LIMIT 3
                """, (start, end))
                top_locations = cursor.fetchall()

                # ── Lead details (sorted by priority) ────────
                cursor.execute("""
                    SELECT
                        customer_number, quantity, timeline,
                        location, status, updated_at
                    FROM leads
                    WHERE created_at BETWEEN %s AND %s
                    ORDER BY
                        CASE status
                            WHEN 'products_shown' THEN
                                CASE WHEN updated_at < NOW() - INTERVAL '1 day'
                                     THEN 1 ELSE 3 END
                            WHEN 'requirements_collecting' THEN 2
                            WHEN 'new'                     THEN 4
                            WHEN 'locked'                  THEN 5
                            ELSE 6
                        END,
                        quantity DESC NULLS LAST
                """, (start, end))
                leads_rows = cursor.fetchall()

        # ── Build leads detail list ───────────────────────────
        leads = []
        for row in leads_rows:
            customer_number, quantity, timeline, location, status, updated_at = row
            leads.append({
                "customer_number": customer_number,
                "quantity":        quantity,
                "timeline":        timeline,
                "location":        location,
                "status":          status,
                "updated_at":      updated_at.strftime("%d %b %H:%M") if updated_at else "-"
            })

        # ── Top locations string ──────────────────────────────
        locations_str = ", ".join(
            f"{loc}({cnt})" for loc, cnt in top_locations
        ) if top_locations else "No data"

        return {
            "status":          "success",
            "start_date":      start.strftime("%d %b %Y"),
            "end_date":        end.strftime("%d %b %Y"),
            "total":           total,
            "products_shown":  products_shown,
            "locked":          locked,
            "incomplete":      incomplete,
            "followup_pending": followup_pending,
            "avg_quantity":    int(avg_qty)    if avg_qty    else None,
            "avg_budget":      int(avg_budget) if avg_budget else None,
            "top_locations":   locations_str,
            "leads":           leads
        }

    except Exception as e:
        print(f"❌ Summary failed: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}

# ============================================================
# CHAT ENDPOINT
# ============================================================

@app.post("/chat")
async def chat(request: ChatRequest):
    """Chat endpoint - checks lock, processes message, saves lead"""
    try:
        # ===== PRIORITY CHECK: Is conversation locked? =====
        lock_info = locked_conversations_cache.get(request.user_id)
        if not lock_info:
            # Fallback: check Supabase (catches restarts)
            lock_info = is_conversation_locked(request.user_id)
            if lock_info:
                # Restore to cache
                locked_conversations_cache[request.user_id] = lock_info

        if lock_info:
            print(f"\n{'='*70}")
            print(f"🔒 LOCKED - BOT SILENT for {request.user_id}")
            print(f"{'='*70}\n")

            return {
                "status": "locked",
                "reply": None,
                "needs_handoff": False,
                "products": None,
                "locked": True,
                "locked_at": lock_info["locked_at"],
                "locked_by": lock_info["locked_by"]
            }

        # ===== Normal chat flow =====
        print(f"\n{'='*70}")
        print(f"💬 API Request from: {request.user_id}")
        print(f"📩 Message: {request.message}")
        print(f"{'='*70}")

        response = bot.chat(request.user_id, request.message)

        print(f"\n🔍 DEBUG: Bot response keys: {response.keys()}")
        print(f"🔍 DEBUG: requirements_summary = {response.get('requirements_summary', 'NOT FOUND')}")
        print(f"🔍 DEBUG: customer_requirements = {response.get('customer_requirements', 'NOT FOUND')}")
        print(f"🔍 DEBUG: handoff_reason = {response.get('handoff_reason', 'NOT FOUND')}")

        # ===== SAVE LEAD if requirements exist =====
        has_requirements = (
            response.get("customer_requirements") and
            any(v for v in response["customer_requirements"].values() if v is not None)
        )

        if has_requirements:
            # Determine status
            if response.get("reply") == "[SEND_PRODUCT_IMAGES_WITH_SUMMARY]":
                lead_status = "products_shown"
            elif response.get("needs_handoff"):
                lead_status = "follow_up"
            else:
                lead_status = "requirements_collecting"

            # Attach last_message for lead saving
            response["last_message"] = request.message
            save_or_update_lead(request.user_id, response, lead_status)

        return_data = {
            "status": "success",
            "reply": response["reply"],
            "needs_handoff": response["needs_handoff"],
            "products": response.get("products"),
            "requirements_summary": response.get("requirements_summary"),
            "customer_requirements": response.get("customer_requirements"),
            "handoff_reason": response.get("handoff_reason"),
            "locked": False,
            "customer_number": request.user_id,
            "last_message": request.message
        }

        print(f"🔍 DEBUG: Returning data with these keys: {return_data.keys()}")
        print(f"🔍 DEBUG: Return data: {return_data}\n")

        return return_data

    except Exception as e:
        print(f"❌ ERROR in chat endpoint: {e}")
        import traceback
        traceback.print_exc()

        return {
            "status": "error",
            "reply": None,
            "needs_handoff": True,
            "products": None,
            "locked": False,
            "customer_number": request.user_id,
            "last_message": request.message
        }


# ============================================================
# HEALTH ENDPOINTS
# ============================================================

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "version": "4.0",
        "locked_conversations": len(locked_conversations_cache),
        "timestamp": datetime.now().isoformat()
    }


@app.get("/health-check")
@app.head("/health-check")
async def health_check():
    try:
        db_url = os.getenv("SUPABASE_DB_URL")
        if not db_url:
            return {"status": "unhealthy", "error": "SUPABASE_DB_URL not configured"}

        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM checkpoints")
                checkpoint_count = cursor.fetchone()[0]

        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "database_connected": True,
            "checkpoint_count": checkpoint_count,
            "locked_conversations": len(locked_conversations_cache),
            "groq_api_configured": bool(os.getenv("GROQ_API_KEY"))
        }

    except Exception as e:
        print(f"❌ Health check failed: {e}")
        return {"status": "unhealthy", "error": str(e)}


if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting Complete Bot API v4.0...")
    print("   • Conversation locking (Supabase persistent) ✅")
    print("   • Leads tracking ✅")
    print("   • LEADS / INFO endpoints ✅")
    uvicorn.run(app, host="0.0.0.0", port=8000)