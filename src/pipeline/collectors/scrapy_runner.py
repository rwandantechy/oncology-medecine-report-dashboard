"""Thin Scrapy entry for stable, structured regulator sites.

Source URL comes from the sources file. Install the optional pipeline extras
before using this collector.
"""

from __future__ import annotations

from typing import Any

from src.pipeline import settings
from src.pipeline.storage.raw import save_original


def collect_with_scrapy(
    *,
    source_id: str,
    source_org: str,
    url: str,
) -> list[dict[str, Any]]:
    if not url:
        raise ValueError(f"Source {source_id} has no url configured")

    try:
        import scrapy
        from scrapy.crawler import CrawlerProcess
    except ImportError as exc:
        raise RuntimeError(
            "scrapy is not installed. Run: uv sync --extra pipeline"
        ) from exc

    collected: list[dict[str, Any]] = []

    class _ListSpider(scrapy.Spider):
        name = f"pipeline_{source_id}"

        def start_requests(self):
            yield scrapy.Request(url, callback=self.parse)

        def parse(self, response):
            save_original(
                source_id=source_id,
                source_org=source_org,
                source_url=response.url,
                body=response.text,
                content_type="text/html",
                meta={"collector": "scrapy", "status": response.status},
            )
            item = {
                "source_url": response.url,
                "title": response.css("h1::text").get(),
                "body": " ".join(response.css("p::text").getall()),
            }
            collected.append(item)
            yield item

    process = CrawlerProcess(
        settings={
            "LOG_ENABLED": False,
            "ROBOTSTXT_OBEY": True,
            "USER_AGENT": settings.user_agent(),
        }
    )
    process.crawl(_ListSpider)
    process.start()
    return collected
