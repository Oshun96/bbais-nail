"""Client CRM.

A client is not a separate account — a nail shop knows people by phone number.
So the history, spend and colour memory are DERIVED from bookings, and only the
things a shop types itself (notes, preferences, allergies) are stored.

That means a client record can never drift out of sync with what actually
happened at the chair.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import List, Optional

import bookings
from db import get_db
from shop_config import ShopConfig

COLLECTION = "clients"


async def ensure_indexes() -> None:
    await get_db()[COLLECTION].create_index([("shop_slug", 1), ("client_key", 1)], unique=True)


async def notes_for(shop_slug: str, key: str) -> dict:
    doc = await get_db()[COLLECTION].find_one(
        {"shop_slug": shop_slug, "client_key": key}, {"_id": 0}
    )
    return doc or {"shop_slug": shop_slug, "client_key": key, "notes": "",
                   "preferences": "", "allergies": ""}


async def save_notes(shop_slug: str, key: str, fields: dict) -> dict:
    allowed = {k: v for k, v in fields.items() if k in ("notes", "preferences", "allergies")}
    allowed["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    await get_db()[COLLECTION].update_one(
        {"shop_slug": shop_slug, "client_key": key},
        {"$set": allowed, "$setOnInsert": {"shop_slug": shop_slug, "client_key": key}},
        upsert=True,
    )
    return await notes_for(shop_slug, key)


def colour_memory(cfg: ShopConfig, history: List[dict], limit: int = 6) -> List[dict]:
    """What they actually had, most recent first — the question every client is
    asked and nobody remembers ("what was that colour last time?")."""
    seen, out = set(), []
    for b in history:
        if b.get("status") == "cancelled":
            continue
        q = b.get("quote") or {}
        cid = q.get("colour_id")
        if not cid or cid in seen:
            continue
        col = cfg.colour(cid)
        if col is None:
            continue
        seen.add(cid)
        out.append({
            "id": col.id, "name": col.name, "hex": col.hex,
            "family": col.family, "finish": col.finish,
            "last_had": b.get("date"), "on": q.get("service_name", ""),
        })
        if len(out) >= limit:
            break
    return out


def summarise(cfg: ShopConfig, history: List[dict]) -> dict:
    """The at-a-glance the front desk needs while the phone is still ringing."""
    done = [b for b in history if b.get("status") == "complete"]
    spend = sum(float((b.get("receipt") or {}).get("ticket", {}).get("total") or b.get("price") or 0)
                for b in done)
    cancelled = [b for b in history if b.get("status") == "cancelled"]
    techs = [b.get("technician_name") for b in done if b.get("technician_name")]
    usual_tech = max(set(techs), key=techs.count) if techs else ""
    shapes = [(b.get("quote") or {}).get("options", {}).get("shape") for b in done]
    shapes = [s for s in shapes if s]
    usual_shape = max(set(shapes), key=shapes.count) if shapes else ""
    return {
        "visits": len(done),
        "upcoming": len([b for b in history if b.get("status") in ("booked", "checked_in")]),
        "cancelled": len(cancelled),
        "total_spend": round(spend, 2),
        "average_ticket": round(spend / len(done), 2) if done else 0,
        "first_visit": done[-1]["date"] if done else None,
        "last_visit": done[0]["date"] if done else None,
        "usual_technician": usual_tech,
        "usual_shape": usual_shape,
    }


async def profile(cfg: ShopConfig, phone: str) -> Optional[dict]:
    key = bookings.normalise_phone(phone)
    if not key:
        return None
    history = await bookings.for_client(cfg.slug, key)
    if not history:
        return None
    latest = history[0].get("client", {})
    return {
        "client_key": key,
        "name": latest.get("name", ""),
        "phone": latest.get("phone", ""),
        "email": next((b.get("client", {}).get("email") for b in history
                       if b.get("client", {}).get("email")), ""),
        "summary": summarise(cfg, history),
        "colour_memory": colour_memory(cfg, history),
        "record": await notes_for(cfg.slug, key),
        "history": [
            {"reference": b["reference"], "date": b["date"], "start": b["start"],
             "status": b["status"], "service": (b.get("quote") or {}).get("service_name", ""),
             "technician": b.get("technician_name", ""),
             "options": (b.get("quote") or {}).get("options", {}),
             "colour_id": (b.get("quote") or {}).get("colour_id"),
             "total": float((b.get("receipt") or {}).get("ticket", {}).get("total") or b.get("price") or 0)}
            for b in history
        ],
    }


async def search(cfg: ShopConfig, q: str = "", limit: int = 50) -> List[dict]:
    """Everyone the shop has seen, newest first, optionally filtered by name or
    phone. Built from bookings so there is no separate list to keep in step.

    The filter runs INSIDE the pipeline, before the limit — filtering a page of
    50 after the fact would make anyone outside the 50 most recent unfindable,
    which is precisely the client a busy shop is searching for.
    """
    pipeline: List[dict] = [
        {"$match": {"shop_slug": cfg.slug, "client_key": {"$nin": ["", None]}}},
        {"$sort": {"date": -1, "start": -1}},
        {"$group": {
            "_id": "$client_key",
            "name": {"$first": "$client.name"},
            "phone": {"$first": "$client.phone"},
            "last_date": {"$first": "$date"},
            "last_service": {"$first": "$quote.service_name"},
            "visits": {"$sum": {"$cond": [{"$eq": ["$status", "complete"]}, 1, 0]}},
            "upcoming": {"$sum": {"$cond": [{"$in": ["$status", ["booked", "checked_in"]]}, 1, 0]}},
        }},
    ]

    if q.strip():
        term = re.escape(q.strip())
        digits = bookings.normalise_phone(q)
        ors: List[dict] = [{"name": {"$regex": term, "$options": "i"}}]
        if digits:
            ors.append({"_id": {"$regex": re.escape(digits)}})
        pipeline.append({"$match": {"$or": ors}})

    pipeline += [{"$sort": {"last_date": -1}}, {"$limit": limit}]

    rows = [r async for r in get_db()[bookings.COLLECTION].aggregate(pipeline)]
    return [{"client_key": r["_id"], **{k: v for k, v in r.items() if k != "_id"}} for r in rows]
