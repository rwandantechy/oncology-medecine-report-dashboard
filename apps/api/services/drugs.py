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


def _letter(name_or_slug: str) -> str:
    for char in name_or_slug:
        if char.isalpha():
            return char.upper()
    return "#"


def _info_url_from_slug(slug: str) -> str:
    return settings.NCI_DRUG_INFO_URL.format(slug=slug)


def _row(slug: str, *, name: str | None = None, info_url: str | None = None) -> dict[str, Any]:
    label = (name or "").strip() or _display_name(slug)
    return {
        "_id": slug,
        SLUG_FIELD: slug,
        NAME_FIELD: label,
        LETTER_FIELD: _letter(label),
        INFO_URL_FIELD: (info_url or "").strip() or _info_url_from_slug(slug),
    }


def _public(document: dict[str, Any]) -> dict[str, Any]:
    slug = str(document.get(SLUG_FIELD) or document.get("_id") or "")
    name = document.get(NAME_FIELD) or _display_name(slug)
    return {
        "id": slug,
        "name": name,
        "letter": document.get(LETTER_FIELD) or _letter(name),
        "info_url": document.get(INFO_URL_FIELD) or _info_url_from_slug(slug),
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


def _rows_from_catalog(path: Path) -> list[dict[str, Any]]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise Missing(str(path)) from error
    if not isinstance(raw, list) or not raw:
        raise Missing(str(path))

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw:
        if isinstance(item, str):
            slug = item.strip().lower()
            if not slug or slug in seen:
                continue
            seen.add(slug)
            rows.append(_row(slug))
            continue
        if not isinstance(item, dict):
            continue
        slug = str(item.get("id") or item.get("slug") or "").strip().lower()
        if not slug or slug in seen:
            continue
        seen.add(slug)
        rows.append(
            _row(
                slug,
                name=str(item.get("name") or "").strip() or None,
                info_url=str(item.get("info_url") or "").strip() or None,
            )
        )
    if not rows:
        raise Missing(str(path))
    return rows


def _rows_from_token_list(path: Path) -> list[dict[str, Any]]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise Missing(str(path)) from error
    if not isinstance(raw, list):
        raise Missing(str(path))
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw:
        slug = str(item or "").strip().lower()
        if not slug or slug in seen:
            continue
        seen.add(slug)
        rows.append(_row(slug))
    if not rows:
        raise Missing(str(path))
    return rows


def _seed_rows() -> tuple[list[dict[str, Any]], Path]:
    catalog = settings.drugs_catalog_path()
    if catalog.is_file():
        return _rows_from_catalog(catalog), catalog
    tokens = settings.drugs_list_path()
    if tokens.is_file():
        return _rows_from_token_list(tokens), tokens
    raise Missing(str(catalog))


def sync_from_file(path: Path | None = None) -> dict[str, Any]:
    """Replace the Atlas drug collection from the NCI catalog (or token list)."""
    if path is not None:
        rows = (
            _rows_from_catalog(path)
            if path.name.endswith("_catalog.json") or "catalog" in path.name
            else _rows_from_token_list(path)
        )
        seed = path
    else:
        rows, seed = _seed_rows()

    store = _store()
    now = datetime.now(timezone.utc)
    slugs = [row["_id"] for row in rows]
    ops = [ReplaceOne({"_id": row["_id"]}, row, upsert=True) for row in rows]
    store.bulk_write(ops, ordered=False)
    store.delete_many({"_id": {"$nin": slugs}})
    _meta_store().replace_one(
        {"_id": META_ID},
        {
            "_id": META_ID,
            SOURCE_FIELD: SOURCE_NAME,
            COUNT_FIELD: len(rows),
            UPDATED_FIELD: now,
            "seed_file": seed.name,
        },
        upsert=True,
    )
    logger.info("Synced %s oncology drugs into Atlas from %s", len(rows), seed)
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

    cursor = store.find(
        {},
        projection={SLUG_FIELD: 1, NAME_FIELD: 1, LETTER_FIELD: 1, INFO_URL_FIELD: 1},
    )
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
