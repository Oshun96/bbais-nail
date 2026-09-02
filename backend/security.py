"""BBAIS Security Standard — baked in from Phase 1, completed in Phase 7.

Covers here:
  VULN-CRED-01  no credential is ever hardcoded, defaulted, logged or returned
                by an API. `require_env` is the only way secrets are read.
  VULN-AUTH-01  no endpoint is authenticated by a client-supplied identifier
                alone; admin surfaces go through `require_admin`.
  Emergent #1   CORS is an explicit allowlist, never "*" with credentials.
  Emergent #2   security headers on every response.
  Emergent #3   request bodies are size-capped before parsing.
"""
from __future__ import annotations

import hmac
import os
from typing import List

from fastapi import Header, HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware

MAX_BODY_BYTES = 1_000_000  # 1 MB; Phase 6 photo upload gets its own larger cap

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "SAMEORIGIN",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), payment=(self)",
    "Cross-Origin-Opener-Policy": "same-origin",
}


def require_env(var: str) -> str:
    """Read a required secret from the environment. Never defaulted in code, and
    the value is never echoed into an error message."""
    val = (os.environ.get(var) or "").strip()
    if not val:
        raise RuntimeError(f"{var} is not set (see .env.example)")
    return val


def optional_env(var: str, default: str = "") -> str:
    return (os.environ.get(var) or "").strip() or default


def cors_origins() -> List[str]:
    """Explicit allowlist from env. Refuses the wildcard outright — a "*" origin
    with credentials is the single most common CORS failure."""
    raw = optional_env("CORS_ORIGINS")
    if not raw:
        return []
    origins = [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]
    if "*" in origins:
        raise RuntimeError("CORS_ORIGINS must be an explicit allowlist, not '*'")
    return origins


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        for k, v in SECURITY_HEADERS.items():
            response.headers.setdefault(k, v)
        return response


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject oversized bodies on the declared length before anything parses them."""

    def __init__(self, app, max_bytes: int = MAX_BODY_BYTES):
        super().__init__(app)
        self.max_bytes = max_bytes

    # A photo is legitimately far bigger than a JSON body, so the consultation
    # route gets its own cap rather than forcing the whole API's limit up.
    UPLOAD_PATHS = ("/consult",)
    UPLOAD_MAX_BYTES = 12_000_000

    async def dispatch(self, request: Request, call_next):
        limit = (self.UPLOAD_MAX_BYTES
                 if request.url.path.endswith(self.UPLOAD_PATHS) else self.max_bytes)
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > limit:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "request body too large")
        return await call_next(request)


async def require_admin(x_admin_key: str = Header(default="")) -> bool:
    """Admin gate (VULN-AUTH-01).

    The key lives in the environment, is compared in constant time, and an unset
    key FAILS CLOSED — an unconfigured deployment refuses admin access rather
    than silently allowing it.
    """
    expected = optional_env("ADMIN_API_KEY")
    if not expected:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "admin access is not configured")
    if not x_admin_key or not hmac.compare_digest(x_admin_key, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid admin key")
    return True
