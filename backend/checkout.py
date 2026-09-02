"""Ringing up a ticket.

All money is computed here, server-side, from the shop's config and the booking
that already exists. The client sends a tip choice and nothing else that touches
the total — never the amount to charge.

A deposit already owed on the booking is credited against the total rather than
charged twice, which is the whole point of taking one.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from shop_config import ShopConfig


@dataclass
class TicketLine:
    label: str
    detail: str
    amount: float


@dataclass
class Ticket:
    currency: str
    lines: List[TicketLine] = field(default_factory=list)
    subtotal: float = 0.0
    tax: float = 0.0
    tip: float = 0.0
    deposit_credit: float = 0.0
    total: float = 0.0
    due_now: float = 0.0

    def as_dict(self) -> dict:
        return {
            "currency": self.currency,
            "lines": [{"label": l.label, "detail": l.detail, "amount": round(l.amount, 2)} for l in self.lines],
            "subtotal": round(self.subtotal, 2),
            "tax": round(self.tax, 2),
            "tip": round(self.tip, 2),
            "deposit_credit": round(self.deposit_credit, 2),
            "total": round(self.total, 2),
            "due_now": round(self.due_now, 2),
        }


def build_ticket(
    cfg: ShopConfig,
    booking: dict,
    *,
    addon_ids: Optional[List[str]] = None,
    tip: float = 0.0,
    tip_percent: Optional[float] = None,
) -> Ticket:
    """The ticket for a booking: what was quoted, plus anything added at the
    chair, plus tax and tip, minus a deposit already taken."""
    t = Ticket(currency=cfg.payments.currency)

    for line in booking.get("quote", {}).get("lines", []):
        t.lines.append(TicketLine(line["label"], line.get("detail", ""), float(line["amount"])))

    for aid in addon_ids or []:
        svc = cfg.service(aid)
        if svc is None:
            raise ValueError(f"{aid!r} is not a service this shop offers")
        t.lines.append(TicketLine(svc.name, "Added at the chair", svc.price))

    t.subtotal = sum(l.amount for l in t.lines)
    t.tax = round(t.subtotal * cfg.payments.tax_rate, 2)

    # Tip is conventionally on the service, before tax.
    if tip_percent is not None:
        t.tip = round(t.subtotal * (tip_percent / 100.0), 2)
    else:
        t.tip = round(max(0.0, tip), 2)

    t.total = round(t.subtotal + t.tax + t.tip, 2)

    dep = booking.get("deposit") or {}
    if dep.get("status") == "paid":
        t.deposit_credit = round(float(dep.get("due") or 0), 2)

    t.due_now = round(max(0.0, t.total - t.deposit_credit), 2)
    return t


def receipt_for(cfg: ShopConfig, booking: dict, ticket: Ticket, payment: dict) -> dict:
    """A receipt is a record of what happened, not a rendering concern — the
    same object backs the on-screen receipt, an emailed copy and the admin's
    history view."""
    return {
        "shop": {"name": cfg.name, "address": cfg.address.one_line(), "phone": cfg.contact.phone},
        "reference": booking["reference"],
        "date": booking["date"],
        "start": booking["start"],
        "client": booking.get("client", {}).get("name", ""),
        "technician": booking.get("technician_name", ""),
        "ticket": ticket.as_dict(),
        "payment": payment,
    }
