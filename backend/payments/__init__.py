"""The payments layer.

`for_shop(cfg)` returns the processor that shop selected in its config. Nothing
outside this package names a provider, so switching a shop from PayPal to Square
is a one-word config change plus that shop's credentials in the environment.
"""
from __future__ import annotations

from typing import Dict

from shop_config import ShopConfig

from .base import (  # noqa: F401  (re-exported as the package's public surface)
    Begun,
    PaymentError,
    PaymentNotConfigured,
    Processor,
    Settled,
    credential,
    is_sandbox,
)
from .paypal import PayPalProcessor
from .square import SquareProcessor
from .stripe import StripeProcessor

_PROCESSORS: Dict[str, Processor] = {
    "stripe": StripeProcessor(),
    "paypal": PayPalProcessor(),
    "square": SquareProcessor(),
}

SUPPORTED = tuple(_PROCESSORS)


def for_shop(cfg: ShopConfig) -> Processor:
    proc = _PROCESSORS.get(cfg.payments.processor)
    if proc is None:                       # unreachable via the schema; a guard, not a branch
        raise PaymentNotConfigured(f"{cfg.payments.processor!r} is not a supported processor")
    return proc


def configured(cfg: ShopConfig) -> bool:
    """Whether this shop's selected processor actually has its credentials set.

    Lets the UI say "card payments aren't switched on yet" honestly instead of
    presenting a card form that cannot possibly work.
    """
    required = {
        "stripe": ["SECRET_KEY"],
        "paypal": ["CLIENT_ID", "CLIENT_SECRET"],
        "square": ["ACCESS_TOKEN", "APPLICATION_ID", "LOCATION_ID"],
    }[cfg.payments.processor]
    return all(credential(cfg.slug, cfg.payments.processor, f, required=False) for f in required)
