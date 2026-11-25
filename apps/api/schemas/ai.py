"""Shapes for admin AI provider controls."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class AiProviderOption(BaseModel):
    name: str
    label: str
    model: str
    configured: bool
    available: bool


class AiSettingsResponse(BaseModel):
    enabled: bool
    primary: str
    fallback: Optional[str] = None
    chain: list[str]
    source: str = Field(description="admin when overridden in Atlas, otherwise env")
    options: list[AiProviderOption]


class AiSettingsUpdate(BaseModel):
    primary: str = Field(min_length=1)
    fallback: Optional[str] = None
