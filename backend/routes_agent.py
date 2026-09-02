"""The front-desk agent's API.

Conversations are persisted, so a chat survives a reload or a closed tab rather
than vanishing. Only the visible messages are stored — tool traffic is never
written down and never replayed.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from agent import model, runtime
from db import get_db

router = APIRouter(prefix="/api/shops/{slug}/agent")
COLLECTION = "conversations"


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: Optional[str] = None


async def ensure_indexes() -> None:
    col = get_db()[COLLECTION]
    await col.create_index([("shop_slug", 1), ("conversation_id", 1)], unique=True)


async def _load(slug: str, cid: str) -> List[dict]:
    doc = await get_db()[COLLECTION].find_one(
        {"shop_slug": slug, "conversation_id": cid}, {"_id": 0, "messages": 1}
    )
    return (doc or {}).get("messages", [])


async def _append(slug: str, cid: str, msgs: List[dict]) -> None:
    await get_db()[COLLECTION].update_one(
        {"shop_slug": slug, "conversation_id": cid},
        {"$push": {"messages": {"$each": msgs}},
         "$set": {"updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")},
         "$setOnInsert": {"shop_slug": slug, "conversation_id": cid,
                          "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}},
        upsert=True,
    )


def register(get_shop):
    from routes_booking import shop_now

    @router.get("/status")
    async def agent_status(slug: str):
        """Whether the desk is connected, and an honest word about cold starts.

        Deliberately does NOT ping the model: waking a GPU just because someone
        opened a page is how a bill runs away.
        """
        cfg = await get_shop(slug)
        return {
            "available": model.configured(),
            "name": cfg.agent.name,
            "greeting": cfg.agent.greeting or f"Welcome to {cfg.name}. How can I help?",
            "cold_start_note": (
                "If nobody's spoken to the desk in a while, the first reply can take "
                "a couple of minutes to come through. The booking form is instant."
            ),
        }

    @router.get("/conversations/{conversation_id}")
    async def get_conversation(slug: str, conversation_id: str):
        return {"conversation_id": conversation_id,
                "messages": await _load(slug, conversation_id)}

    @router.post("/chat")
    async def chat(slug: str, req: ChatIn):
        cfg = await get_shop(slug)
        if not model.configured():
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                                "The front desk isn't connected yet.")

        cid = req.conversation_id or secrets.token_urlsafe(12)
        history = await _load(slug, cid)
        now = shop_now(cfg)

        user_msg = {"role": "user", "content": req.message.strip(),
                    "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        try:
            reply, actions = await runtime.respond(
                cfg, history, req.message.strip(), today=now.date(), now=now
            )
        except model.ModelUnavailable as e:
            # Persist what the client said even when the desk could not answer,
            # so the conversation is intact when they try again.
            await _append(slug, cid, [user_msg])
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e))

        assistant_msg = {"role": "assistant", "content": reply,
                         "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        await _append(slug, cid, [user_msg, assistant_msg])

        return {"conversation_id": cid, "reply": reply,
                # What the agent actually DID this turn, so the UI can refresh
                # the booking views without guessing.
                "actions": actions}

    return router
