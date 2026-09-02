"""SEO and PWA files, generated live per shop.

These are served from the API rather than baked into the build so that a shop
editing its hours or prices in the admin panel has correct structured data
immediately — there is never a stale second copy.

The static site proxies /robots.txt, /sitemap.xml, /llms.txt and /manifest.json
here for its own shop.
"""
from __future__ import annotations

import os

from fastapi import APIRouter, Request, Response

import reviews
import seo
import shop_store

router = APIRouter()


def _base_url(request: Request, slug: str) -> str:
    """The public address of the SITE (not the API).

    Env-driven, never hardcoded: SITE_URL wins; otherwise fall back to the
    request's own origin so a preview deployment describes itself correctly.
    """
    configured = (os.environ.get("SITE_URL") or "").strip().rstrip("/")
    if configured:
        return configured
    return str(request.base_url).rstrip("/")


def register(get_shop):

    async def _shop(slug: str | None):
        return await get_shop(slug or shop_store.default_slug())

    @router.get("/api/shops/{slug}/seo/schemas")
    async def schemas(slug: str, request: Request):
        """The 14 JSON-LD schemas for this shop, ready to inject into the page."""
        cfg = await _shop(slug)
        stats = await reviews.stats(slug)
        return {"schemas": seo.build_schemas(cfg, _base_url(request, slug), stats)}

    @router.get("/api/shops/{slug}/llms.txt", response_class=Response)
    async def llms(slug: str, request: Request):
        cfg = await _shop(slug)
        return Response(seo.llms_txt(cfg, _base_url(request, slug)),
                        media_type="text/plain; charset=utf-8")

    @router.get("/api/shops/{slug}/robots.txt", response_class=Response)
    async def robots(slug: str, request: Request):
        await _shop(slug)
        return Response(seo.robots_txt(_base_url(request, slug)),
                        media_type="text/plain; charset=utf-8")

    @router.get("/api/shops/{slug}/sitemap.xml", response_class=Response)
    async def sitemap(slug: str, request: Request):
        cfg = await _shop(slug)
        return Response(seo.sitemap_xml(cfg, _base_url(request, slug)),
                        media_type="application/xml")

    @router.get("/api/shops/{slug}/manifest.json")
    async def pwa_manifest(slug: str, request: Request):
        cfg = await _shop(slug)
        return seo.manifest(cfg, _base_url(request, slug))

    @router.get("/api/shops/{slug}/icon-{size}.png", response_class=Response)
    async def icon(slug: str, size: int):
        cfg = await _shop(slug)
        px = 512 if size not in (192, 512) else size
        return Response(seo.icon_png(cfg, px), media_type="image/png",
                        headers={"Cache-Control": "public, max-age=86400"})

    return router
