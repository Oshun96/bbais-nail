"""BBAIS Nail Platform — API.

Phase 1 surface: the shop-config engine that every later phase reads through.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")  # before anything reads the environment

from fastapi import APIRouter, Depends, FastAPI, HTTPException, status  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

import bookings  # noqa: E402
import db  # noqa: E402
import routes_booking  # noqa: E402
import clients  # noqa: E402
import reviews  # noqa: E402
import routes_admin  # noqa: E402
import routes_agent  # noqa: E402
import routes_consult  # noqa: E402
import routes_desk  # noqa: E402
import walkins  # noqa: E402
import shop_store  # noqa: E402
from security import (  # noqa: E402
    BodySizeLimitMiddleware,
    SecurityHeadersMiddleware,
    cors_origins,
    require_admin,
)
from shop_config import DAY_LABELS, DAYS, ShopConfig  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.ping()
    written = await shop_store.seed_shops()
    await bookings.ensure_indexes()
    await walkins.ensure_indexes()
    await clients.ensure_indexes()
    await reviews.ensure_indexes()
    await routes_agent.ensure_indexes()
    print(f"[bbais-nail] db ok; seeded shops: {written or 'none (already current)'}")
    yield
    await db.close()


app = FastAPI(title="BBAIS Nail Platform", version="0.1.0", lifespan=lifespan)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(BodySizeLimitMiddleware)
origins = cors_origins()
if origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        # PUT belongs here: the admin panel saves client records and whole shop
        # configs with it. Omitting it only shows up in production, because the
        # dev proxy makes the same calls same-origin and skips preflight entirely.
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-Admin-Key"],
    )

api = APIRouter(prefix="/api")


@api.get("/health")
async def health():
    await db.ping()
    return {"ok": True, "service": "bbais-nail", "phase": 1}


@api.get("/shops")
async def shops():
    """Every shop this deployment can serve, plus which one is the default."""
    return {"default": shop_store.default_slug(), "shops": await shop_store.list_shops()}


async def _load(slug: str) -> ShopConfig:
    cfg = await shop_store.get_shop(slug)
    if cfg is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no shop configured for {slug!r}")
    return cfg


@api.get("/shops/{slug}/config")
async def shop_config(slug: str):
    """THE white-label payload. The entire front end themes and populates itself
    from this one response — brand, hours, services, techs, menus, colours,
    deposit rules and the agent's voice."""
    cfg = await _load(slug)
    return {
        **cfg.model_dump(mode="json"),
        # Derived, so every client renders hours and prices identically instead of
        # each one reinventing the formatting.
        "derived": {
            "day_order": list(DAYS),
            "day_labels": DAY_LABELS,
            "address_one_line": cfg.address.one_line(),
            "open_days": [d for d in DAYS if cfg.is_open_on(d)],
            "categories": list(dict.fromkeys(s.category for s in cfg.services if s.active)),
            "colour_families": list(dict.fromkeys(c.family for c in cfg.colours if c.active)),
            "price_from": min((s.price for s in cfg.services if s.active and not s.addon), default=0),
            "service_block_min": {s.id: s.block_min for s in cfg.services if s.active},
        },
    }


@api.put("/shops/{slug}/config", dependencies=[Depends(require_admin)])
async def update_shop_config(slug: str, payload: ShopConfig):
    """Admin-only (VULN-AUTH-01). Validated through the same schema as a seed
    file, so a bad edit is rejected before it can reach the storefront."""
    if payload.slug != slug:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "slug in body must match the URL")
    await _load(slug)
    return (await shop_store.save_shop(payload)).model_dump(mode="json")


app.include_router(api)
app.include_router(routes_booking.register(_load))
app.include_router(routes_desk.register(_load))
_admin_router, _public_reviews = routes_admin.register(_load)
app.include_router(_admin_router)
app.include_router(_public_reviews)
app.include_router(routes_agent.register(_load))
app.include_router(routes_consult.register(_load))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
