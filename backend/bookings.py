"""Booking persistence.

Bookings are stored per shop with the local date and start time the shop's own
staff would say out loud, plus `block_min` — the reserved chair time including
processing. Availability, the admin calendar and (later) check-in all read the
same records, so chat and form can never drift into two sources of truth.
"""
from __future__ import annotations

import secrets
from datetime import date as Date, datetime, timezone
from typing import List, Optional

from db import get_db

COLLECTION = "bookings"
ACTIVE = ("booked", "checked_in", "in_service")


def new_reference() -> str:
    """Short, unambiguous booking reference a client can read down the phone.
    Excludes characters that get misheard or misread (0/O, 1/I)."""
    alphabet = "ACDEFGHJKLMNPQRTUVWXY2346789"
    return "".join(secrets.choice(alphabet) for _ in range(6))


async def ensure_indexes() -> None:
    col = get_db()[COLLECTION]
    await col.create_index([("shop_slug", 1), ("date", 1), ("technician_id", 1)])
    await col.create_index([("shop_slug", 1), ("reference", 1)], unique=True)
    await col.create_index([("shop_slug", 1), ("client_key", 1)])


async def for_day(shop_slug: str, d: Date, *, technician_id: Optional[str] = None) -> List[dict]:
    """Every booking that occupies chair time on a date. Cancelled bookings are
    excluded here so they never block a slot."""
    q = {"shop_slug": shop_slug, "date": d.isoformat(), "status": {"$in": list(ACTIVE)}}
    if technician_id:
        q["technician_id"] = technician_id
    return [b async for b in get_db()[COLLECTION].find(q, {"_id": 0})]


async def overlapping(shop_slug: str, d: Date, technician_id: str, start_min: int, block_min: int) -> Optional[dict]:
    """The booking this one would collide with, if any.

    Re-checked inside the create path so two people confirming the same slot at
    the same moment cannot both win.
    """
    from scheduling import to_min

    for b in await for_day(shop_slug, d, technician_id=technician_id):
        b_start = to_min(b["start"])
        if start_min < b_start + int(b["block_min"]) and b_start < start_min + block_min:
            return b
    return None


async def create(doc: dict) -> dict:
    # client_key is what ties a booking to a returning client (CRM, colour memory).
    doc = {**doc, "client_key": normalise_phone((doc.get("client") or {}).get("phone", "")),
           "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    await get_db()[COLLECTION].insert_one(dict(doc))
    return doc


async def get(shop_slug: str, reference: str) -> Optional[dict]:
    return await get_db()[COLLECTION].find_one(
        {"shop_slug": shop_slug, "reference": reference.upper()}, {"_id": 0}
    )


async def set_status(shop_slug: str, reference: str, status: str) -> Optional[dict]:
    return await get_db()[COLLECTION].find_one_and_update(
        {"shop_slug": shop_slug, "reference": reference.upper()},
        {"$set": {"status": status}},
        projection={"_id": 0},
        return_document=True,
    )


def normalise_phone(phone: str) -> str:
    """Digits only — how a shop actually recognises a returning client, however
    they typed their number this time."""
    return "".join(c for c in str(phone or "") if c.isdigit())[-10:] or ""


async def in_range(shop_slug: str, start: Date, end: Date) -> List[dict]:
    """Every booking between two dates inclusive, ordered for a calendar."""
    cur = get_db()[COLLECTION].find(
        {"shop_slug": shop_slug, "date": {"$gte": start.isoformat(), "$lte": end.isoformat()}},
        {"_id": 0},
    ).sort([("date", 1), ("start", 1)])
    return [b async for b in cur]


async def for_client(shop_slug: str, phone: str) -> List[dict]:
    """A client's whole history, newest first."""
    cur = get_db()[COLLECTION].find(
        {"shop_slug": shop_slug, "client_key": normalise_phone(phone)}, {"_id": 0}
    ).sort([("date", -1), ("start", -1)])
    return [b async for b in cur]


async def update_fields(shop_slug: str, reference: str, fields: dict) -> Optional[dict]:
    return await get_db()[COLLECTION].find_one_and_update(
        {"shop_slug": shop_slug, "reference": reference.upper()},
        {"$set": fields},
        projection={"_id": 0},
        return_document=True,
    )
