"""Loading, seeding and serving shop configs.

`backend/shops/*.json` are the seed configs shipped with the platform. On boot
they are upserted into Mongo, which is then the live store — so the Phase 4 admin
panel can edit a shop without touching the repo. Seeding never clobbers a shop
that has already been edited live: a seed only writes when the shop is absent, or
when its seed file has actually changed since it was last seeded.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Dict, List, Optional

from shop_config import ShopConfig
from db import get_db

SHOPS_DIR = Path(__file__).parent / "shops"
COLLECTION = "shops"


def _digest(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def load_seed_files() -> Dict[str, tuple[ShopConfig, str]]:
    """Parse and VALIDATE every seed file. A malformed shop config fails loudly
    here rather than silently serving a half-themed platform."""
    out: Dict[str, tuple[ShopConfig, str]] = {}
    for path in sorted(SHOPS_DIR.glob("*.json")):
        raw = path.read_text(encoding="utf-8")
        try:
            cfg = ShopConfig.model_validate(json.loads(raw))
        except Exception as exc:
            raise RuntimeError(f"invalid shop config {path.name}: {exc}") from exc
        if cfg.slug != path.stem:
            raise RuntimeError(f"{path.name}: slug {cfg.slug!r} must match the filename")
        out[cfg.slug] = (cfg, _digest(raw))
    return out


async def seed_shops() -> List[str]:
    """Upsert seed configs into Mongo. Returns the slugs actually written."""
    db = get_db()
    await db[COLLECTION].create_index("slug", unique=True)
    written: List[str] = []
    for slug, (cfg, digest) in load_seed_files().items():
        existing = await db[COLLECTION].find_one({"slug": slug}, {"_seed_digest": 1, "_edited": 1})
        if existing and (existing.get("_edited") or existing.get("_seed_digest") == digest):
            continue
        doc = cfg.model_dump(mode="json")
        doc["_seed_digest"] = digest
        await db[COLLECTION].replace_one({"slug": slug}, doc, upsert=True)
        written.append(slug)
    return written


async def list_shops() -> List[dict]:
    db = get_db()
    cur = db[COLLECTION].find({}, {"_id": 0, "slug": 1, "name": 1, "tagline": 1, "theme": 1})
    return [
        {
            "slug": d["slug"],
            "name": d["name"],
            "tagline": d.get("tagline", ""),
            "accent": (d.get("theme") or {}).get("accent") or (d.get("theme") or {}).get("gold"),
            "logo_mark": (d.get("theme") or {}).get("logo_mark", ""),
        }
        async for d in cur
    ]


async def get_shop(slug: str) -> Optional[ShopConfig]:
    doc = await get_db()[COLLECTION].find_one({"slug": slug}, {"_id": 0, "_seed_digest": 0, "_edited": 0})
    return ShopConfig.model_validate(doc) if doc else None


async def save_shop(cfg: ShopConfig) -> ShopConfig:
    """Persist an edited shop. `_edited` marks it so re-seeding never overwrites
    live changes (the 'edits must persist' law)."""
    doc = cfg.model_dump(mode="json")
    doc["_edited"] = True
    await get_db()[COLLECTION].replace_one({"slug": cfg.slug}, doc, upsert=True)
    return cfg


def default_slug() -> str:
    """Which shop this deployment serves when the request names none.

    Env-driven, never hardcoded: one deployment per shop sets DEFAULT_SHOP_SLUG;
    a multi-tenant preview falls back to the first seed file on disk.
    """
    env = (os.environ.get("DEFAULT_SHOP_SLUG") or "").strip()
    if env:
        return env
    seeds = sorted(p.stem for p in SHOPS_DIR.glob("*.json"))
    if not seeds:
        raise RuntimeError("no shop configs found in backend/shops/")
    return seeds[0]
