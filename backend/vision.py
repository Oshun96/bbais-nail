"""Photo consultation — BLKOmni.

A client (or the front desk) sends a photo of their hands. The vision model
reads the nails; this module turns that reading into a recommendation the shop
can actually deliver, because every suggested shape and colour is mapped onto
THIS shop's own menu before it is shown.

The same two rules as the front-desk agent apply, and for the same reason: no
engine is ever named, and two tries then stop.
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import httpx

from agent.model import MAX_TRIES, ModelUnavailable, scrub
from shop_config import ShopConfig

CONNECT_TIMEOUT = 15.0
READ_TIMEOUT = 300.0
MAX_UPLOAD_BYTES = 12_000_000        # a phone photo, before we shrink it
MAX_EDGE = 1024                      # what we actually send
ALLOWED = {"image/jpeg", "image/png", "image/webp"}


class VisionUnavailable(ModelUnavailable):
    pass


def endpoint() -> str:
    url = (os.environ.get("BLKOMNI_URL") or "").strip().rstrip("/")
    if not url:
        raise VisionUnavailable("Photo consultations aren't switched on yet.")
    return url


def model_name() -> str:
    return (os.environ.get("BLKOMNI_MODEL") or "blkomni-flash-ba1").strip()


def configured() -> bool:
    return bool((os.environ.get("BLKOMNI_URL") or "").strip())


def try_on_enabled() -> bool:
    """The render step from Phase 8. Present in the flow but switched off until
    the render service is actually connected — never a button that does nothing."""
    return bool((os.environ.get("FLYBLK_URL") or "").strip())


# ------------------------------------------------------------------ image ---
def prepare_image(raw: bytes, content_type: str) -> str:
    """Validate, shrink and encode. Shrinking is not cosmetic: a 12MP phone photo
    wastes GPU time and adds nothing a nail reading needs."""
    if len(raw) > MAX_UPLOAD_BYTES:
        raise ValueError("that photo is too large — try one under 12MB")
    if content_type not in ALLOWED:
        raise ValueError("please send a JPEG, PNG or WebP photo")

    from PIL import Image, ImageOps

    try:
        img = Image.open(io.BytesIO(raw))
        img = ImageOps.exif_transpose(img)      # honour the phone's rotation
        img = img.convert("RGB")
    except Exception:
        raise ValueError("that file could not be read as an image")

    if max(img.size) > MAX_EDGE:
        img.thumbnail((MAX_EDGE, MAX_EDGE), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


# ----------------------------------------------------------------- prompt ---
def _prompt(cfg: ShopConfig, client_note: str = "") -> str:
    shapes = ", ".join(f"{o.id} ({o.label})" for o in cfg.nail_menu.shapes if o.active)
    lengths = ", ".join(f"{o.id} ({o.label})" for o in cfg.nail_menu.lengths if o.active)
    finishes = ", ".join(f"{o.id} ({o.label})" for o in cfg.nail_menu.finishes if o.active)
    colours = ", ".join(f"{c.id} ({c.name}, {c.family})" for c in cfg.colours if c.active)

    # What the client asked for in their own words. It leads the recommendation:
    # a consultation that ignores what someone actually wants is not advice.
    asked = ""
    if client_note.strip():
        asked = (
            f'\n\nThe client has told you what they are after, in their own words:\n'
            f'"{client_note.strip()[:600]}"\n'
            "Take this as the brief. Your recommendation must answer it directly, using the\n"
            "closest options on the menu below. If what they asked for is not on the menu, say\n"
            "so plainly in your consultation and recommend the nearest thing the shop can do.\n"
        )

    return f"""Look at this photo of a client's hands and give a nail consultation.

Report ONLY what you can actually see. If something is not visible, say "unclear"
rather than guessing.{asked}

Then recommend from this shop's menu — you may ONLY use these ids:
SHAPES: {shapes}
LENGTHS: {lengths}
FINISHES: {finishes}
COLOURS: {colours}

Reply with JSON only, no other text, in exactly this form:
{{
  "observed": {{
    "nail_shape": "what shape they are filed to now, or unclear",
    "length": "short / medium / long, or unclear",
    "current_colour": "what is on them now, or bare, or unclear",
    "skin_tone": "a short plain description",
    "condition": "one short sentence on nail and cuticle condition"
  }},
  "recommended": {{
    "shapes": ["up to 2 shape ids from the list"],
    "lengths": ["up to 2 length ids from the list"],
    "finishes": ["up to 2 finish ids from the list"],
    "colours": ["up to 3 colour ids from the list"]
  }},
  "why": "one or two sentences on why these suit this hand",
  "consultation": "3 to 5 warm sentences spoken to the client by their nail tech, answering what they asked for"
}}"""


def _extract_json(text: str) -> Optional[dict]:
    """Pull the JSON object out of a reply that may be wrapped in prose or fences.

    A THINKING model narrates before it answers, so the object is rarely the
    whole reply. Take the LAST balanced object, which is the conclusion.
    """
    if not text:
        return None
    text = re.sub(r"^\s*```(?:json)?|```\s*$", "", text.strip(), flags=re.MULTILINE)

    best = None
    for m in re.finditer(r"\{", text):
        depth, in_str, esc = 0, False, False
        for i in range(m.start(), len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(text[m.start():i + 1])
                        if isinstance(obj, dict) and ("recommended" in obj or "observed" in obj):
                            best = obj
                    except json.JSONDecodeError:
                        pass
                    break
    return best


# ------------------------------------------------------------------- call ---
async def analyse(cfg: ShopConfig, data_url: str, client_note: str = "") -> Dict[str, Any]:
    """One consultation. Raises VisionUnavailable with a client-safe message."""
    payload = {
        "model": model_name(),
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": _prompt(cfg, client_note)},
            {"type": "image_url", "image_url": {"url": data_url}},
        ]}],
        "temperature": 0.2,
        "max_tokens": 1400,
    }
    url = f"{endpoint()}/v1/chat/completions"
    timeout = httpx.Timeout(READ_TIMEOUT, connect=CONNECT_TIMEOUT)

    for _ in range(MAX_TRIES):
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as c:
                r = await c.post(url, json=payload)
            if r.status_code == 404:
                raise VisionUnavailable("Photo consultations aren't reachable right now.")
            if r.status_code >= 400:
                continue
            raw = r.json()["choices"][0]["message"]["content"] or ""
            parsed = _extract_json(raw)
            if parsed:
                return parsed
            # Readable prose but no JSON is still a usable consultation.
            return {"observed": {}, "recommended": {}, "why": "",
                    "consultation": raw.strip()[:1200]}
        except VisionUnavailable:
            raise
        except (httpx.TimeoutException, httpx.HTTPError, KeyError, IndexError, ValueError):
            continue

    raise VisionUnavailable(
        "The consultation is taking longer than usual. "
        "You can pick a shape and colour yourself on the booking form in the meantime."
    )


# ---------------------------------------------------------------- mapping ---
def _match(ids: Any, allowed: Dict[str, Any], limit: int) -> List[str]:
    """Keep only ids this shop genuinely offers. A recommendation the shop cannot
    deliver is worse than no recommendation."""
    out: List[str] = []
    for v in (ids or [])[: limit * 2]:
        key = str(v).strip().lower()
        if key in allowed and key not in out:
            out.append(key)
        if len(out) >= limit:
            break
    return out


def to_shop_menu(cfg: ShopConfig, parsed: Dict[str, Any]) -> Dict[str, Any]:
    """Turn the model's reading into something bookable on THIS shop's menu."""
    shapes = {o.id: o for o in cfg.nail_menu.shapes if o.active}
    lengths = {o.id: o for o in cfg.nail_menu.lengths if o.active}
    finishes = {o.id: o for o in cfg.nail_menu.finishes if o.active}
    colours = {c.id: c for c in cfg.colours if c.active}

    rec = parsed.get("recommended") or {}
    s = _match(rec.get("shapes"), shapes, 2)
    l = _match(rec.get("lengths"), lengths, 2)
    f = _match(rec.get("finishes"), finishes, 2)
    c = _match(rec.get("colours"), colours, 3)

    obs = parsed.get("observed") or {}
    text = scrub(str(parsed.get("consultation") or "").strip(), cfg.name)
    why = scrub(str(parsed.get("why") or "").strip(), cfg.name)

    return {
        "observed": {k: str(obs.get(k, "") or "")[:200] for k in
                     ("nail_shape", "length", "current_colour", "skin_tone", "condition")},
        "why": why,
        "consultation": text,
        "recommended": {
            "shapes": [{"id": i, "label": shapes[i].label, "surcharge": shapes[i].surcharge} for i in s],
            "lengths": [{"id": i, "label": lengths[i].label, "surcharge": lengths[i].surcharge} for i in l],
            "finishes": [{"id": i, "label": finishes[i].label, "surcharge": finishes[i].surcharge} for i in f],
            "colours": [{"id": i, "name": colours[i].name, "hex": colours[i].hex,
                         "family": colours[i].family} for i in c],
        },
        # Straight into the booking flow, pre-filled.
        "book_with": {
            "shape": s[0] if s else None,
            "length": l[0] if l else None,
            "finish": f[0] if f else None,
            "colour": c[0] if c else None,
        },
    }
