"""Stripe — PaymentIntents.

begin()  creates a PaymentIntent for the server-computed amount and returns the
         client secret plus the publishable key, which is all Stripe.js needs.
settle() re-reads the intent FROM STRIPE and only reports paid when Stripe says
         `succeeded` for the amount we asked for.
"""
from __future__ import annotations

import httpx

from .base import Begun, PaymentError, Settled, credential, from_minor, is_sandbox, to_minor

API = "https://api.stripe.com/v1"


class StripeProcessor:
    name = "stripe"

    async def begin(self, *, shop_slug, amount, currency, reference, description) -> Begun:
        secret = credential(shop_slug, "stripe", "SECRET_KEY")
        publishable = credential(shop_slug, "stripe", "PUBLISHABLE_KEY", required=False)
        data = {
            "amount": str(to_minor(amount, currency)),
            "currency": currency.lower(),
            "description": description,
            "metadata[reference]": reference,
            "metadata[shop]": shop_slug,
            "automatic_payment_methods[enabled]": "true",
        }
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(f"{API}/payment_intents", data=data, auth=(secret, ""))
        if r.status_code >= 400:
            raise PaymentError(f"Stripe refused the payment: {_msg(r)}")
        pi = r.json()
        return Begun(
            provider="stripe",
            reference=pi["id"],
            sandbox=secret.startswith("sk_test_") or is_sandbox(shop_slug, "stripe"),
            client={"publishable_key": publishable, "client_secret": pi["client_secret"]},
        )

    async def settle(self, *, shop_slug, reference, amount, currency, client_token="") -> Settled:
        secret = credential(shop_slug, "stripe", "SECRET_KEY")
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get(f"{API}/payment_intents/{reference}", auth=(secret, ""))
        if r.status_code >= 400:
            raise PaymentError(f"Stripe could not confirm the payment: {_msg(r)}")
        pi = r.json()
        received = from_minor(int(pi.get("amount_received") or 0), currency)
        return Settled(
            provider="stripe",
            paid=pi.get("status") == "succeeded" and received >= amount - 0.005,
            amount=received,
            currency=(pi.get("currency") or currency).upper(),
            transaction_id=pi.get("id", ""),
            status=pi.get("status", "unknown"),
            sandbox=not pi.get("livemode", False),
        )


def _msg(r: httpx.Response) -> str:
    try:
        return r.json().get("error", {}).get("message", r.text[:200])
    except Exception:
        return r.text[:200]
