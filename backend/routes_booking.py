"""Booking API — quote, availability, confirm, look up.

The field-based flow and (from Phase 5) the front-desk agent both go through
these functions, so there is exactly one implementation of "what does this cost,
when is it free, and is this slot still open".
"""
from __future__ import annotations

from datetime import date as Date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator

import bookings
import scheduling
from scheduling import QuoteError, build_quote, to_min
from shop_config import ShopConfig

router = APIRouter(prefix="/api/shops/{slug}")


def shop_now(cfg: ShopConfig) -> datetime:
    """The shop's own wall clock — what "today" and "too late to book" mean."""
    try:
        return datetime.now(ZoneInfo(cfg.timezone)).replace(tzinfo=None)
    except Exception:
        return datetime.now()


def _parse_date(cfg: ShopConfig, raw: Optional[str]) -> Date:
    if not raw:
        return shop_now(cfg).date()
    try:
        return Date.fromisoformat(raw)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"date must be YYYY-MM-DD, got {raw!r}")


def _quote_or_400(cfg: ShopConfig, **kw):
    try:
        return build_quote(cfg, **kw)
    except QuoteError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))


class BookingRequest(BaseModel):
    """Defined at module level on purpose: with postponed annotations, FastAPI
    resolves a handler's body model out of module globals, so a class nested in
    register() would be read as a query parameter instead of the request body."""
    service: str
    date: str
    start: str
    shape: Optional[str] = None
    length: Optional[str] = None
    finish: Optional[str] = None
    colour: Optional[str] = None
    technician: Optional[str] = None          # None => no preference
    name: str = Field(min_length=1, max_length=120)
    phone: str = Field(min_length=4, max_length=40)
    email: str = Field(default="", max_length=200)
    notes: str = Field(default="", max_length=1000)

    @field_validator("start")
    @classmethod
    def _hhmm(cls, v: str) -> str:
        h, sep, m = v.partition(":")
        if not (sep and h.isdigit() and m.isdigit()):
            raise ValueError("start must be HH:MM")
        return f"{int(h):02d}:{int(m):02d}"


def register(get_shop):
    """Wired with the app's shop loader so this module never touches storage
    layout or the 404 policy itself."""

    @router.get("/quote")
    async def quote(
        slug: str,
        service: str,
        shape: Optional[str] = None,
        length: Optional[str] = None,
        finish: Optional[str] = None,
        colour: Optional[str] = None,
    ):
        """Price and chair time for a selection, itemised."""
        cfg = await get_shop(slug)
        return _quote_or_400(cfg, service_id=service, shape=shape, length=length,
                             finish=finish, colour=colour).as_dict()

    @router.get("/availability")
    async def availability(
        slug: str,
        service: str,
        date: Optional[str] = None,
        shape: Optional[str] = None,
        length: Optional[str] = None,
        finish: Optional[str] = None,
        technician: Optional[str] = None,
    ):
        """Real open start times for a real selection on a real date."""
        cfg = await get_shop(slug)
        d = _parse_date(cfg, date)
        now = shop_now(cfg)

        first, last = scheduling.bookable_range(cfg, now.date())
        if d < first or d > last:
            return {"date": d.isoformat(), "slots": [], "by_technician": {},
                    "closed_reason": "outside the booking window"}

        q = _quote_or_400(cfg, service_id=service, shape=shape, length=length, finish=finish)
        if technician and cfg.technician(technician) is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{technician!r} is not a technician here")

        busy = scheduling.busy_from_bookings(await bookings.for_day(slug, d))
        by_tech = scheduling.availability(cfg, d, q.block_min, busy, tech_id=technician, now=now)

        closed = ""
        if not by_tech:
            dk = scheduling.day_key(d)
            if not cfg.is_open_on(dk):
                closed = "closed that day"
            else:
                closed = "fully booked" if busy else "no technician available"

        return {
            "date": d.isoformat(),
            "block_min": q.block_min,
            "duration_min": q.duration_min,
            "buffer_min": q.buffer_min,
            "slots": scheduling.merge_slots(by_tech),
            "by_technician": by_tech,
            "closed_reason": closed,
        }

    @router.get("/availability/days")
    async def availability_days(
        slug: str,
        service: str,
        days: int = Query(14, ge=1, le=60),
        start: Optional[str] = None,
        shape: Optional[str] = None,
        length: Optional[str] = None,
        finish: Optional[str] = None,
        technician: Optional[str] = None,
    ):
        """Which of the next N days have anything open — so the date picker can
        grey out closed and full days instead of letting people click into a
        dead end."""
        cfg = await get_shop(slug)
        now = shop_now(cfg)
        first = _parse_date(cfg, start) if start else now.date()
        q = _quote_or_400(cfg, service_id=service, shape=shape, length=length, finish=finish)

        _, last = scheduling.bookable_range(cfg, now.date())
        out = []
        for i in range(days):
            d = first + timedelta(days=i)
            if d > last:
                break
            busy = scheduling.busy_from_bookings(await bookings.for_day(slug, d))
            by_tech = scheduling.availability(cfg, d, q.block_min, busy, tech_id=technician, now=now)
            slots = scheduling.merge_slots(by_tech)
            out.append({
                "date": d.isoformat(),
                "day": scheduling.day_key(d),
                "open": cfg.is_open_on(scheduling.day_key(d)),
                "count": len(slots),
                "first": slots[0] if slots else None,
            })
        return {"days": out, "block_min": q.block_min}

    @router.post("/bookings", status_code=status.HTTP_201_CREATED)
    async def create_booking(slug: str, req: BookingRequest):
        """Confirm a booking.

        Availability is recomputed here rather than trusted from the client, and
        the overlap check runs again immediately before the insert, so a slot
        that went while the client was filling in their details is refused
        instead of double-booked.
        """
        cfg = await get_shop(slug)
        d = _parse_date(cfg, req.date)
        now = shop_now(cfg)

        first, last = scheduling.bookable_range(cfg, now.date())
        if d < first or d > last:
            raise HTTPException(status.HTTP_409_CONFLICT, "that date is outside the booking window")

        q = _quote_or_400(cfg, service_id=req.service, shape=req.shape, length=req.length,
                          finish=req.finish, colour=req.colour)

        busy = scheduling.busy_from_bookings(await bookings.for_day(slug, d))
        by_tech = scheduling.availability(cfg, d, q.block_min, busy, tech_id=req.technician, now=now)

        # "No preference" resolves to whoever is genuinely free at that time.
        candidates = [t for t, slots in by_tech.items() if req.start in slots]
        if not candidates:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"{req.start} is no longer available for that service on {d.isoformat()}",
            )
        tech_id = req.technician or candidates[0]

        start_min = to_min(req.start)
        clash = await bookings.overlapping(slug, d, tech_id, start_min, q.block_min)
        if clash:
            raise HTTPException(status.HTTP_409_CONFLICT, "that slot was just taken")

        tech = cfg.technician(tech_id)
        doc = {
            "shop_slug": slug,
            "reference": bookings.new_reference(),
            "status": "booked",
            "date": d.isoformat(),
            "start": req.start,
            "end": scheduling.to_hhmm(start_min + q.block_min),
            "technician_id": tech_id,
            "technician_name": tech.name if tech else tech_id,
            "tech_was_chosen": bool(req.technician),
            "client": {"name": req.name.strip(), "phone": req.phone.strip(),
                       "email": req.email.strip(), "notes": req.notes.strip()},
            "quote": q.as_dict(),
            "duration_min": q.duration_min,
            "buffer_min": q.buffer_min,
            "block_min": q.block_min,
            "price": round(q.price, 2),
            "deposit": {
                "due": q.deposit_due,
                "reason": q.deposit_reason,
                # Phase 3 wires the processors; until then the amount owed is
                # recorded and settled at the shop, never faked as collected.
                "status": "owed" if q.deposit_due else "not_required",
                "refundable_until_hours": cfg.deposit.refundable_until_hours,
            },
            "remind_at": scheduling.reminder_at(cfg, d, req.start, q.block_min),
            "source": "web",
        }
        return await bookings.create(doc)

    @router.get("/bookings/{reference}")
    async def get_booking(slug: str, reference: str):
        b = await bookings.get(slug, reference)
        if b is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "no booking with that reference")
        return b

    @router.post("/bookings/{reference}/cancel")
    async def cancel_booking(slug: str, reference: str):
        b = await bookings.get(slug, reference)
        if b is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "no booking with that reference")
        if b["status"] == "cancelled":
            return b
        if b["status"] not in bookings.ACTIVE:
            raise HTTPException(status.HTTP_409_CONFLICT, f"a {b['status']} booking cannot be cancelled")
        return await bookings.set_status(slug, reference, "cancelled")

    return router
