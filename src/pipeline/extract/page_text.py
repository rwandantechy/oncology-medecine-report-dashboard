"""Draft fields from page text using the same AI provider settings as the API."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from urllib import request

from src.pipeline import settings
from src.pipeline.extract.api_map import make_record_id
from src.pipeline.models import DraftAlert

logger = logging.getLogger(__name__)

_PROMPT = (
    "Extract one medicine safety notice as JSON with keys: "
    "product_name, source_country, manufacturer, distributor, "
    "publish_date (YYYY-MM-DD or null), reason, more_info. "
    "Use null when unknown. Return JSON only.\n\nTEXT:\n"
)


def draft_from_page_text(
    *,
    text: str,
    source_id: str,
    source_org: str,
    source_url: str,
    raw_path: str | None = None,
) -> DraftAlert:
    extracted = _generate(text)
    product = extracted.get("product_name")
    if isinstance(product, str):
        product = product.strip() or None

    return DraftAlert(
        record_id=make_record_id(source_id, product or "", source_url),
        source_id=source_id,
        source_org=source_org,
        source_url=source_url,
        product_name=product,
        source_country=extracted.get("source_country"),
        manufacturer=extracted.get("manufacturer"),
        distributor=extracted.get("distributor"),
        publish_date=extracted.get("publish_date"),
        reason=extracted.get("reason"),
        more_info=extracted.get("more_info"),
        scraped_at=datetime.now(timezone.utc).isoformat(),
        extraction_method="langextract_ollama",
        raw_path=raw_path,
    )


def _generate(text: str) -> dict:
    clipped = text[: settings.extract_max_chars()]
    prompt = _PROMPT + clipped
    try:
        from apps.api.services import ai_providers

        provider = ai_providers.active_provider()
        if not provider.configured:
            raise ai_providers.ProviderError("AI provider is not configured")
        return provider.generate_json(
            prompt,
            timeout=settings.extract_timeout(),
            max_output_tokens=settings.extract_max_tokens(),
        )
    except Exception as exc:
        logger.warning(
            "Shared AI provider unavailable (%s); using OLLAMA_URL helper",
            type(exc).__name__,
        )
        return _ollama_generate(prompt)


def _ollama_generate(prompt: str) -> dict:
    url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
    model = os.getenv("OLLAMA_MODEL", "qwen3:0.6b")
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0, "num_predict": settings.extract_max_tokens()},
    }
    body = json.dumps(payload).encode()
    req = request.Request(
        f"{url}/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=settings.extract_timeout()) as response:
        data = json.loads(response.read())
    raw = data.get("response") or "{}"
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        if start < 0 or end <= start:
            raise
        return json.loads(raw[start : end + 1])
