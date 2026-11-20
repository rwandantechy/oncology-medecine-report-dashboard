"""Generic JSON API collector. Source URL and params come from the sources file."""

from __future__ import annotations

from typing import Any

import requests

from src.pipeline import settings
from src.pipeline.models import RawCapture
from src.pipeline.storage.raw import save_original


def collect_api(
    *,
    source_id: str,
    source_org: str,
    url: str,
    params: dict[str, Any] | None = None,
) -> tuple[RawCapture, Any]:
    if not url:
        raise ValueError(f"Source {source_id} has no url configured")

    response = requests.get(
        url,
        params=params or {},
        timeout=settings.http_timeout(),
        headers={
            "User-Agent": settings.user_agent(),
            "Accept": "application/json",
        },
    )
    response.raise_for_status()
    capture = save_original(
        source_id=source_id,
        source_org=source_org,
        source_url=str(response.url),
        body=response.text,
        content_type=response.headers.get("Content-Type", "application/json"),
        meta={"status_code": response.status_code, "collector": "api"},
    )
    return capture, response.json()
