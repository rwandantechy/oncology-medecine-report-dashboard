"""Required-field and date-shape checks driven by pipeline settings."""

from __future__ import annotations

import re

from src.pipeline import settings
from src.pipeline.models import DraftAlert, ReviewStatus


def validate_alert(alert: DraftAlert, seen_ids: set[str] | None = None) -> DraftAlert:
    errors: list[str] = []

    if settings.require_product_name() and not alert.product_name:
        errors.append("missing product_name")
    if settings.require_reason() and not alert.reason:
        errors.append("missing reason")
    if settings.require_publish_date():
        if not alert.publish_date:
            errors.append("missing publish_date")
        elif not re.match(settings.date_pattern(), alert.publish_date):
            errors.append("publish_date must match PIPELINE_DATE_PATTERN")

    if seen_ids is not None and alert.record_id in seen_ids:
        errors.append("duplicate record_id")

    alert.validation_errors = errors
    alert.status = ReviewStatus.pending if errors else ReviewStatus.approved
    return alert
