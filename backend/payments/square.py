"""Square — Payments API.

Square tokenises the card in the browser, so there is nothing to create up
front: begin() just hands the Web Payments SDK its application id and location,
and settle() charges the resulting token server-side for the amount the server
computed.

The booking reference is sent as the idempotency key, so a double-tapped
"Take payment" charges once.
"""
from __future__ import annotations

import httpx

from .base import Begun, PaymentError, Settled, credential, from_minor, is_sandbox, to_minor

LIVE = "https://connect.squareup.com"
SANDBOX = "https://connect.squareupsandbox.com"
VERSION = "2025-01-23"


def _base(shop_slug: str) -> str:
    return SANDBOX if is_sandbox(shop_slug, "square") else LIVE


def _headers(shop_slug: str) -> dict:
    return {
        "Authorization": f"Bearer {credential(shop_slug, 'square', 'ACCESS_TOKEN')}",
        "Square-Version": VERSION,
        "Content-Type": "application/json",
    }


class SquareProcessor:
    name = "square"

    async def begin(self, *, shop_slug, amount, currency, reference, description) -> Begun:
        # Validate the credentials now rather than failing at the card form.
        credential(shop_slug, "square", "ACCESS_TOKEN")
        return Begun(
            provider="square",
            reference=reference,
            sandbox=is_sandbox(shop_slug, "square"),
            client={
                "application_id": credential(shop_slug, "square", "APPLICATION_ID"),
                "location_id": credential(shop_slug, "square", "LOCATION_ID"),
                "currency": currency.upper(),
                "amount": amount,
            },
        )

    async def settle(self, *, shop_slug, reference, amount, currency, client_token="") -> Settled:
        if not client_token:
            raise PaymentError("Square needs a card token from the payment form")
        body = {
            "source_id": client_token,
            "idempotency_key": reference[:45],
            "amount_money": {"amount": to_minor(amount, currency), "currency": currency.upper()},
            "location_id": credential(shop_slug, "square", "LOCATION_ID"),
            "note": f"Booking {reference}"[:500],
        }
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(f"{_base(shop_slug)}/v2/payments", headers=_headers(shop_slug), json=body)
        if r.status_code >= 400:
            raise PaymentError(f"Square refused the payment: {_msg(r)}")
        pay = r.json().get("payment", {})
        got = from_minor(int((pay.get("amount_money") or {}).get("amount") or 0), currency)
        status = pay.get("status", "unknown")
        return Settled(
            provider="square",
            paid=status in ("COMPLETED", "APPROVED") and got >= amount - 0.005,
            amount=got,
            currency=((pay.get("amount_money") or {}).get("currency") or currency).upper(),
            transaction_id=pay.get("id", ""),
            status=status,
            sandbox=is_sandbox(shop_slug, "square"),
        )


def _msg(r: httpx.Response) -> str:
    try:
        errs = r.json().get("errors") or []
        return errs[0].get("detail") or errs[0].get("code") or r.text[:200]
    except Exception:
        return r.text[:200]
