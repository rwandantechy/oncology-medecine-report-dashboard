"""Write-once storage for original API and page responses."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

from src.pipeline.models import RawCapture
from src.pipeline import settings


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def save_original(
    *,
    source_id: str,
    source_org: str,
    source_url: str,
    body: str | bytes,
    content_type: str,
    meta: dict[str, Any] | None = None,
) -> RawCapture:
    """Persist the untouched response next to a small metadata sidecar."""
    root = settings.raw_dir()
    root.mkdir(parents=True, exist_ok=True)
    payload = body if isinstance(body, bytes) else body.encode("utf-8", errors="replace")
    digest = sha256(payload).hexdigest()[:16]
    folder = root / source_id / _stamp()
    folder.mkdir(parents=True, exist_ok=True)

    suffix = ".json" if "json" in content_type.lower() else ".html"
    body_path = folder / f"{digest}{suffix}"
    body_path.write_bytes(payload)

    capture = RawCapture(
        source_id=source_id,
        source_org=source_org,
        source_url=source_url,
        collected_at=datetime.now(timezone.utc).isoformat(),
        content_type=content_type,
        body_path=str(body_path),
        meta=meta or {},
    )
    (folder / f"{digest}.meta.json").write_text(
        capture.model_dump_json(indent=2),
        encoding="utf-8",
    )
    return capture


def read_body(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8", errors="replace")


def read_json_body(path: str | Path) -> Any:
    return json.loads(read_body(path))
