"""The model connection.

Two rules are enforced HERE, in code, rather than trusted to prompt wording:

1. **Nothing about the engine reaches a member of the public.** `scrub()` strips
   model, vendor and infrastructure names from every reply before it leaves the
   server. A prompt instruction can be talked around; a regex on the way out
   cannot.

2. **Two tries, then stop.** A cold GPU takes a couple of minutes to answer, and
   that is disclosed honestly rather than papered over with retries. A high retry
   cap on a paid endpoint is how you burn money overnight.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional

import httpx

MAX_TRIES = 2                     # hard cap. Never raise this.
CONNECT_TIMEOUT = 15.0
READ_TIMEOUT = 300.0              # a cold start can legitimately take ~150s


class ModelUnavailable(RuntimeError):
    """The desk could not be reached. Carries a client-safe message only."""


class ModelNotConfigured(ModelUnavailable):
    pass


# Infrastructure and vendor names that must never appear in a member-facing
# reply. Matched case-insensitively on word boundaries.
_FORBIDDEN = re.compile(
    r"\b("
    r"blkcode|blkomni|blk-?ai|bbais[- ]?ba\d*|ba1[- ]?fast|"
    r"qwen\w*|vllm|modal(?:\.com)?|openai|anthropic|claude|gpt-?\d*|llama\d*|mistral|"
    r"language model|large language model|\bllm\b|neural network|"
    r"as an ai|i am an ai|i'm an ai|ai assistant|ai model|chatbot"
    r")\b",
    re.IGNORECASE,
)

_URLS = re.compile(r"https?://\S*(?:modal\.run|onrender\.com/api)\S*", re.IGNORECASE)


def scrub(text: str, shop_name: str) -> str:
    """Strip anything that would leak how the desk is built.

    A sentence that mentions the engine is almost always ABOUT the engine, so
    word-substitution would leave mangled nonsense ("we are powered by Shop Name
    running on Shop Name"). Any offending sentence is dropped instead; if that
    empties the reply, the desk deflects in its own voice. Losing a sentence is
    always better than leaking one or shipping word salad.
    """
    if not text:
        return text

    cleaned = _URLS.sub("", text)
    kept = [s for s in re.split(r"(?<=[.!?])\s+", cleaned) if s.strip() and not _FORBIDDEN.search(s)]
    out = re.sub(r"[ \t]{2,}", " ", " ".join(kept)).strip()

    if not out:
        return (f"I'm the front desk here at {shop_name} — I can check prices, find you a time, "
                "or get you booked in. What are you after?")
    return out


def leaked(text: str) -> bool:
    """Whether a reply mentioned anything it should not. For logging only."""
    return bool(text and (_FORBIDDEN.search(text) or _URLS.search(text)))


def endpoint() -> str:
    url = (os.environ.get("BLKCODE_BA1_FAST_URL") or "").strip().rstrip("/")
    if not url:
        raise ModelNotConfigured("The front desk isn't connected yet.")
    return url


def model_name() -> str:
    return (os.environ.get("BLKCODE_BA1_FAST_MODEL") or "blkcode-ba1-fast").strip()


def configured() -> bool:
    return bool((os.environ.get("BLKCODE_BA1_FAST_URL") or "").strip())


async def complete(
    messages: List[Dict[str, Any]],
    *,
    tools: Optional[List[dict]] = None,
    temperature: float = 0.3,
    max_tokens: int = 900,
) -> dict:
    """One chat completion. Returns the raw assistant message (which may carry
    tool calls). Raises ModelUnavailable with a client-safe message."""
    url = f"{endpoint()}/v1/chat/completions"
    payload: Dict[str, Any] = {
        "model": model_name(),
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    last = ""
    timeout = httpx.Timeout(READ_TIMEOUT, connect=CONNECT_TIMEOUT)
    for attempt in range(MAX_TRIES):
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as c:
                r = await c.post(url, json=payload)
            if r.status_code == 404:
                # A 404 is a wrong address, not a cold start. Fail immediately
                # rather than retrying into a wall.
                raise ModelUnavailable("The front desk isn't reachable right now.")
            if r.status_code >= 400:
                last = f"{r.status_code}"
                continue
            data = r.json()
            return data["choices"][0]["message"]
        except ModelUnavailable:
            raise
        except (httpx.TimeoutException, httpx.HTTPError) as e:
            last = type(e).__name__
        except (KeyError, IndexError, ValueError):
            last = "unreadable response"

    raise ModelUnavailable(
        "The front desk is taking longer than usual to answer. "
        "You can book instantly with the booking form in the meantime."
    )
