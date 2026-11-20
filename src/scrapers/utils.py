"""Utility helpers shared by scrapers."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin

# Leading words that appear in NCI or FDA text but are not medication identities.
# Matching these alone caused non-oncology products (e.g. sterile eye drops) to pass.
NON_DRUG_LEADING_TOKENS = frozenset(
    {
        "sterile",
        "sterility",
        "water",
        "diluent",
        "solution",
        "injection",
        "injectable",
        "oral",
        "topical",
        "ophthalmic",
        "ophthalmology",
        "eye",
        "drops",
        "drop",
        "lubricant",
        "lubricating",
        "for",
        "with",
        "and",
        "the",
        "usp",
        "nf",
        "rx",
        "only",
    }
)


def absolutize(base_url: str, href: str) -> str:
    """Join two urls."""

    return urljoin(base_url, href)


def parse_date(value: Optional[str]) -> Optional[datetime]:
    """Parse various date formats encountered in NAFDAC/FDA pages."""

    if not value:
        return None

    value = value.strip()

    # --- 1) Month-Year formats (10-2020, 10/2020) ---
    month_year = re.sub(r"[\/]", "-", value)
    if re.fullmatch(r"\d{2}-\d{4}", month_year):
        try:
            return datetime.strptime(month_year, "%m-%Y")
        except ValueError:
            pass

    # --- 2) NAFDAC-style day-month-year formats ---
    for fmt in ("%d-%b-%y", "%d-%b-%Y", "%d-%B-%y", "%d-%B-%Y"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass

    # --- 3) ISO / ISO-like formats ---
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def normalize_drug_name(name: str) -> str:
    """Normalize drug name according to NCI.

    Hyphens are preserved — NCI and FDA use them in regimen and biologic
    names (e.g. ``amivantamab-vmjw``, ``r-chop``, ``5-fu``).
    """

    if not name:
        return ""

    name = name.lower()

    name = re.sub(r"[®™©]", "", name)

    # remove dosage (e.g., 500mg, 10 ml, etc.)
    name = re.sub(r"\b\d+(\.\d+)?\s*(mg|mcg|g|ml|%)\b", "", name)

    # keep letters, digits, hyphens, and spaces; drop other punctuation
    name = re.sub(r"[^a-z0-9\s\-]", " ", name)
    name = re.sub(r"-+", "-", name)
    name = re.sub(r"\s+", " ", name).strip(" -")

    return name


def _clean_drug_token(raw: str) -> str | None:
    """Normalize a single whitespace-delimited token for allowlist use."""

    token = raw.lower().strip(" ,;:./")
    token = re.sub(r"[^a-z0-9\-]", "", token)
    token = re.sub(r"-+", "-", token).strip("-")
    if not token or token in NON_DRUG_LEADING_TOKENS:
        return None
    return token


def extract_drug_token(text: str) -> str | None:
    """Return the first medication-like token from an official NCI list label.

    Skips non-drug leading descriptors so names like "Sterile Talc Powder"
    yield ``talc`` rather than poisoning the allowlist with ``sterile``.
    Hyphenated NCI names (e.g. ``Ado-Trastuzumab``, ``ABVE-PC``) are kept intact.
    """

    if not text:
        return None

    cleaned = re.sub(r"[()]", " ", text)
    for raw in cleaned.split():
        token = _clean_drug_token(raw)
        if token:
            return token
    return None


def match_oncology_token(text: str, approved_drugs: list[str] | set[str]) -> str | None:
    """Match ``text`` against the oncology allowlist, skipping descriptor tokens."""

    if not text or not approved_drugs:
        return None

    approved = set(approved_drugs)
    normalized = normalize_drug_name(text)
    if not normalized:
        return None

    # Exact phrase hit (rare; mostly single hyphenated tokens).
    if normalized in approved and normalized not in NON_DRUG_LEADING_TOKENS:
        return normalized.capitalize()

    for token in normalized.split():
        cleaned = _clean_drug_token(token)
        if cleaned and cleaned in approved:
            return cleaned.capitalize()
    return None


def read_json(file_path: str) -> dict:
    """Read a json file."""

    with open(file_path, "r") as file:
        data = json.load(file)
    return data
