"""Shapes for admin collection tools."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class CollectionTool(BaseModel):
    id: str
    label: str
    description: str
    configured: bool
    busy: bool = False


class CollectionToolsResponse(BaseModel):
    configured: bool
    tools: list[CollectionTool]
    actions_url: Optional[str] = None


class CollectionRunResult(BaseModel):
    tool_id: str
    status: str = Field(description="queued when GitHub accepted the dispatch")
    message: str
    actions_url: Optional[str] = None
