"""Draft alerts that carry validation and review state through the pipeline."""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from src.models import DrugAlert


class ReviewStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class RawCapture(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    source_org: str
    source_url: str
    collected_at: str
    content_type: str
    body_path: str
    meta: dict[str, Any] = Field(default_factory=dict)


class DraftAlert(DrugAlert):
    """A DrugAlert plus the fields the review gate needs."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    status: ReviewStatus = ReviewStatus.pending
    validation_errors: list[str] = Field(default_factory=list)
    extraction_method: str = "existing_scraper"
    raw_path: Optional[str] = None

    @classmethod
    def from_drug_alert(
        cls,
        alert: DrugAlert,
        *,
        extraction_method: str = "existing_scraper",
        raw_path: str | None = None,
    ) -> "DraftAlert":
        return cls(
            **alert.model_dump(),
            extraction_method=extraction_method,
            raw_path=raw_path,
        )

    def as_drug_alert(self) -> DrugAlert:
        return DrugAlert(**self.model_dump(include=set(DrugAlert.model_fields)))
