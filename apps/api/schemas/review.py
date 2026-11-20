"""Shapes for the notice review queue."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict


class ReviewItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    record_id: str
    source_id: str
    source_org: str
    source_url: str
    product_name: Optional[str] = None
    source_country: Optional[str] = None
    manufacturer: Optional[str] = None
    distributor: Optional[str] = None
    publish_date: Optional[str] = None
    scraped_at: str
    reason: Optional[str] = None
    more_info: Optional[str] = None
    status: str
    validation_errors: list[str]
    extraction_method: str


class ReviewPage(BaseModel):
    items: list[ReviewItem]
    total: int


class ReviewActionResult(BaseModel):
    record_id: str
    status: str
