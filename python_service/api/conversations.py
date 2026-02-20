"""
Conversation management endpoints
POST /lock_conversation
POST /unlock_conversation
POST /reset_conversation
GET  /locked_conversations
"""

from fastapi import APIRouter
from datetime import datetime
from models.schemas import LockRequest
from services.lock_service import (
    locked_conversations_cache,
    is_conversation_locked,
    set_conversation_lock,
    remove_conversation_lock
)
from db.connection import get_db_connection

router = APIRouter()


# ============================================================
# LOCK
# ============================================================

@router.post("/lock_conversation")
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


# ============================================================
# UNLOCK
# ============================================================

@router.post("/unlock_conversation")
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
        # Check Supabase in case memory cache is stale (post-restart)
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


# ============================================================
# RESET
# ============================================================

@router.post("/reset_conversation")
async def reset_conversation(request: LockRequest):
    user_id = request.user_id

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:

                # Delete LangGraph checkpoints
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


# ============================================================
# LIST LOCKED (memory cache view)
# ============================================================

@router.get("/locked_conversations")
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