"""PayPal — Orders v2.

begin()  creates an order for the server-computed amount and returns the order
         id plus the client id the PayPal Buttons SDK needs.
settle() CAPTURES the order server-side. The browser approving an order is not
         payment; only a capture that PayPal reports as COMPLETED is.
"""
from __future__ import annotations

import httpx

from .base import Begun, PaymentError, Settled, credential, is_sandbox

LIVE = "https://api-m.paypal.com"
SANDBOX = "https://api-m.sandbox.paypal.com"


def _base(shop_slug: str) -> str:
    return SANDBOX if is_sandbox(shop_slug, "paypal") else LIVE


async def _token(client: httpx.AsyncClient, shop_slug: str) -> str:
    cid = credential(shop_slug, "paypal", "CLIENT_ID")
    secret = credential(shop_slug, "paypal", "CLIENT_SECRET")
    r = await client.post(
        f"{_base(shop_slug)}/v1/oauth2/token",
        data={"grant_type": "client_credentials"},
        auth=(cid, secret),
        headers={"Accept": "application/json"},
    )
    if r.status_code >= 400:
        raise PaymentError(f"PayPal rejected the shop's credentials: {_msg(r)}")
    return r.json()["access_token"]


class PayPalProcessor:
    name = "paypal"

    async def begin(self, *, shop_slug, amount, currency, reference, description) -> Begun:
        async with httpx.AsyncClient(timeout=30) as c:
            tok = await _token(c, shop_slug)
            r = await c.post(
                f"{_base(shop_slug)}/v2/checkout/orders",
                headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
                json={
                    "intent": "CAPTURE",
                    "purchase_units": [{
                        "reference_id": reference,
                        "description": description[:127],
                        "amount": {"currency_code": currency.upper(), "value": f"{amount:.2f}"},
                    }],
                },
            )
        if r.status_code >= 400:
            raise PaymentError(f"PayPal refused the order: {_msg(r)}")
        order = r.json()
        return Begun(
            provider="paypal",
            reference=order["id"],
            sandbox=is_sandbox(shop_slug, "paypal"),
            client={"client_id": credential(shop_slug, "paypal", "CLIENT_ID"),
                    "order_id": order["id"],
                    "currency": currency.upper()},
        )

    async def settle(self, *, shop_slug, reference, amount, currency, client_token="") -> Settled:
        async with httpx.AsyncClient(timeout=30) as c:
            tok = await _token(c, shop_slug)
            hdrs = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
            r = await c.post(f"{_base(shop_slug)}/v2/checkout/orders/{reference}/capture",
                             headers=hdrs, json={})
            # An order captured already (double submit, retry) is not an error —
            # read its real state rather than reporting a false failure.
            if r.status_code == 422 and "ORDER_ALREADY_CAPTURED" in r.text:
                r = await c.get(f"{_base(shop_slug)}/v2/checkout/orders/{reference}", headers=hdrs)

        if r.status_code >= 400:
            raise PaymentError(f"PayPal could not capture the payment: {_msg(r)}")

        order = r.json()
        cap = {}
        for unit in order.get("purchase_units", []):
            caps = (unit.get("payments") or {}).get("captures") or []
            if caps:
                cap = caps[0]
                break
        got = float((cap.get("amount") or {}).get("value") or 0)
        status = cap.get("status") or order.get("status", "unknown")
        return Settled(
            provider="paypal",
            paid=status == "COMPLETED" and got >= amount - 0.005,
            amount=got,
            currency=((cap.get("amount") or {}).get("currency_code") or currency).upper(),
            transaction_id=cap.get("id", order.get("id", "")),
            status=status,
            sandbox=is_sandbox(shop_slug, "paypal"),
        )


def _msg(r: httpx.Response) -> str:
    try:
        j = r.json()
        d = (j.get("details") or [{}])[0]
        return d.get("description") or j.get("message") or r.text[:200]
    except Exception:
        return r.text[:200]
