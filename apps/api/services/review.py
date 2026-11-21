"""Workspace access to the ingest review queue.

The queue lives in the pipeline SQLite database. Approved notices still reach the
public snapshot through the usual import path; this service only manages the
holding queue.
"""

from __future__ import annotations

from src.pipeline.models import DraftAlert
from src.pipeline.review import service as queue


class NotFound(LookupError):
    """The record is not waiting in the review queue."""


def _item(alert: DraftAlert) -> dict:
    payload = alert.as_drug_alert().model_dump()
    payload["status"] = alert.status.value
    payload["validation_errors"] = list(alert.validation_errors)
    payload["extraction_method"] = alert.extraction_method
    return payload


def pending() -> dict:
    items = [_item(alert) for alert in queue.pending()]
    return {"items": items, "total": len(items)}


def approve(record_id: str) -> dict:
    if not queue.approve(record_id):
        raise NotFound(record_id)
    return {"record_id": record_id, "status": "approved"}


def reject(record_id: str) -> dict:
    if not queue.reject(record_id):
        raise NotFound(record_id)
    return {"record_id": record_id, "status": "rejected"}


def update(record_id: str, fields: dict) -> dict:
    alert = queue.update(record_id, fields)
    if alert is None:
        raise NotFound(record_id)
    return _item(alert)


def remove(record_id: str) -> dict:
    if not queue.remove(record_id):
        raise NotFound(record_id)
    return {"record_id": record_id, "status": "deleted"}
