"""Read the committed NCI oncology drug-name list."""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..core import settings

logger = logging.getLogger(__name__)

SOURCE_NAME = "NCI A–Z List of Cancer Drugs"


class Missing(RuntimeError):
    """The drug list file is absent or unreadable."""


def _display_name(slug: str) -> str:
    parts = [part for part in slug.replace("_", "-").split("-") if part]
    return "-".join(part[:1].upper() + part[1:] for part in parts) if parts else slug


def _letter(slug: str) -> str:
    for char in slug:
        if char.isalpha():
            return char.upper()
    return "#"


def _info_url(slug: str) -> str:
    return settings.NCI_DRUG_INFO_URL.format(slug=slug)


@lru_cache(maxsize=1)
def _load(path_key: str) -> tuple[dict[str, Any], ...]:
    path = Path(path_key)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        logger.warning("Drug list unreadable at %s: %s", path, error)
        raise Missing(str(path)) from error
    if not isinstance(raw, list):
        raise Missing(str(path))

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw:
        slug = str(item or "").strip().lower()
        if not slug or slug in seen:
            continue
        seen.add(slug)
        rows.append(
            {
                "id": slug,
                "name": _display_name(slug),
                "letter": _letter(slug),
                "info_url": _info_url(slug),
            }
        )
    rows.sort(key=lambda row: (row["letter"], row["name"].lower()))
    return tuple(rows)


def catalog() -> dict[str, Any]:
    path = settings.drugs_list_path()
    if not path.is_file():
        raise Missing(str(path))
    drugs = list(_load(str(path.resolve())))
    return {
        "source": SOURCE_NAME,
        "source_url": settings.NCI_DRUGS_SOURCE_URL,
        "count": len(drugs),
        "drugs": drugs,
        "path": path.name,
    }
