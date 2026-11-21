"""Rewrite machine JSON endpoints to doctor-readable regulator HTML pages."""

from __future__ import annotations

from typing import Any, Mapping, MutableMapping

from src.scrapers.utils import normalize_source_url


def with_official_source_url(record: Mapping[str, Any]) -> dict[str, Any]:
    """Return a copy of ``record`` with ``source_url`` normalized when present."""

    payload = dict(record)
    if "source_url" in payload:
        payload["source_url"] = normalize_source_url(
            payload.get("source_id"),
            payload.get("source_url"),
        )
    return payload


def map_official_source_urls(records: list[MutableMapping[str, Any]] | list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [with_official_source_url(record) for record in records]
