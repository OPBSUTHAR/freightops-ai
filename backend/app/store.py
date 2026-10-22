"""Repository layer.

The API only talks to this interface, so the control tower runs with zero
infrastructure (MemoryStore) or on MongoDB (MongoStore) without code changes.
Documents use Mongo-shaped dicts with a string `id` field.
"""
from __future__ import annotations

import copy
import logging
import uuid
from typing import Any, Iterable

from .config import settings

log = logging.getLogger("freightops.store")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


class Store:
    def __init__(self) -> None:
        self._data: dict[str, dict[str, dict[str, Any]]] = {}

    async def insert(self, collection: str, doc: dict[str, Any]) -> dict[str, Any]:
        bucket = self._data.setdefault(collection, {})
        bucket[doc["id"]] = copy.deepcopy(doc)
        return copy.deepcopy(doc)

    async def get(self, collection: str, doc_id: str) -> dict[str, Any] | None:
        doc = self._data.get(collection, {}).get(doc_id)
        return copy.deepcopy(doc) if doc else None

    async def find(
        self,
        collection: str,
        *,
        where: dict[str, Any] | None = None,
        sort: str | None = None,
        desc: bool = True,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        rows = list(self._data.get(collection, {}).values())
        if where:
            rows = [r for r in rows if all(r.get(k) == v for k, v in where.items())]
        if sort:
            rows.sort(key=lambda r: r.get(sort) or "", reverse=desc)
        rows = [copy.deepcopy(r) for r in rows]
        return rows[:limit] if limit else rows

    async def update(self, collection: str, doc_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        bucket = self._data.setdefault(collection, {})
        if doc_id not in bucket:
            return None
        bucket[doc_id].update(copy.deepcopy(patch))
        return copy.deepcopy(bucket[doc_id])

    async def count(self, collection: str) -> int:
        return len(self._data.get(collection, {}))

    async def clear(self, collection: str) -> None:
        self._data.pop(collection, None)

    async def ping(self) -> str:
        return "memory"

    async def close(self) -> None:
        return None


class MongoStore(Store):
    """Thin async Mongo adapter. Falls back to memory when no driver is installed."""

    def __init__(self, uri: str, db_name: str) -> None:
        super().__init__()
        try:
            from pymongo import AsyncMongoClient  # PyMongo 4.9+

            self._client = AsyncMongoClient(uri, serverSelectionTimeoutMS=2500)
        except ImportError:  # pragma: no cover - legacy driver
            from motor.motor_asyncio import AsyncIOMotorClient

            self._client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=2500)
        self._db = self._client[db_name]

    async def insert(self, collection: str, doc: dict[str, Any]) -> dict[str, Any]:
        await self._db[collection].insert_one(copy.deepcopy(doc))
        return doc

    async def get(self, collection: str, doc_id: str) -> dict[str, Any] | None:
        return await self._db[collection].find_one({"id": doc_id}, {"_id": 0})

    async def find(
        self,
        collection: str,
        *,
        where: dict[str, Any] | None = None,
        sort: str | None = None,
        desc: bool = True,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        cursor = self._db[collection].find(where or {}, {"_id": 0})
        if sort:
            cursor = cursor.sort(sort, -1 if desc else 1)
        if limit:
            cursor = cursor.limit(limit)
        return [doc async for doc in cursor]

    async def update(self, collection: str, doc_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        await self._db[collection].update_one({"id": doc_id}, {"$set": patch})
        return await self.get(collection, doc_id)

    async def count(self, collection: str) -> int:
        return await self._db[collection].count_documents({})

    async def clear(self, collection: str) -> None:
        await self._db[collection].delete_many({})

    async def ping(self) -> str:
        await self._client.admin.command("ping")
        return "mongo"

    async def close(self) -> None:
        self._client.close()


def build_store() -> Store:
    if settings.storage == "mongo":
        try:
            return MongoStore(settings.mongodb_uri, settings.mongodb_db)
        except Exception as exc:  # pragma: no cover - environment dependent
            log.warning("Mongo unavailable (%s); using in-memory store", exc)
    return Store()


async def ensure_seed(store: Store, seed_fn: Iterable) -> None:
    if await store.count("shipments") == 0:
        for doc in seed_fn:
            await store.insert("shipments", doc)
