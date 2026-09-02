"""
BBAIS Nail Platform — the per-shop configuration schema.

This module IS the white-label engine. Everything a shop differs on lives here:
brand, hours, service menu, technicians, nail menus, colour menu, deposit rules
and the front-desk agent's voice. A new shop is a config document, never a build.

Nothing environment-dependent is hardcoded (0-hardcode rule): URLs, keys and
credentials are read from the environment by the modules that need them, never
stored in a shop config.
"""
from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
DAY_LABELS = {
    "mon": "Monday", "tue": "Tuesday", "wed": "Wednesday", "thu": "Thursday",
    "fri": "Friday", "sat": "Saturday", "sun": "Sunday",
}


def _check_hex(v: Optional[str]) -> Optional[str]:
    if v in (None, ""):
        return v
    body = v[1:]
    if not (v.startswith("#") and len(v) in (4, 7) and all(c in "0123456789abcdefABCDEF" for c in body)):
        raise ValueError(f"colour must be #rgb or #rrggbb, got {v!r}")
    return v


def _check_hhmm(v: str) -> str:
    hh, sep, mm = v.partition(":")
    if not (sep and hh.isdigit() and mm.isdigit() and 0 <= int(hh) <= 23 and 0 <= int(mm) <= 59):
        raise ValueError(f"time must be 24h HH:MM, got {v!r}")
    return f"{int(hh):02d}:{int(mm):02d}"


def _luma(v: str) -> float:
    h = v.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


# ---------------------------------------------------------------- identity ---
class Address(BaseModel):
    line1: str = ""
    line2: str = ""
    city: str = ""
    state: str = ""
    postal_code: str = ""
    country: str = "US"

    def one_line(self) -> str:
        return ", ".join(p for p in (self.line1, self.line2, self.city, self.state, self.postal_code) if p)


class Contact(BaseModel):
    phone: str = ""
    email: str = ""
    instagram: str = ""
    booking_note: str = ""


class DayHours(BaseModel):
    """A single day. `closed` wins over open/close, so a closed day can keep its
    historical times on file without ever becoming bookable."""
    closed: bool = False
    open: str = "09:00"      # 24h "HH:MM" — the only time format used platform-wide
    close: str = "19:00"

    @field_validator("open", "close")
    @classmethod
    def _hhmm(cls, v: str) -> str:
        return _check_hhmm(v)


# ------------------------------------------------------------------- theme ---
class Theme(BaseModel):
    """BBAIS dark-luxe is the default. A shop overrides accent colour and logo;
    the dark base is never overridden to white — no white backgrounds ever."""
    base: str = "#000000"
    surface: str = "#080808"
    surface_raised: str = "#101010"
    line: str = "#1E1E1E"
    gold: str = "#D4AF37"
    rose_gold: str = "#B76E79"
    text: str = "#F5F1E8"
    muted: str = "#A39B8B"
    accent: Optional[str] = None            # per-shop brand colour override
    heading_font: str = "Cormorant Garamond"
    body_font: str = "DM Sans"
    logo_url: str = ""
    logo_mark: str = ""                     # monogram fallback when no logo file

    @field_validator("base", "surface", "surface_raised", "line", "gold",
                     "rose_gold", "text", "muted", "accent")
    @classmethod
    def _hex(cls, v):
        return _check_hex(v)

    @field_validator("base", "surface")
    @classmethod
    def _never_light(cls, v: str) -> str:
        """A guardrail, not decoration: dark-luxe forbids a light base, so a shop
        config physically cannot ship a white background."""
        if _luma(v) > 60:
            raise ValueError(f"base/surface must stay dark (no white backgrounds): {v!r}")
        return v


# ---------------------------------------------------------------- services ---
class Service(BaseModel):
    id: str
    name: str
    category: str = "Nails"
    description: str = ""
    duration_min: int = Field(60, gt=0)
    # Processing / buffer time: acrylic cures, polish dries, the station is reset.
    # The scheduler holds this AFTER the service so the tech is not double-booked.
    buffer_min: int = Field(0, ge=0)
    price: float = Field(0, ge=0)
    is_fill: bool = False                   # fills: separate, cheaper, shorter than full sets
    # An add-on is bought alongside a service, never on its own. Flagged rather
    # than inferred from the category name, so "from" pricing never advertises a
    # $12 nail repair as the entry price for a full set.
    addon: bool = False
    deposit_required: Optional[bool] = None  # None => fall back to the shop deposit rules
    active: bool = True

    @property
    def block_min(self) -> int:
        """Total chair time the calendar must reserve."""
        return self.duration_min + self.buffer_min


class TechDay(BaseModel):
    off: bool = False
    start: str = "09:00"
    end: str = "19:00"

    @field_validator("start", "end")
    @classmethod
    def _hhmm(cls, v: str) -> str:
        return _check_hhmm(v)


class Technician(BaseModel):
    id: str
    name: str
    title: str = "Nail Technician"
    bio: str = ""
    photo_url: str = ""
    specialties: List[str] = Field(default_factory=list)
    schedule: Dict[str, TechDay] = Field(default_factory=dict)
    active: bool = True

    def works_on(self, day: str) -> bool:
        d = self.schedule.get(day)
        return bool(self.active and d and not d.off)


# --------------------------------------------------------------- nail menus ---
class MenuOption(BaseModel):
    """One shape / length / finish. `surcharge` is added to the service price and
    `extra_min` to its duration — specialty work costs more AND takes longer."""
    id: str
    label: str
    description: str = ""
    surcharge: float = Field(0, ge=0)
    extra_min: int = Field(0, ge=0)
    active: bool = True


class NailMenu(BaseModel):
    shapes: List[MenuOption] = Field(default_factory=list)
    lengths: List[MenuOption] = Field(default_factory=list)
    finishes: List[MenuOption] = Field(default_factory=list)

    def option(self, kind: str, oid: str) -> Optional[MenuOption]:
        return next((o for o in getattr(self, kind, []) if o.id == oid and o.active), None)


class Colour(BaseModel):
    id: str
    name: str
    hex: str
    family: str = ""                        # nude / red / pink / dark / brights ...
    finish: str = "glossy"
    active: bool = True

    @field_validator("hex")
    @classmethod
    def _hex(cls, v: str) -> str:
        return _check_hex(v)


# -------------------------------------------------------- deposits & agent ----
class DepositRules(BaseModel):
    enabled: bool = True
    kind: Literal["percent", "fixed"] = "percent"
    amount: float = Field(25, ge=0)          # 25 => 25% when kind == "percent"
    min_amount: float = Field(10, ge=0)
    # Long sets are where no-shows actually hurt: deposit anything at/over this block.
    applies_over_min: int = Field(60, ge=0)
    applies_to_categories: List[str] = Field(default_factory=list)   # empty => all
    refundable_until_hours: int = Field(24, ge=0)
    policy_text: str = ""


class BookingRules(BaseModel):
    """How this shop takes appointments. Shops genuinely differ here — a walk-in
    lounge books on 15-minute marks an hour out, a studio books on the half hour
    a day out — so it is config, not a constant."""
    slot_granularity_min: int = Field(15, gt=0)
    # How soon before an appointment the book closes.
    min_lead_min: int = Field(60, ge=0)
    max_days_ahead: int = Field(90, gt=0)
    # Sets at/over this length get a reminder — long sets are where no-shows hurt.
    remind_over_min: int = Field(60, ge=0)
    remind_hours_before: int = Field(24, ge=0)


class AgentPersona(BaseModel):
    """The front-desk agent's voice. It speaks AS the shop — never as a model,
    never with an engine or infrastructure name."""
    name: str = "Front Desk"
    tone: str = "warm, precise, unhurried"
    persona: str = ""
    greeting: str = ""
    signoff: str = ""
    escalation_phone: str = ""


class PaymentsConfig(BaseModel):
    """Which processor this shop uses. Credentials NEVER live here — they are read
    from the environment per shop (VULN-CRED-01)."""
    processor: Literal["paypal", "stripe", "square"] = "paypal"
    currency: str = "USD"
    tax_rate: float = Field(0, ge=0)         # 0.08875 => 8.875%
    tip_presets: List[int] = Field(default_factory=lambda: [18, 20, 25])


class SeoConfig(BaseModel):
    title: str = ""
    description: str = ""
    keywords: List[str] = Field(default_factory=list)
    price_range: str = "$$"


# -------------------------------------------------------------- the config ----
class ShopConfig(BaseModel):
    slug: str
    name: str
    tagline: str = ""
    about: str = ""
    timezone: str = "America/New_York"
    address: Address = Field(default_factory=Address)
    contact: Contact = Field(default_factory=Contact)
    hours: Dict[str, DayHours] = Field(default_factory=dict)
    theme: Theme = Field(default_factory=Theme)
    services: List[Service] = Field(default_factory=list)
    technicians: List[Technician] = Field(default_factory=list)
    nail_menu: NailMenu = Field(default_factory=NailMenu)
    colours: List[Colour] = Field(default_factory=list)
    deposit: DepositRules = Field(default_factory=DepositRules)
    booking: BookingRules = Field(default_factory=BookingRules)
    agent: AgentPersona = Field(default_factory=AgentPersona)
    payments: PaymentsConfig = Field(default_factory=PaymentsConfig)
    seo: SeoConfig = Field(default_factory=SeoConfig)

    @field_validator("slug")
    @classmethod
    def _slug(cls, v: str) -> str:
        s = v.strip().lower()
        if not s or not all(c.isalnum() or c == "-" for c in s):
            raise ValueError(f"slug must be lowercase alphanumeric/dashes, got {v!r}")
        return s

    @field_validator("hours")
    @classmethod
    def _all_days(cls, v: Dict[str, DayHours]) -> Dict[str, DayHours]:
        unknown = set(v) - set(DAYS)
        if unknown:
            raise ValueError(f"unknown day key(s): {sorted(unknown)}")
        # A missing day is a closed day, so hours are always total and ordered.
        return {d: v.get(d, DayHours(closed=True)) for d in DAYS}

    # -- lookups the rest of the platform reads through ------------------------
    def service(self, sid: str) -> Optional[Service]:
        return next((s for s in self.services if s.id == sid and s.active), None)

    def technician(self, tid: str) -> Optional[Technician]:
        return next((t for t in self.technicians if t.id == tid and t.active), None)

    def colour(self, cid: str) -> Optional[Colour]:
        return next((c for c in self.colours if c.id == cid and c.active), None)

    def is_open_on(self, day: str) -> bool:
        h = self.hours.get(day)
        return bool(h and not h.closed)
