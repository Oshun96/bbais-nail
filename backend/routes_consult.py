"""Photo consultation API.

The try-on render is present in this response from the start, switched off, so
the flow is complete and Phase 8 only has to flip a switch — never a button that
pretends to work.
"""
from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

import vision

router = APIRouter(prefix="/api/shops/{slug}/consult")


def register(get_shop):

    @router.get("/status")
    async def consult_status(slug: str):
        """Whether photo consultation is on, and whether try-on is yet.

        Does not touch the GPU: opening a page must never wake one.
        """
        return {
            "available": vision.configured(),
            "max_upload_bytes": vision.MAX_UPLOAD_BYTES,
            "accepted": sorted(vision.ALLOWED),
            "cold_start_note": (
                "The first consultation after a quiet spell takes a couple of minutes "
                "to come back. Everything else on the site is instant."
            ),
            "try_on": {
                "available": vision.try_on_enabled(),
                "note": "Seeing the look rendered on your own hand is coming soon.",
            },
        }

    @router.post("")
    async def consult(slug: str, photo: UploadFile = File(...),
                      note: str = Form("")):
        """`note` is the client's own words — what they actually want. It leads
        the recommendation rather than sitting beside it."""
        cfg = await get_shop(slug)
        if not vision.configured():
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                                "Photo consultations aren't switched on yet.")

        raw = await photo.read()
        try:
            data_url = vision.prepare_image(raw, photo.content_type or "")
        except ValueError as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))

        try:
            parsed = await vision.analyse(cfg, data_url, note[:600])
        except vision.VisionUnavailable as e:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e))

        result = vision.to_shop_menu(cfg, parsed)
        result["asked_for"] = note.strip()[:600]
        result["try_on"] = {
            "available": vision.try_on_enabled(),
            "note": "Seeing this rendered on your own hand is coming soon.",
        }
        return result

    return router
