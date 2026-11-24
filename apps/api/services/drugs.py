"""NCI oncology drug list backed by MongoDB Atlas."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from pymongo import ASCENDING, ReplaceOne
from pymongo.collection import Collection
from pymongo.errors import PyMongoError

from ..core import settings
from ..db import mongo

logger = logging.getLogger(__name__)

SOURCE_NAME = "NCI A–Z List of Cancer Drugs"
META_ID = "oncology_drugs"
SLUG_FIELD = "slug"
NAME_FIELD = "name"
LETTER_FIELD = "letter"
INFO_URL_FIELD = "info_url"
UPDATED_FIELD = "updated_at"
COUNT_FIELD = "count"
SOURCE_FIELD = "source"


class Missing(RuntimeError):
    """The drug list is not available in Atlas or the seed file."""


class StoreUnavailable(RuntimeError):
    """MongoDB is not configured or unreachable."""


def _display_name(slug: str) -> str:
    parts = [part for part in slug.replace("_", "-").split("-") if part]
    return "-".join(part[:1].upper() + part[1:] for part in parts) if parts else slug


def _letter(slug: str) -> str:
    for char in slug:
        if char.isalpha():
            return char.upper()
    return "#"


def _info_url(slug: str) -> str:
    return settings.NCI_DRUG_INFO_URL.format(slug=slug)


def _row(slug: str) -> dict[str, Any]:
    return {
        "_id": slug,
        SLUG_FIELD: slug,
        NAME_FIELD: _display_name(slug),
        LETTER_FIELD: _letter(slug),
        INFO_URL_FIELD: _info_url(slug),
    }


def _public(document: dict[str, Any]) -> dict[str, Any]:
    slug = str(document.get(SLUG_FIELD) or document.get("_id") or "")
    return {
        "id": slug,
        "name": document.get(NAME_FIELD) or _display_name(slug),
        "letter": document.get(LETTER_FIELD) or _letter(slug),
        "info_url": document.get(INFO_URL_FIELD) or _info_url(slug),
    }


@lru_cache(maxsize=1)
def _drugs() -> Collection:
    store = mongo.collection(settings.DRUGS_COLLECTION)
    store.create_index([(LETTER_FIELD, ASCENDING), (NAME_FIELD, ASCENDING)])
    store.create_index([(SLUG_FIELD, ASCENDING)], unique=True)
    return store


@lru_cache(maxsize=1)
def _meta() -> Collection:
    return mongo.collection(settings.DRUGS_META_COLLECTION)


def _store() -> Collection:
    try:
        return _drugs()
    except (mongo.NotConfigured, PyMongoError) as error:
        raise StoreUnavailable(str(error)) from error


def _meta_store() -> Collection:
    try:
        return _meta()
    except (mongo.NotConfigured, PyMongoError) as error:
        raise StoreUnavailable(str(error)) from error


def _slugs_from_file(path: Path) -> list[str]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise Missing(str(path)) from error
    if not isinstance(raw, list):
        raise Missing(str(path))
    slugs: list[str] = []
    seen: set[str] = set()
    for item in raw:
        slug = str(item or "").strip().lower()
        if not slug or slug in seen:
            continue
        seen.add(slug)
        slugs.append(slug)
    return slugs


def sync_from_file(path: Path | None = None) -> dict[str, Any]:
    """Replace the Atlas drug collection with names from the NCI JSON file."""
    seed = path or settings.drugs_list_path()
    if not seed.is_file():
        raise Missing(str(seed))
    slugs = _slugs_from_file(seed)
    if not slugs:
        raise Missing(str(seed))

    store = _store()
    now = datetime.now(timezone.utc)
    ops = [ReplaceOne({"_id": slug}, _row(slug), upsert=True) for slug in slugs]
    store.bulk_write(ops, ordered=False)
    store.delete_many({"_id": {"$nin": slugs}})
    _meta_store().replace_one(
        {"_id": META_ID},
        {
            "_id": META_ID,
            SOURCE_FIELD: SOURCE_NAME,
            COUNT_FIELD: len(slugs),
            UPDATED_FIELD: now,
            "seed_file": seed.name,
        },
        upsert=True,
    )
    logger.info("Synced %s oncology drugs into Atlas from %s", len(slugs), seed)
    return catalog(ensure_seeded=False)


def _read_meta() -> dict[str, Any]:
    try:
        document = _meta_store().find_one({"_id": META_ID}) or {}
    except StoreUnavailable:
        return {}
    return document


def catalog(*, ensure_seeded: bool = True) -> dict[str, Any]:
    """Return the drug list from Atlas, seeding from JSON when empty."""
    try:
        store = _store()
    except StoreUnavailable as error:
        raise Missing("mongodb") from error

    count = store.estimated_document_count()
    if count == 0 and ensure_seeded:
        sync_from_file()
        store = _store()
        count = store.estimated_document_count()
    if count == 0:
        raise Missing("empty")

    cursor = store.find({}, projection={SLUG_FIELD: 1, NAME_FIELD: 1, LETTER_FIELD: 1, INFO_URL_FIELD: 1})
    drugs = sorted(
        (_public(document) for document in cursor),
        key=lambda row: (row["letter"], row["name"].lower()),
    )
    meta = _read_meta()
    updated = meta.get(UPDATED_FIELD)
    return {
        "source": meta.get(SOURCE_FIELD) or SOURCE_NAME,
        "source_url": settings.NCI_DRUGS_SOURCE_URL,
        "count": len(drugs),
        "drugs": drugs,
        "storage": "mongodb",
        "updated_at": updated.isoformat() if hasattr(updated, "isoformat") else updated,
    }
