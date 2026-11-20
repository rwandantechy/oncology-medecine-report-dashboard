"""Map known API JSON shapes onto DraftAlert using field paths from the sources file."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from src.pipeline.models import DraftAlert


def make_record_id(source_id: str, product_name: str, source_key: str) -> str:
    raw = "||".join([source_id, product_name or "", source_key])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _dig(item: dict[str, Any], path: str | None) -> Any:
    if not path:
        return None
    current: Any = item
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def map_api_item(
    item: dict[str, Any],
    *,
    source_id: str,
    source_org: str,
    source_url: str,
    field_map: dict[str, str],
    raw_path: str | None = None,
) -> DraftAlert:
    """Build a draft from an API item using a per-source field map.

    ``field_map`` keys are DraftAlert fields; values are dotted paths into the
    JSON item. ``record_key`` selects the stable source identifier used in
    ``record_id``.
    """
    product = _dig(item, field_map.get("product_name"))
    if isinstance(product, str):
        product = product.strip() or None
    source_key = _dig(item, field_map.get("record_key")) or product or source_url
    publish_date = _dig(item, field_map.get("publish_date"))
    if publish_date is not None:
        publish_date = str(publish_date)

    return DraftAlert(
        record_id=make_record_id(source_id, product or "", str(source_key)),
        source_id=source_id,
        source_org=source_org,
        source_url=_dig(item, field_map.get("source_url")) or source_url,
        product_name=product,
        source_country=_dig(item, field_map.get("source_country")),
        manufacturer=_dig(item, field_map.get("manufacturer")),
        distributor=_dig(item, field_map.get("distributor")),
        publish_date=publish_date,
        reason=_dig(item, field_map.get("reason")),
        more_info=_dig(item, field_map.get("more_info")),
        scraped_at=datetime.now(timezone.utc).isoformat(),
        extraction_method="api_map",
        raw_path=raw_path,
    )


def map_api_payload(
    payload: Any,
    *,
    source_id: str,
    source_org: str,
    source_url: str,
    field_map: dict[str, str],
    results_path: str = "results",
    raw_path: str | None = None,
) -> list[DraftAlert]:
    items = _dig(payload, results_path) if isinstance(payload, dict) else payload
    if items is None and isinstance(payload, list):
        items = payload
    if not isinstance(items, list):
        return []
    return [
        map_api_item(
            item,
            source_id=source_id,
            source_org=source_org,
            source_url=source_url,
            field_map=field_map,
            raw_path=raw_path,
        )
        for item in items
        if isinstance(item, dict)
    ]
