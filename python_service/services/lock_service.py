"""
Lock service — manages conversation locks in memory + Supabase
Memory cache = fast lookup
Supabase = source of truth (survives restarts)
"""

from datetime import datetime
from db.connection import get_db_connection

# ============================================================
# IN-MEMORY CACHE
# Fast lookup. Lost on restart — Supabase restores it on startup.
# ============================================================

locked_conversations_cache: dict = {}


# ============================================================
# LOCK OPERATIONS
# ============================================================

def is_conversation_locked(user_id: str) -> dict | None:
    """
    Check if conversation is locked.
    Checks memory cache first, falls back to Supabase.
    Returns lock info dict or None.
    """
    # Fast path: memory cache
    if user_id in locked_conversations_cache:
        return locked_conversations_cache[user_id]

    # Slow path: Supabase (catches post-restart state)
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
        return None


def set_conversation_lock(user_id: str):
    """
    Lock conversation in Supabase + memory cache.
    """
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
    """
    Unlock conversation in Supabase + memory cache.
    """
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


def load_locked_conversations_from_db():
    """
    Load all locked conversations from Supabase into memory cache.
    Called once on startup.
    """
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