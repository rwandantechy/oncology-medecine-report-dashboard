"""Run every enabled source: collect → extract → validate → route."""

from __future__ import annotations

import logging
from typing import Any

from src.pipeline import settings
from src.pipeline.collectors.api import collect_api
from src.pipeline.collectors.browser import collect_browser_page
from src.pipeline.collectors.existing import run_existing_scraper
from src.pipeline.collectors.scrapy_runner import collect_with_scrapy
from src.pipeline.extract.api_map import map_api_payload
from src.pipeline.extract.page_text import draft_from_page_text
from src.pipeline.models import DraftAlert
from src.pipeline.review.service import route_alert
from src.pipeline.validate.checks import validate_alert

logger = logging.getLogger(__name__)


def process_source(source: dict[str, Any]) -> list[DraftAlert]:
    kind = (source.get("kind") or "").strip().lower()
    source_id = source.get("id") or ""
    source_org = source.get("org") or source_id

    if kind == "existing_scraper":
        alerts = run_existing_scraper(source.get("scraper") or "")
        return [
            DraftAlert.from_drug_alert(alert, extraction_method="existing_scraper")
            for alert in alerts
        ]

    if kind == "api":
        capture, payload = collect_api(
            source_id=source_id,
            source_org=source_org,
            url=source.get("url") or "",
            params=source.get("params") or {},
        )
        return map_api_payload(
            payload,
            source_id=source_id,
            source_org=source_org,
            source_url=capture.source_url,
            field_map=source.get("field_map") or {},
            results_path=source.get("results_path") or "results",
            raw_path=capture.body_path,
        )

    if kind == "browser":
        capture, html = collect_browser_page(
            source_id=source_id,
            source_org=source_org,
            url=source.get("url") or "",
        )
        return [
            draft_from_page_text(
                text=html,
                source_id=source_id,
                source_org=source_org,
                source_url=capture.source_url,
                raw_path=capture.body_path,
            )
        ]

    if kind == "scrapy":
        items = collect_with_scrapy(
            source_id=source_id,
            source_org=source_org,
            url=source.get("url") or "",
        )
        drafts: list[DraftAlert] = []
        for item in items:
            text = " ".join(
                part for part in [item.get("title"), item.get("body")] if part
            )
            drafts.append(
                draft_from_page_text(
                    text=text,
                    source_id=source_id,
                    source_org=source_org,
                    source_url=item.get("source_url") or source.get("url") or "",
                )
            )
        return drafts

    raise ValueError(
        f"Unknown source kind {kind!r} for {source_id}. "
        "Use existing_scraper, api, browser, or scrapy."
    )


def run_ingest() -> dict[str, int]:
    sources = settings.load_sources()
    seen: set[str] = set()
    summary = {"approved": 0, "review": 0, "errors": 0, "sources": 0}

    for source in sources:
        summary["sources"] += 1
        source_id = source.get("id") or "?"
        try:
            drafts = process_source(source)
        except Exception:
            logger.exception("Source %s failed", source_id)
            summary["errors"] += 1
            continue

        for draft in drafts:
            checked = validate_alert(draft, seen_ids=seen)
            seen.add(checked.record_id)
            bucket = route_alert(checked)
            summary[bucket] = summary.get(bucket, 0) + 1

    logger.info("Ingest finished: %s", summary)
    return summary


def ingest_flow():
    """Prefect entry when installed; otherwise a plain callable."""
    if settings.use_prefect():
        try:
            from prefect import flow

            @flow(name="oncosmart-ingest", log_prints=True)
            def _flow():
                return run_ingest()

            return _flow()
        except Exception as exc:
            logger.warning(
                "Prefect unavailable (%s: %s); running without it",
                type(exc).__name__,
                exc,
            )
    return run_ingest()
