"""Check-in, the walk-in queue, and checkout.

The money path is deliberately two-legged: `/checkout/begin` computes the ticket
and opens a payment with the PROVIDER for the amount the server calculated, and
`/checkout/settle` asks the provider what actually happened before anything is
marked paid. The browser never states an amount and is never believed about the
outcome.
"""
from __future__ import annotations

from datetime import date as Date, datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

import bookings
import checkout as checkout_mod
import payments
import scheduling
import walkins
from db import get_db
from shop_config import ShopConfig

router = APIRouter(prefix="/api/shops/{slug}")


class WalkInRequest(BaseModel):
    service: str
    name: str = Field(min_length=1, max_length=120)
    phone: str = Field(min_length=4, max_length=40)
    technician: Optional[str] = None
    notes: str = Field(default="", max_length=500)


class CheckoutBegin(BaseModel):
    addons: List[str] = Field(default_factory=list)
    tip: float = Field(default=0, ge=0)
    tip_percent: Optional[float] = Field(default=None, ge=0, le=100)


class CheckoutSettle(BaseModel):
    payment_reference: str
    # Square hands back a card token; Stripe/PayPal settle on their own id.
    client_token: str = ""
    addons: List[str] = Field(default_factory=list)
    tip: float = Field(default=0, ge=0)
    tip_percent: Optional[float] = Field(default=None, ge=0, le=100)
    method: str = "card"          # "card" | "cash" — cash still records a ticket


def register(get_shop):
    def _today(cfg: ShopConfig) -> Date:
        from routes_booking import shop_now
        return shop_now(cfg).date()

    async def _techs_on_floor(cfg: ShopConfig, d: Date) -> int:
        dk = scheduling.day_key(d)
        return sum(1 for t in cfg.technicians if t.works_on(dk))

    # ------------------------------------------------------------ check-in ---
    @router.post("/bookings/{reference}/check-in")
    async def check_in(slug: str, reference: str):
        """An appointment arrives."""
        b = await bookings.get(slug, reference)
        if b is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "no booking with that reference")
        if b["status"] == "checked_in":
            return b
        if b["status"] != "booked":
            raise HTTPException(status.HTTP_409_CONFLICT, f"a {b['status']} booking cannot be checked in")
        await get_db()[bookings.COLLECTION].update_one(
            {"shop_slug": slug, "reference": reference.upper()},
            {"$set": {"checked_in_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}},
        )
        return await bookings.set_status(slug, reference, "checked_in")

    @router.post("/queue", status_code=status.HTTP_201_CREATED)
    async def join_queue(slug: str, req: WalkInRequest):
        """A walk-in joins the line and is told where they stand."""
        cfg = await get_shop(slug)
        d = _today(cfg)
        if not cfg.is_open_on(scheduling.day_key(d)):
            raise HTTPException(status.HTTP_409_CONFLICT, "the shop is closed today")
        svc = cfg.service(req.service)
        if svc is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{req.service!r} is not a service this shop offers")
        if req.technician and cfg.technician(req.technician) is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{req.technician!r} is not a technician here")

        ahead = await walkins.waiting(slug, d)
        entry = await walkins.add({
            "shop_slug": slug,
            "reference": bookings.new_reference(),
            "status": walkins.WAITING,
            "date": d.isoformat(),
            "service_id": svc.id,
            "service_name": svc.name,
            "technician_id": req.technician,
            "client": {"name": req.name.strip(), "phone": req.phone.strip(), "notes": req.notes.strip()},
        })
        return {
            **entry,
            "position": len(ahead) + 1,
            "estimated_wait_min": walkins.estimate_wait(cfg, ahead, await _techs_on_floor(cfg, d)),
        }

    @router.get("/queue")
    async def get_queue(slug: str):
        """The line as it stands, with each person's position and estimate."""
        cfg = await get_shop(slug)
        d = _today(cfg)
        line = await walkins.waiting(slug, d)
        on_floor = await _techs_on_floor(cfg, d)
        return {
            "date": d.isoformat(),
            "technicians_on_floor": on_floor,
            "waiting": [
                {**w, "position": i + 1,
                 "estimated_wait_min": walkins.estimate_wait(cfg, line[:i], on_floor)}
                for i, w in enumerate(line)
            ],
        }

    @router.get("/queue/{reference}")
    async def queue_position(slug: str, reference: str):
        """What a waiting client sees on their own phone."""
        cfg = await get_shop(slug)
        d = _today(cfg)
        line = await walkins.waiting(slug, d)
        for i, w in enumerate(line):
            if w["reference"] == reference.upper():
                return {**w, "position": i + 1,
                        "estimated_wait_min": walkins.estimate_wait(cfg, line[:i], await _techs_on_floor(cfg, d))}
        entry = await walkins.get(slug, reference)
        if entry is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "not in today's queue")
        return {**entry, "position": 0, "estimated_wait_min": 0}

    @router.post("/queue/{reference}/seat")
    async def seat_walkin(slug: str, reference: str):
        """Take a walk-in to a chair.

        Converts them into a real booking so checkout, history and the calendar
        only ever deal with one kind of record.
        """
        cfg = await get_shop(slug)
        entry = await walkins.get(slug, reference)
        if entry is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "not in the queue")
        if entry["status"] != walkins.WAITING:
            raise HTTPException(status.HTTP_409_CONFLICT, f"already {entry['status']}")

        d = Date.fromisoformat(entry["date"])
        from routes_booking import shop_now
        now = shop_now(cfg)
        q = scheduling.build_quote(cfg, entry["service_id"])

        tech_id = entry.get("technician_id")
        if not tech_id:
            dk = scheduling.day_key(d)
            free = [t.id for t in cfg.technicians if t.works_on(dk)]
            if not free:
                raise HTTPException(status.HTTP_409_CONFLICT, "no technician is on the floor")
            tech_id = free[0]

        start = scheduling.to_hhmm(now.hour * 60 + now.minute)
        tech = cfg.technician(tech_id)
        b = await bookings.create({
            "shop_slug": slug,
            "reference": entry["reference"],          # same reference the client was given
            "status": "in_service",
            "date": d.isoformat(),
            "start": start,
            "end": scheduling.to_hhmm(scheduling.to_min(start) + q.block_min),
            "technician_id": tech_id,
            "technician_name": tech.name if tech else tech_id,
            "tech_was_chosen": bool(entry.get("technician_id")),
            "client": entry.get("client", {}),
            "quote": q.as_dict(),
            "duration_min": q.duration_min,
            "buffer_min": q.buffer_min,
            "block_min": q.block_min,
            "price": round(q.price, 2),
            "deposit": {"due": 0, "reason": "", "status": "not_required",
                        "refundable_until_hours": cfg.deposit.refundable_until_hours},
            "remind_at": None,
            "source": "walk-in",
        })
        await walkins.set_status(slug, reference, "seated")
        return b

    @router.post("/queue/{reference}/leave")
    async def leave_queue(slug: str, reference: str):
        entry = await walkins.set_status(slug, reference, "left")
        if entry is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "not in the queue")
        return entry

    # ------------------------------------------------------------ checkout ---
    async def _booking_for_checkout(slug: str, reference: str) -> dict:
        b = await bookings.get(slug, reference)
        if b is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "no booking with that reference")
        if b["status"] == "complete":
            raise HTTPException(status.HTTP_409_CONFLICT, "that booking is already checked out")
        if b["status"] == "cancelled":
            raise HTTPException(status.HTTP_409_CONFLICT, "that booking was cancelled")
        return b

    @router.get("/payments/status")
    async def payments_status(slug: str):
        """Whether card payments are actually switched on for this shop, so the
        desk is told the truth instead of shown a card form that cannot work."""
        cfg = await get_shop(slug)
        return {
            "processor": cfg.payments.processor,
            "configured": payments.configured(cfg),
            "sandbox": payments.is_sandbox(cfg.slug, cfg.payments.processor),
            "currency": cfg.payments.currency,
            "tip_presets": cfg.payments.tip_presets,
            "tax_rate": cfg.payments.tax_rate,
        }

    @router.post("/bookings/{reference}/checkout/begin")
    async def checkout_begin(slug: str, reference: str, req: CheckoutBegin):
        """Price the ticket and open a payment with the shop's processor."""
        cfg = await get_shop(slug)
        b = await _booking_for_checkout(slug, reference)
        try:
            ticket = checkout_mod.build_ticket(cfg, b, addon_ids=req.addons,
                                               tip=req.tip, tip_percent=req.tip_percent)
        except ValueError as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))

        out = {"ticket": ticket.as_dict(), "processor": cfg.payments.processor,
               "configured": payments.configured(cfg)}
        if not payments.configured(cfg) or ticket.due_now <= 0:
            return out

        proc = payments.for_shop(cfg)
        try:
            begun = await proc.begin(
                shop_slug=slug, amount=ticket.due_now, currency=ticket.currency,
                reference=b["reference"], description=f"{cfg.name} — {b['quote']['service_name']}",
            )
        except payments.PaymentError as e:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e))
        return {**out, "payment": {"reference": begun.reference, "sandbox": begun.sandbox,
                                   "client": begun.client}}

    @router.post("/bookings/{reference}/checkout/settle")
    async def checkout_settle(slug: str, reference: str, req: CheckoutSettle):
        """Confirm with the provider, then — and only then — mark it complete."""
        cfg = await get_shop(slug)
        b = await _booking_for_checkout(slug, reference)
        try:
            ticket = checkout_mod.build_ticket(cfg, b, addon_ids=req.addons,
                                               tip=req.tip, tip_percent=req.tip_percent)
        except ValueError as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))

        if req.method == "cash":
            payment = {"method": "cash", "paid": True, "amount": ticket.due_now,
                       "currency": ticket.currency, "provider": "cash",
                       "transaction_id": "", "status": "taken_at_counter", "sandbox": False}
        else:
            if not payments.configured(cfg):
                raise HTTPException(status.HTTP_409_CONFLICT,
                                    "card payments are not switched on for this shop")
            proc = payments.for_shop(cfg)
            try:
                settled = await proc.settle(
                    shop_slug=slug, reference=req.payment_reference,
                    amount=ticket.due_now, currency=ticket.currency,
                    client_token=req.client_token,
                )
            except payments.PaymentError as e:
                raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e))
            if not settled.paid:
                raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED,
                                    f"payment not completed ({settled.status})")
            payment = {"method": "card", "paid": True, "amount": settled.amount,
                       "currency": settled.currency, "provider": settled.provider,
                       "transaction_id": settled.transaction_id, "status": settled.status,
                       "sandbox": settled.sandbox}

        receipt = checkout_mod.receipt_for(cfg, b, ticket, payment)
        await get_db()[bookings.COLLECTION].update_one(
            {"shop_slug": slug, "reference": reference.upper()},
            {"$set": {"status": "complete", "receipt": receipt, "payment": payment,
                      "deposit.status": "settled" if (b.get("deposit") or {}).get("due") else
                                        (b.get("deposit") or {}).get("status", "not_required"),
                      "completed_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}},
        )
        return {"booking": await bookings.get(slug, reference), "receipt": receipt}

    @router.get("/bookings/{reference}/receipt")
    async def get_receipt(slug: str, reference: str):
        b = await bookings.get(slug, reference)
        if b is None or not b.get("receipt"):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "no receipt for that reference")
        return b["receipt"]

    return router
