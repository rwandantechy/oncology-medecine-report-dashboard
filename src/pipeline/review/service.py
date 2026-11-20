"""Approve, reject, and list drafts that failed automatic checks."""

from __future__ import annotations

from src.pipeline import settings
from src.pipeline.models import DraftAlert, ReviewStatus
from src.pipeline.storage import db


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
