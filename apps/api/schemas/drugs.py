"""Shapes for the NCI oncology drug list."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class DrugItem(BaseModel):
    id: str
    name: str
    letter: str = Field(min_length=1, max_length=1)
    info_url: str


class DrugsResponse(BaseModel):
    source: str
    source_url: str
    count: int
    drugs: list[DrugItem]
    path: Optional[str] = None
