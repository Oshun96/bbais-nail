"""Quoting and availability — the scheduling intelligence a nail shop actually needs.

Two ideas carry the whole module:

1. **A booking occupies more chair time than the client is "in" for.** Acrylic
   cures, polish dries, the station gets reset. Every service carries a buffer,
   and specialty shapes/lengths/finishes add their own minutes on top. The
   calendar reserves `block_min`, never `duration_min` — that is what stops a
   colour set landing on top of an acrylic full set.

2. **All schedule maths is done in the shop's own local clock.** A salon's day is
   inherently local, so slots are computed as naive local times and stored as a
   local date plus "HH:MM". No timezone conversion anywhere means no timezone bugs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as Date, datetime, timedelta
from typing import Dict, Iterable, List, Optional, Sequence

from shop_config import DAYS, ShopConfig

OPTION_KINDS = ("shapes", "lengths", "finishes")


def day_key(d: Date) -> str:
    """Monday-first day key, matching the config's hours/schedule keys."""
    return DAYS[d.weekday()]


def to_min(hhmm: str) -> int:
    h, _, m = hhmm.partition(":")
    return int(h) * 60 + int(m)


def to_hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


# ------------------------------------------------------------------- quote ---
@dataclass
class LineItem:
    label: str
    detail: str
    amount: float
    minutes: int = 0


@dataclass
class Quote:
    service_id: str
    service_name: str
    category: str
    duration_min: int          # time the client is in the chair
    buffer_min: int            # processing/reset time held after
    price: float
    lines: List[LineItem] = field(default_factory=list)
    options: Dict[str, str] = field(default_factory=dict)
    colour_id: Optional[str] = None
    deposit_due: float = 0.0
    deposit_reason: str = ""

    @property
    def block_min(self) -> int:
        """What the calendar reserves."""
        return self.duration_min + self.buffer_min

    def as_dict(self) -> dict:
        return {
            "service_id": self.service_id,
            "service_name": self.service_name,
            "category": self.category,
            "duration_min": self.duration_min,
            "buffer_min": self.buffer_min,
            "block_min": self.block_min,
            "price": round(self.price, 2),
            "deposit_due": round(self.deposit_due, 2),
            "deposit_reason": self.deposit_reason,
            "options": self.options,
            "colour_id": self.colour_id,
            "lines": [
                {"label": li.label, "detail": li.detail,
                 "amount": round(li.amount, 2), "minutes": li.minutes}
                for li in self.lines
            ],
        }


class QuoteError(ValueError):
    """A selection the shop's own config does not offer."""


def build_quote(
    cfg: ShopConfig,
    service_id: str,
    *,
    shape: Optional[str] = None,
    length: Optional[str] = None,
    finish: Optional[str] = None,
    colour: Optional[str] = None,
) -> Quote:
    """Price and time a selection from the shop's config alone.

    Every surcharge and every added minute is traceable to a config entry, so a
    shop changes its pricing by editing its config and nothing else.
    """
    svc = cfg.service(service_id)
    if svc is None:
        raise QuoteError(f"{service_id!r} is not a service this shop offers")

    q = Quote(
        service_id=svc.id,
        service_name=svc.name,
        category=svc.category,
        duration_min=svc.duration_min,
        buffer_min=svc.buffer_min,
        price=svc.price,
    )
    q.lines.append(LineItem(svc.name, f"{svc.duration_min} min in the chair", svc.price, svc.duration_min))

    for kind, chosen in (("shapes", shape), ("lengths", length), ("finishes", finish)):
        if not chosen:
            continue
        opt = cfg.nail_menu.option(kind, chosen)
        if opt is None:
            raise QuoteError(f"{chosen!r} is not on this shop's {kind} menu")
        q.options[kind[:-1]] = opt.id          # shapes -> shape
        q.price += opt.surcharge
        q.duration_min += opt.extra_min
        if opt.surcharge or opt.extra_min:
            q.lines.append(LineItem(
                opt.label,
                kind[:-1].title() + (f" · +{opt.extra_min} min" if opt.extra_min else ""),
                opt.surcharge,
                opt.extra_min,
            ))

    if colour:
        col = cfg.colour(colour)
        if col is None:
            raise QuoteError(f"{colour!r} is not on this shop's colour menu")
        q.colour_id = col.id

    q.deposit_due, q.deposit_reason = deposit_for(cfg, q)
    return q


def deposit_for(cfg: ShopConfig, q: Quote) -> tuple[float, str]:
    """Deposit owed on this quote, per the shop's rules.

    A service may force or waive a deposit itself (`deposit_required`); otherwise
    the shop rules decide, gated on the booked block and optionally on category.
    """
    rules = cfg.deposit
    svc = cfg.service(q.service_id)
    forced = svc.deposit_required if svc else None

    if forced is False:
        return 0.0, ""
    if not rules.enabled and not forced:
        return 0.0, ""

    if forced is not True:
        if q.block_min < rules.applies_over_min:
            return 0.0, ""
        if rules.applies_to_categories and q.category not in rules.applies_to_categories:
            return 0.0, ""

    amount = q.price * (rules.amount / 100.0) if rules.kind == "percent" else rules.amount
    amount = max(amount, rules.min_amount)
    amount = min(amount, q.price)          # never hold more than the service costs
    reason = (
        f"{rules.amount:g}% of {q.price:g}" if rules.kind == "percent"
        else f"flat {rules.amount:g}"
    )
    return round(amount, 2), reason


# -------------------------------------------------------------- availability ---
@dataclass
class Busy:
    """An occupied stretch of one tech's day, in local minutes from midnight."""
    tech_id: str
    start: int
    end: int


def busy_from_bookings(bookings: Iterable[dict]) -> List[Busy]:
    out: List[Busy] = []
    for b in bookings:
        if b.get("status") == "cancelled":
            continue
        start = to_min(b["start"])
        out.append(Busy(b["technician_id"], start, start + int(b["block_min"])))
    return out


def working_window(cfg: ShopConfig, tech_id: str, d: Date) -> Optional[tuple[int, int]]:
    """The minutes a tech can actually take work on a date: their shift clipped
    to the shop's own opening hours. Returns None if either is closed/off."""
    dk = day_key(d)
    hours = cfg.hours.get(dk)
    if not hours or hours.closed:
        return None
    tech = cfg.technician(tech_id)
    if tech is None or not tech.works_on(dk):
        return None
    shift = tech.schedule[dk]
    start = max(to_min(hours.open), to_min(shift.start))
    end = min(to_min(hours.close), to_min(shift.end))
    return (start, end) if end > start else None


def slots_for_tech(
    cfg: ShopConfig,
    tech_id: str,
    d: Date,
    block_min: int,
    busy: Sequence[Busy],
    *,
    now: Optional[datetime] = None,
) -> List[str]:
    """Every start time this tech could take a `block_min` job on this date.

    The whole block must fit inside the working window and must not overlap
    anything already on that tech's book — which is why the buffer matters: a
    90-minute set with 15 minutes of cure time blocks 105.
    """
    window = working_window(cfg, tech_id, d)
    if window is None:
        return []
    open_min, close_min = window
    step = cfg.booking.slot_granularity_min
    mine = [b for b in busy if b.tech_id == tech_id]

    earliest = open_min
    if now is not None and d == now.date():
        # Today's book closes `min_lead_min` out, rounded up to the next slot.
        cutoff = now.hour * 60 + now.minute + cfg.booking.min_lead_min
        earliest = max(earliest, -(-cutoff // step) * step)

    out: List[str] = []
    t = -(-earliest // step) * step          # align to the grid
    while t + block_min <= close_min:
        if not any(t < b.end and b.start < t + block_min for b in mine):
            out.append(to_hhmm(t))
        t += step
    return out


def availability(
    cfg: ShopConfig,
    d: Date,
    block_min: int,
    busy: Sequence[Busy],
    *,
    tech_id: Optional[str] = None,
    now: Optional[datetime] = None,
) -> Dict[str, List[str]]:
    """Slots per technician. `tech_id=None` means "no preference" — every tech
    who can do it, which the caller merges into one list for the client."""
    techs = [cfg.technician(tech_id)] if tech_id else [t for t in cfg.technicians if t.active]
    result: Dict[str, List[str]] = {}
    for t in techs:
        if t is None:
            continue
        s = slots_for_tech(cfg, t.id, d, block_min, busy, now=now)
        if s:
            result[t.id] = s
    return result


def merge_slots(per_tech: Dict[str, List[str]]) -> List[str]:
    return sorted({s for slots in per_tech.values() for s in slots})


def bookable_range(cfg: ShopConfig, today: Date) -> tuple[Date, Date]:
    return today, today + timedelta(days=cfg.booking.max_days_ahead)


def reminder_at(cfg: ShopConfig, d: Date, start: str, block_min: int) -> Optional[str]:
    """When a reminder should go out, or None if this booking is too short to
    warrant one. Stored on the booking so delivery is a separate concern."""
    if block_min < cfg.booking.remind_over_min or not cfg.booking.remind_hours_before:
        return None
    when = datetime.combine(d, datetime.min.time()) + timedelta(minutes=to_min(start))
    return (when - timedelta(hours=cfg.booking.remind_hours_before)).isoformat(timespec="minutes")
