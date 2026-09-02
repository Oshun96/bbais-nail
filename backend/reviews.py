"""Reviews.

A review can only be left against a booking that actually happened, and only
once — the booking reference is the proof of visit, so the shop cannot be
review-bombed by someone who was never there.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from db import get_db

COLLECTION = "reviews"


async def ensure_indexes() -> None:
    col = get_db()[COLLECTION]
    await col.create_index([("shop_slug", 1), ("reference", 1)], unique=True)
    await col.create_index([("shop_slug", 1), ("created_at", -1)])


async def get(shop_slug: str, reference: str) -> Optional[dict]:
    return await get_db()[COLLECTION].find_one(
        {"shop_slug": shop_slug, "reference": reference.upper()}, {"_id": 0}
    )


async def add(shop_slug: str, booking: dict, rating: int, text: str) -> dict:
    doc = {
        "shop_slug": shop_slug,
        "reference": booking["reference"],
        "rating": int(rating),
        "text": text.strip()[:1500],
        "client_name": (booking.get("client") or {}).get("name", ""),
        "client_key": booking.get("client_key", ""),
        "technician_id": booking.get("technician_id", ""),
        "technician_name": booking.get("technician_name", ""),
        "service": (booking.get("quote") or {}).get("service_name", ""),
        "visited_on": booking.get("date"),
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "published": True,
    }
    await get_db()[COLLECTION].insert_one(dict(doc))
    return doc


async def listing(shop_slug: str, *, limit: int = 50, published_only: bool = False) -> List[dict]:
    q = {"shop_slug": shop_slug}
    if published_only:
        q["published"] = True
    cur = get_db()[COLLECTION].find(q, {"_id": 0}).sort("created_at", -1).limit(limit)
    return [r async for r in cur]


async def set_published(shop_slug: str, reference: str, published: bool) -> Optional[dict]:
    return await get_db()[COLLECTION].find_one_and_update(
        {"shop_slug": shop_slug, "reference": reference.upper()},
        {"$set": {"published": published}},
        projection={"_id": 0},
        return_document=True,
    )


async def stats(shop_slug: str) -> dict:
    rows = await listing(shop_slug, limit=1000, published_only=True)
    if not rows:
        return {"count": 0, "average": 0.0}
    return {"count": len(rows),
            "average": round(sum(r["rating"] for r in rows) / len(rows), 2)}
