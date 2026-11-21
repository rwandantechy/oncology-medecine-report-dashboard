"""Approve, reject, update, and list drafts that failed automatic checks."""

from __future__ import annotations

from typing import Any

from src.pipeline import settings
from src.pipeline.models import DraftAlert, ReviewStatus
from src.pipeline.storage import db
from src.pipeline.validate.checks import validate_alert

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


def route_alert(alert: DraftAlert) -> str:
    """Persist a draft to the approved table or the review queue."""
    with db.connect() as connection:
        db.ensure_schema(connection)
        if (
            settings.auto_approve_valid()
            and alert.status == ReviewStatus.approved
            and not alert.validation_errors
        ):
            db.upsert_approved(connection, alert)
            connection.commit()
            return "approved"

        alert.status = ReviewStatus.pending
        db.upsert_review(connection, alert)
        connection.commit()
        return "review"


def pending() -> list[DraftAlert]:
    with db.connect() as connection:
        db.ensure_schema(connection)
        return db.list_pending(connection)


def approve(record_id: str) -> bool:
    with db.connect() as connection:
        db.ensure_schema(connection)
        alert = db.get_review(connection, record_id)
        if alert is None:
            return False
        alert.status = ReviewStatus.approved
        alert.validation_errors = []
        db.upsert_approved(connection, alert)
        db.set_review_status(connection, record_id, ReviewStatus.approved)
        connection.commit()
        return True


def reject(record_id: str) -> bool:
    with db.connect() as connection:
        db.ensure_schema(connection)
        alert = db.get_review(connection, record_id)
        if alert is None:
            return False
        db.set_review_status(connection, record_id, ReviewStatus.rejected)
        connection.commit()
        return True


def update(record_id: str, fields: dict[str, Any]) -> DraftAlert | None:
    """Update editable fields on a pending review draft and re-validate."""
    payload = {key: fields[key] for key in EDITABLE_FIELDS if key in fields}
    if not payload:
        return None

    with db.connect() as connection:
        db.ensure_schema(connection)
        alert = db.get_review(connection, record_id)
        if alert is None or alert.status != ReviewStatus.pending:
            return None

        for key, value in payload.items():
            if isinstance(value, str):
                value = value.strip() or None
            setattr(alert, key, value)

        seen = {record_id} if db.approved_exists(connection, record_id) else set()
        validate_alert(alert, seen_ids=seen or None)
        alert.status = ReviewStatus.pending
        db.upsert_review(connection, alert)
        connection.commit()
        return alert


def remove(record_id: str) -> bool:
    """Hard-delete a draft from the review queue."""
    with db.connect() as connection:
        db.ensure_schema(connection)
        alert = db.get_review(connection, record_id)
        if alert is None or alert.status != ReviewStatus.pending:
            return False
        ok = db.delete_review(connection, record_id)
        connection.commit()
        return ok
