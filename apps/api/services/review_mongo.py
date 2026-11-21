"""MongoDB-backed review queue for writable workspace actions on Vercel."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pymongo import ASCENDING, ReturnDocument

from ..core import settings
from ..db import mongo
from .source_links import with_official_source_url

EDITABLE_FIELDS = frozenset(
    {
        "product_name",
        "reason",
        "more_info",
        "manufacturer",
        "distributor",
        "publish_date",
        "source_country",
    }
)


def available() -> bool:
    return bool(mongo.uri())


def _collection():
    return mongo.collection(settings.REVIEW_COLLECTION)


def _alerts():
    return mongo.collection(settings.ALERTS_COLLECTION)


def _as_item(doc: dict[str, Any]) -> dict[str, Any]:
    payload = {key: value for key, value in doc.items() if key != "_id"}
    payload.setdefault("record_id", doc.get("_id") or doc.get("record_id"))
    payload.setdefault("validation_errors", [])
    payload.setdefault("extraction_method", "existing_scraper")
    payload.setdefault("status", "pending")
    return with_official_source_url(payload)


def hydrate_from_sqlite_if_empty(sqlite_pending: list[dict[str, Any]]) -> None:
    """Copy SQLite pending drafts into Mongo once when the collection is empty."""

    collection = _collection()
    if collection.estimated_document_count() > 0 or not sqlite_pending:
        return
    collection.create_index([("status", ASCENDING)])
    now = datetime.now(timezone.utc).isoformat()
    docs = []
    for item in sqlite_pending:
        record_id = item.get("record_id")
        if not record_id:
            continue
        doc = dict(item)
        doc["_id"] = record_id
        doc["status"] = "pending"
        doc.setdefault("scraped_at", now)
        docs.append(doc)
    if docs:
        collection.insert_many(docs, ordered=False)


def pending() -> list[dict[str, Any]]:
    collection = _collection()
    collection.create_index([("status", ASCENDING)])
    cursor = collection.find({"status": "pending"}).sort("publish_date", -1)
    return [_as_item(doc) for doc in cursor]


def update(record_id: str, fields: dict[str, Any]) -> dict[str, Any] | None:
    payload = {key: fields[key] for key in EDITABLE_FIELDS if key in fields}
    if not payload:
        return None
    for key, value in list(payload.items()):
        if isinstance(value, str):
            payload[key] = value.strip() or None
    doc = _collection().find_one_and_update(
        {"_id": record_id, "status": "pending"},
        {"$set": payload},
        return_document=ReturnDocument.AFTER,
    )
    return _as_item(doc) if doc else None


def approve(record_id: str) -> bool:
    collection = _collection()
    doc = collection.find_one({"_id": record_id, "status": "pending"})
    if not doc:
        return False
    alert = {key: value for key, value in doc.items() if key not in {"_id", "status", "validation_errors", "extraction_method", "raw_path"}}
    alert["record_id"] = record_id
    # Keep published snapshot_id if already present; otherwise mark as review-approved.
    alert.setdefault("snapshot_id", f"review-approved-{datetime.now(timezone.utc):%Y%m%d}")
    _alerts().update_one(
        {"_id": record_id},
        {"$set": {key: value for key, value in alert.items() if key != "record_id"}},
        upsert=True,
    )
    collection.update_one({"_id": record_id}, {"$set": {"status": "approved"}})
    return True


def reject(record_id: str) -> bool:
    result = _collection().update_one(
        {"_id": record_id, "status": "pending"},
        {"$set": {"status": "rejected"}},
    )
    return result.matched_count > 0


def remove(record_id: str) -> bool:
    result = _collection().delete_one({"_id": record_id, "status": "pending"})
    return result.deleted_count > 0
