"""The admin panel's API — everything a front desk runs the shop from.

Every route here is behind `require_admin` (VULN-AUTH-01). Staff actions are
deliberately allowed to do things the public flow refuses — book inside the
lead-time window, place an appointment outside the slot grid — because the desk
can see the room. What staff CANNOT do is double-book a technician: the overlap
check applies to them exactly as it does to the public.
"""
from __future__ import annotations

from datetime import date as Date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

import bookings
import checkout as checkout_mod
import clients
import payments
import reviews
import scheduling
import shop_store
from scheduling import QuoteError, build_quote, to_min
from security import require_admin
from shop_config import DAYS, ShopConfig

router = APIRouter(prefix="/api/shops/{slug}/admin", dependencies=[Depends(require_admin)])
public = APIRouter(prefix="/api/shops/{slug}")     # review submission is public


class ManualBooking(BaseModel):
    service: str
    date: str
    start: str
    technician: str                      # the desk always names the tech
    shape: Optional[str] = None
    length: Optional[str] = None
    finish: Optional[str] = None
    colour: Optional[str] = None
    name: str = Field(min_length=1, max_length=120)
    phone: str = Field(min_length=4, max_length=40)
    email: str = Field(default="", max_length=200)
    notes: str = Field(default="", max_length=1000)


class Reschedule(BaseModel):
    date: Optional[str] = None
    start: Optional[str] = None
    technician: Optional[str] = None


class ClientRecord(BaseModel):
    notes: str = Field(default="", max_length=4000)
    preferences: str = Field(default="", max_length=2000)
    allergies: str = Field(default="", max_length=1000)


class ReviewIn(BaseModel):
    reference: str
    rating: int = Field(ge=1, le=5)
    text: str = Field(default="", max_length=1500)


def _deep_merge(base: dict, patch: dict) -> dict:
    """Merge a config patch. Lists are replaced wholesale — a services list with
    one item removed must mean exactly that, not a merge of the survivors."""
    out = dict(base)
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def register(get_shop):
    from routes_booking import shop_now

    # ------------------------------------------------------------ calendar ---
    @router.get("/calendar")
    async def calendar(slug: str, date: Optional[str] = None, days: int = Query(1, ge=1, le=31)):
        """The book, by technician, for one or more days."""
        cfg = await get_shop(slug)
        start = Date.fromisoformat(date) if date else shop_now(cfg).date()
        end = start + timedelta(days=days - 1)
        rows = await bookings.in_range(slug, start, end)

        out: List[dict] = []
        for i in range(days):
            d = start + timedelta(days=i)
            dk = scheduling.day_key(d)
            hours = cfg.hours.get(dk)
            day_rows = [b for b in rows if b["date"] == d.isoformat()]
            out.append({
                "date": d.isoformat(),
                "day": dk,
                "open": cfg.is_open_on(dk),
                "hours": None if not hours or hours.closed else {"open": hours.open, "close": hours.close},
                "technicians": [
                    {
                        "id": t.id, "name": t.name,
                        "working": t.works_on(dk),
                        "shift": (None if not t.works_on(dk)
                                  else {"start": t.schedule[dk].start, "end": t.schedule[dk].end}),
                        "bookings": sorted(
                            [b for b in day_rows if b["technician_id"] == t.id],
                            key=lambda b: b["start"],
                        ),
                    }
                    for t in cfg.technicians if t.active
                ],
                "unassigned": [b for b in day_rows
                               if b["technician_id"] not in {t.id for t in cfg.technicians}],
            })
        return {"from": start.isoformat(), "to": end.isoformat(), "days": out}

    # --------------------------------------------------- manual scheduling ---
    @router.post("/bookings", status_code=status.HTTP_201_CREATED)
    async def manual_booking(slug: str, req: ManualBooking):
        """Book from the desk.

        Lead time and the slot grid are the public flow's guardrails, not the
        shop's — staff can place an appointment anywhere in a tech's shift. The
        one rule that still holds is that a tech cannot be in two chairs at once.
        """
        cfg = await get_shop(slug)
        d = Date.fromisoformat(req.date)
        tech = cfg.technician(req.technician)
        if tech is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{req.technician!r} is not a technician here")

        try:
            q = build_quote(cfg, req.service, shape=req.shape, length=req.length,
                            finish=req.finish, colour=req.colour)
        except QuoteError as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))

        start_min = to_min(req.start)
        clash = await bookings.overlapping(slug, d, req.technician, start_min, q.block_min)
        if clash:
            raise HTTPException(status.HTTP_409_CONFLICT,
                                f"{tech.name} already has {clash['reference']} at {clash['start']}")

        return await bookings.create({
            "shop_slug": slug,
            "reference": bookings.new_reference(),
            "status": "booked",
            "date": d.isoformat(),
            "start": req.start,
            "end": scheduling.to_hhmm(start_min + q.block_min),
            "technician_id": tech.id,
            "technician_name": tech.name,
            "tech_was_chosen": True,
            "client": {"name": req.name.strip(), "phone": req.phone.strip(),
                       "email": req.email.strip(), "notes": req.notes.strip()},
            "quote": q.as_dict(),
            "duration_min": q.duration_min,
            "buffer_min": q.buffer_min,
            "block_min": q.block_min,
            "price": round(q.price, 2),
            "deposit": {"due": q.deposit_due, "reason": q.deposit_reason,
                        "status": "owed" if q.deposit_due else "not_required",
                        "refundable_until_hours": cfg.deposit.refundable_until_hours},
            "remind_at": scheduling.reminder_at(cfg, d, req.start, q.block_min),
            "source": "front-desk",
        })

    @router.patch("/bookings/{reference}")
    async def reschedule(slug: str, reference: str, req: Reschedule):
        """Move an appointment: another day, another time, another technician."""
        cfg = await get_shop(slug)
        b = await bookings.get(slug, reference)
        if b is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "no booking with that reference")
        if b["status"] in ("complete", "cancelled"):
            raise HTTPException(status.HTTP_409_CONFLICT, f"a {b['status']} booking cannot be moved")

        d = Date.fromisoformat(req.date or b["date"])
        start = req.start or b["start"]
        tech_id = req.technician or b["technician_id"]
        tech = cfg.technician(tech_id)
        if tech is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{tech_id!r} is not a technician here")

        start_min = to_min(start)
        block = int(b["block_min"])
        clash = await bookings.overlapping(slug, d, tech_id, start_min, block)
        if clash and clash["reference"] != b["reference"]:
            raise HTTPException(status.HTTP_409_CONFLICT,
                                f"{tech.name} already has {clash['reference']} at {clash['start']}")

        return await bookings.update_fields(slug, reference, {
            "date": d.isoformat(),
            "start": start,
            "end": scheduling.to_hhmm(start_min + block),
            "technician_id": tech_id,
            "technician_name": tech.name,
            "remind_at": scheduling.reminder_at(cfg, d, start, block),
            "rescheduled_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })

    @router.post("/bookings/{reference}/complete")
    async def mark_complete(slug: str, reference: str):
        """Mark done without ringing anything up — for a comp, a redo, or a
        ticket already settled elsewhere."""
        b = await bookings.get(slug, reference)
        if b is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "no booking with that reference")
        if b["status"] == "cancelled":
            raise HTTPException(status.HTTP_409_CONFLICT, "a cancelled booking cannot be completed")
        return await bookings.update_fields(slug, reference, {
            "status": "complete",
            "completed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })

    @router.get("/bookings")
    async def find_bookings(slug: str, q: str = "", date: Optional[str] = None):
        cfg = await get_shop(slug)
        if q:
            one = await bookings.get(slug, q)
            if one:
                return [one]
            return await bookings.for_client(slug, q)
        d = Date.fromisoformat(date) if date else shop_now(cfg).date()
        return await bookings.in_range(slug, d, d)

    # ------------------------------------------------- manual card payment ---
    @router.post("/bookings/{reference}/payment")
    async def manual_payment(slug: str, reference: str,
                             amount: float = Body(..., embed=True),
                             method: str = Body("cash", embed=True),
                             note: str = Body("", embed=True)):
        """Record a payment taken at the desk (cash, or a card run on the shop's
        own terminal). Card-present terminals settle outside this platform, so
        this records the fact rather than pretending to charge."""
        b = await bookings.get(slug, reference)
        if b is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "no booking with that reference")
        if amount < 0:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "amount cannot be negative")
        cfg = await get_shop(slug)
        payment = {"method": method, "paid": True, "amount": round(amount, 2),
                   "currency": cfg.payments.currency, "provider": "manual",
                   "transaction_id": "", "status": "recorded_at_desk",
                   "note": note[:300], "sandbox": False}
        ticket = checkout_mod.build_ticket(cfg, b)
        receipt = checkout_mod.receipt_for(cfg, b, ticket, payment)
        return await bookings.update_fields(slug, reference, {
            "status": "complete", "payment": payment, "receipt": receipt,
            "completed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })

    # ----------------------------------------------------------------- CRM ---
    @router.get("/clients")
    async def list_clients(slug: str, q: str = "", limit: int = Query(50, ge=1, le=200)):
        cfg = await get_shop(slug)
        return await clients.search(cfg, q, limit)

    @router.get("/clients/{key}")
    async def client_profile(slug: str, key: str):
        cfg = await get_shop(slug)
        prof = await clients.profile(cfg, key)
        if prof is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "no client with that number")
        return prof

    @router.put("/clients/{key}")
    async def save_client(slug: str, key: str, req: ClientRecord):
        cfg = await get_shop(slug)
        k = bookings.normalise_phone(key)
        return await clients.save_notes(cfg.slug, k, req.model_dump())

    # -------------------------------------------------------- config edits ---
    @router.patch("/config")
    async def patch_config(slug: str, patch: Dict[str, Any] = Body(...)):
        """Edit services, technicians, hours, menus, deposit or booking rules.

        The patch is merged and then validated through the SAME schema as a seed
        file, so a bad edit is refused before it can reach the storefront.
        """
        cfg = await get_shop(slug)
        merged = _deep_merge(cfg.model_dump(mode="json"), patch)
        merged["slug"] = cfg.slug                     # the slug is the identity; never patched
        try:
            new_cfg = ShopConfig.model_validate(merged)
        except Exception as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"invalid config: {e}")
        await shop_store.save_shop(new_cfg)
        return new_cfg.model_dump(mode="json")

    # ------------------------------------------------------------- reviews ---
    @router.get("/reviews")
    async def admin_reviews(slug: str):
        return {"stats": await reviews.stats(slug), "reviews": await reviews.listing(slug)}

    @router.post("/reviews/{reference}/publish")
    async def publish_review(slug: str, reference: str, published: bool = Body(True, embed=True)):
        r = await reviews.set_published(slug, reference, published)
        if r is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "no review for that booking")
        return r

    @public.post("/reviews", status_code=status.HTTP_201_CREATED)
    async def leave_review(slug: str, req: ReviewIn):
        """Public, but only against a real completed visit, and only once."""
        b = await bookings.get(slug, req.reference)
        if b is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "no booking with that reference")
        if b["status"] != "complete":
            raise HTTPException(status.HTTP_409_CONFLICT, "you can review a visit once it's finished")
        if await reviews.get(slug, req.reference):
            raise HTTPException(status.HTTP_409_CONFLICT, "that visit has already been reviewed")
        return await reviews.add(slug, b, req.rating, req.text)

    @public.get("/reviews")
    async def public_reviews(slug: str, limit: int = Query(20, ge=1, le=100)):
        return {"stats": await reviews.stats(slug),
                "reviews": await reviews.listing(slug, limit=limit, published_only=True)}

    return router, public
