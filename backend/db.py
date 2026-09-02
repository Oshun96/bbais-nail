"""Mongo (Atlas) connection for the BBAIS Nail Platform.

Connection string and database name come from the environment only — never a
literal in code (0-hardcode rule, VULN-CRED-01).
"""
from __future__ import annotations

import os
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

_client: Optional[AsyncIOMotorClient] = None
_db: Optional[AsyncIOMotorDatabase] = None


def _require(var: str) -> str:
    val = (os.environ.get(var) or "").strip()
    if not val:
        raise RuntimeError(
            f"{var} is not set. Copy .env.example to .env and fill it in — "
            "credentials are never committed or defaulted in code."
        )
    return val


def get_db() -> AsyncIOMotorDatabase:
    """Lazily open one pooled client for the process."""
    global _client, _db
    if _db is None:
        _client = AsyncIOMotorClient(_require("MONGO_URL"), serverSelectionTimeoutMS=10000)
        _db = _client[_require("DB_NAME")]
    return _db


async def ping() -> bool:
    await get_db().command("ping")
    return True


async def close() -> None:
    global _client, _db
    if _client is not None:
        _client.close()
    _client, _db = None, None
