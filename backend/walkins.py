"""The walk-in queue.

A walk-in is not a booking — it has no slot — so it lives in its own collection
and gets a position in line rather than a time. When a tech takes them, the
walk-in is converted into a real booking so that checkout, history and the
admin calendar have exactly one kind of record to read.
"""
from __future__ import annotations

from datetime import date as Date, datetime, timezone
from typing import List, Optional

from db import get_db
from shop_config import ShopConfig

COLLECTION = "walkins"
WAITING = "waiting"


async def ensure_indexes() -> None:
    col = get_db()[COLLECTION]
    await col.create_index([("shop_slug", 1), ("date", 1), ("status", 1)])
    await col.create_index([("shop_slug", 1), ("reference", 1)], unique=True)


async def add(doc: dict) -> dict:
    doc = {**doc, "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    await get_db()[COLLECTION].insert_one(dict(doc))
    return doc


async def waiting(shop_slug: str, d: Date) -> List[dict]:
    """Everyone still in line today, in the order they arrived."""
    cur = get_db()[COLLECTION].find(
        {"shop_slug": shop_slug, "date": d.isoformat(), "status": WAITING}, {"_id": 0}
    ).sort("created_at", 1)
    return [w async for w in cur]


async def get(shop_slug: str, reference: str) -> Optional[dict]:
    return await get_db()[COLLECTION].find_one(
        {"shop_slug": shop_slug, "reference": reference.upper()}, {"_id": 0}
    )


async def set_status(shop_slug: str, reference: str, status: str, extra: Optional[dict] = None) -> Optional[dict]:
    return await get_db()[COLLECTION].find_one_and_update(
        {"shop_slug": shop_slug, "reference": reference.upper()},
        {"$set": {"status": status, **(extra or {})}},
        projection={"_id": 0},
        return_document=True,
    )


def estimate_wait(cfg: ShopConfig, ahead: List[dict], techs_on_floor: int) -> int:
    """Rough minutes until this person sits down.

    Total chair time queued ahead, spread across the technicians actually
    working. Deliberately a plain estimate — a queue that pretends to be precise
    is worse than one that is honest.
    """
    if techs_on_floor <= 0:
        return 0
    total = 0
    for w in ahead:
        svc = cfg.service(w.get("service_id", ""))
        total += svc.block_min if svc else 45
    return int(total / techs_on_floor)
