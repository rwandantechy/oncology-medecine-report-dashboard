"""Browser collector for regulator pages that need rendering."""

from __future__ import annotations

import asyncio

from src.pipeline.models import RawCapture
from src.pipeline.storage.raw import save_original


async def _crawl(url: str) -> str:
    try:
        from crawl4ai import AsyncWebCrawler
    except ImportError as exc:
        raise RuntimeError(
            "crawl4ai is not installed. Run: uv sync --extra pipeline && playwright install"
        ) from exc

    async with AsyncWebCrawler(verbose=False) as crawler:
        result = await crawler.arun(url=url)
        if not getattr(result, "success", True):
            message = getattr(result, "error_message", None) or f"Crawl failed for {url}"
            raise RuntimeError(message)
        return result.html or result.cleaned_html or ""


def collect_browser_page(
    *,
    source_id: str,
    source_org: str,
    url: str,
) -> tuple[RawCapture, str]:
    if not url:
        raise ValueError(f"Source {source_id} has no url configured")

    html = asyncio.run(_crawl(url))
    capture = save_original(
        source_id=source_id,
        source_org=source_org,
        source_url=url,
        body=html,
        content_type="text/html",
        meta={"collector": "crawl4ai"},
    )
    return capture, html
