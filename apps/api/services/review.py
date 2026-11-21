"""Workspace access to the ingest review queue."""

from __future__ import annotations

import logging
import sqlite3

from src.pipeline.models import DraftAlert
from src.pipeline.review import service as queue

from ..core import content
from . import review_mongo
from .source_links import with_official_source_url

logger = logging.getLogger(__name__)


class NotFound(LookupError):
    """The record is not waiting in the review queue."""


class WriteUnavailable(RuntimeError):
    """The review store cannot accept writes in this environment."""


def _item(alert: DraftAlert) -> dict:
    payload = alert.as_drug_alert().model_dump()
    payload["status"] = alert.status.value
    payload["validation_errors"] = list(alert.validation_errors)
    payload["extraction_method"] = alert.extraction_method
    return with_official_source_url(payload)


def _use_mongo() -> bool:
    return review_mongo.available()


def pending() -> dict:
    if _use_mongo():
        try:
            sqlite_items = [_item(alert) for alert in queue.pending()]
        except Exception:
            logger.warning("SQLite review hydrate skipped", exc_info=True)
            sqlite_items = []
        review_mongo.hydrate_from_sqlite_if_empty(sqlite_items)
        items = review_mongo.pending()
        return {"items": items, "total": len(items)}

    items = [_item(alert) for alert in queue.pending()]
    return {"items": items, "total": len(items)}


def approve(record_id: str) -> dict:
    try:
        if _use_mongo():
            ok = review_mongo.approve(record_id)
        else:
            ok = queue.approve(record_id)
    except sqlite3.OperationalError as error:
        raise WriteUnavailable(content.ERRORS["review_write_unavailable"]) from error
    if not ok:
        raise NotFound(record_id)
    return {"record_id": record_id, "status": "approved"}


def reject(record_id: str) -> dict:
    try:
        if _use_mongo():
            ok = review_mongo.reject(record_id)
        else:
            ok = queue.reject(record_id)
    except sqlite3.OperationalError as error:
        raise WriteUnavailable(content.ERRORS["review_write_unavailable"]) from error
    if not ok:
        raise NotFound(record_id)
    return {"record_id": record_id, "status": "rejected"}


def update(record_id: str, fields: dict) -> dict:
    try:
        if _use_mongo():
            item = review_mongo.update(record_id, fields)
            if item is None:
                raise NotFound(record_id)
            return item
        alert = queue.update(record_id, fields)
        if alert is None:
            raise NotFound(record_id)
        return _item(alert)
    except sqlite3.OperationalError as error:
        raise WriteUnavailable(content.ERRORS["review_write_unavailable"]) from error


def remove(record_id: str) -> dict:
    try:
        if _use_mongo():
            ok = review_mongo.remove(record_id)
        else:
            ok = queue.remove(record_id)
    except sqlite3.OperationalError as error:
        raise WriteUnavailable(content.ERRORS["review_write_unavailable"]) from error
    if not ok:
        raise NotFound(record_id)
    return {"record_id": record_id, "status": "deleted"}
