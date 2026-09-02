"""One payment interface, three processors behind it.

A shop picks its processor in config; the platform uses whichever is set and the
rest of the codebase never learns which one it is. Credentials are read from the
environment per shop and never appear in a config document, a log line or an API
response (VULN-CRED-01).

Every processor is modelled as two steps, because that is what all three
genuinely need:

  begin()   the server opens a payment for an amount it decided itself, and
            hands back only what the browser needs to collect the card.
  settle()  the browser reports back, and the server asks the PROVIDER what
            actually happened. A client claiming "paid" is never believed.

The amount is always computed server-side from the booking. It is never taken
from the request body, so a tampered client cannot pay $1 for a $131 set.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Optional, Protocol

CURRENCY_MINOR_UNITS = {"JPY": 0, "KRW": 0}   # currencies without cents


def to_minor(amount: float, currency: str) -> int:
    """Money -> the provider's smallest unit. Rounded once, here, so the three
    processors can never disagree by a cent."""
    digits = CURRENCY_MINOR_UNITS.get(currency.upper(), 2)
    return int(round(amount * (10 ** digits)))


def from_minor(amount: int, currency: str) -> float:
    digits = CURRENCY_MINOR_UNITS.get(currency.upper(), 2)
    return amount / (10 ** digits)


class PaymentError(RuntimeError):
    """A processor refused, or is not configured. The message is safe to show a
    member of staff; it never carries a credential."""


class PaymentNotConfigured(PaymentError):
    pass


# ------------------------------------------------------------- credentials ---
def _env_key(shop_slug: str, processor: str, field_name: str) -> str:
    slug = re.sub(r"[^A-Z0-9]+", "_", shop_slug.upper()).strip("_")
    return f"PAY_{slug}_{processor.upper()}_{field_name.upper()}"


def credential(shop_slug: str, processor: str, field_name: str, *, required: bool = True) -> str:
    """Per-shop credential, falling back to a deployment-wide default.

    `PAY_LACQUER_AND_LUME_STRIPE_SECRET_KEY` wins; `PAY_STRIPE_SECRET_KEY` is the
    fallback so a single-shop deployment does not have to repeat its slug.
    """
    specific = os.environ.get(_env_key(shop_slug, processor, field_name), "").strip()
    if specific:
        return specific
    shared = os.environ.get(f"PAY_{processor.upper()}_{field_name.upper()}", "").strip()
    if shared:
        return shared
    if required:
        raise PaymentNotConfigured(
            f"{processor} is selected for this shop but its credentials are not set "
            f"(expected {_env_key(shop_slug, processor, field_name)})"
        )
    return ""


def is_sandbox(shop_slug: str, processor: str) -> bool:
    """Sandbox unless a deployment explicitly says live. Defaulting to sandbox
    means a misconfigured deployment cannot silently take real money."""
    raw = credential(shop_slug, processor, "ENV", required=False).lower()
    return raw not in ("live", "production", "prod")


# --------------------------------------------------------------- contracts ---
@dataclass
class Begun:
    """What the browser needs to collect a card. Never a secret key — only
    publishable identifiers the provider intends to be public."""
    provider: str
    reference: str                       # provider-side id we later settle against
    sandbox: bool
    client: dict = field(default_factory=dict)


@dataclass
class Settled:
    provider: str
    paid: bool
    amount: float
    currency: str
    transaction_id: str
    status: str
    sandbox: bool = True


class Processor(Protocol):
    name: str

    async def begin(self, *, shop_slug: str, amount: float, currency: str, reference: str,
                    description: str) -> Begun: ...

    async def settle(self, *, shop_slug: str, reference: str, amount: float,
                     currency: str, client_token: str = "") -> Settled: ...
