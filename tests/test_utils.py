"""Unit tests for src.scrapers.utils."""

from datetime import datetime
from pathlib import Path

import pytest

# --- absolutize ---


def test_absolutize_relative_path(utils_mod):
    assert (
        utils_mod.absolutize("https://example.com/page/", "sub") == "https://example.com/page/sub"
    )
    assert (
        utils_mod.absolutize("https://example.com/", "recalls/123")
        == "https://example.com/recalls/123"
    )


def test_absolutize_absolute_url(utils_mod):
    base = "https://example.com/page/"
    href = "https://other.com/path"
    assert utils_mod.absolutize(base, href) == "https://other.com/path"


# --- parse_date ---


def test_parse_date_handles_listing_and_month_year(utils_mod):
    parse_date = utils_mod.parse_date

    # NAFDAC listing style
    assert parse_date("15-Oct-25") == datetime(2025, 10, 15)
    assert parse_date("15-October-2025") == datetime(2025, 10, 15)

    # ISO-ish
    assert parse_date("2026-01-09") == datetime(2026, 1, 9)

    # Month/year with - or /
    assert parse_date("10-2020") == datetime(2020, 10, 1)
    assert parse_date("10/2020") == datetime(2020, 10, 1)

    # None/empty
    assert parse_date("") is None
    assert parse_date(None) is None


def test_parse_date_invalid_returns_none(utils_mod):
    assert utils_mod.parse_date("not-a-date") is None
    assert utils_mod.parse_date("32-13-2020") is None


# --- normalize_drug_name ---


def test_normalize_drug_name_empty(utils_mod):
    assert utils_mod.normalize_drug_name("") == ""
    assert utils_mod.normalize_drug_name(None) == ""


def test_normalize_drug_name_removes_dosage(utils_mod):
    assert "500mg" not in utils_mod.normalize_drug_name("Darzalex 500mg")
    assert "10 ml" not in utils_mod.normalize_drug_name("Drug 10 ml")


def test_normalize_drug_name_removes_trademarks(utils_mod):
    assert "®" not in utils_mod.normalize_drug_name("Darzalex®")
    assert "™" not in utils_mod.normalize_drug_name("Drug™")


def test_normalize_drug_name_lowercase_and_clean(utils_mod):
    result = utils_mod.normalize_drug_name("HERCEPTIN 600mg/5ml")
    assert result == "herceptin"


# --- extract_drug_token ---


def test_extract_drug_token_empty(utils_mod):
    assert utils_mod.extract_drug_token("") is None
    assert utils_mod.extract_drug_token(None) is None


def test_extract_drug_token_removes_parentheses_keeps_content(utils_mod):
    token = utils_mod.extract_drug_token("Darzalex (Daratumumab)")
    assert "darzalex" == token


def test_extract_drug_token_lowercase(utils_mod):
    token = utils_mod.extract_drug_token("HERCEPTIN Trastuzumab")
    assert "herceptin" == token


def test_extract_drug_token_skips_sterile_descriptor(utils_mod):
    assert utils_mod.extract_drug_token("Sterile Talc Powder") == "talc"
    assert utils_mod.extract_drug_token("Sterile Water for Injection") is None


def test_extract_drug_token_preserves_nci_hyphens(utils_mod):
    assert utils_mod.extract_drug_token("Ado-Trastuzumab Emtansine") == "ado-trastuzumab"
    assert utils_mod.extract_drug_token("Amivantamab-vmjw") == "amivantamab-vmjw"
    assert utils_mod.extract_drug_token("5-FU (Fluorouracil Injection)") == "5-fu"
    assert utils_mod.extract_drug_token("ABVE-PC") == "abve-pc"
    assert (
        utils_mod.extract_drug_token("Pertuzumab, Trastuzumab, and Hyaluronidase-zzxf")
        == "pertuzumab"
    )


def test_normalize_drug_name_preserves_hyphens(utils_mod):
    assert utils_mod.normalize_drug_name("Amivantamab-vmjw") == "amivantamab-vmjw"
    assert utils_mod.normalize_drug_name("R-CHOP") == "r-chop"


def test_match_oncology_token_rejects_sterile_eye_drops(utils_mod):
    approved = ["talc", "azacitidine", "herceptin"]
    assert (
        utils_mod.match_oncology_token(
            "Sterile Eye Drops Redness Relief",
            approved,
        )
        is None
    )


def test_match_oncology_token_accepts_sterile_talc(utils_mod):
    approved = ["talc", "azacitidine"]
    assert utils_mod.match_oncology_token("Sterile Talc Powder", approved) == "Talc"


def test_match_oncology_token_accepts_hyphenated_biologic(utils_mod):
    approved = ["amivantamab-vmjw", "azacitidine"]
    assert (
        utils_mod.match_oncology_token("Amivantamab-vmjw Injection", approved)
        == "Amivantamab-vmjw"
    )


def test_match_oncology_token_rejects_ac_eye_drops_and_pepcid(utils_mod):
    approved = ["ac", "azacitidine", "mitomycin"]
    assert utils_mod.match_oncology_token("Sterile EYE DROPS AC", approved) is None
    assert utils_mod.match_oncology_token("PEPCID AC MAXIMUM STRENGTH", approved) is None
    assert utils_mod.match_oncology_token("Guaiatussin AC Sugar-Free", approved) is None
    assert utils_mod.match_oncology_token("HUMAN CHORIONIC GONADOTROPIN", approved) is None
    assert utils_mod.match_oncology_token("Mitomycin 0.04% Ophth DR eye drops", approved) is None


def test_match_oncology_token_accepts_leading_ac_regimen(utils_mod):
    approved = ["ac", "ac-t"]
    assert utils_mod.match_oncology_token("AC", approved) == "Ac"
    assert utils_mod.match_oncology_token("AC-T", approved) == "Ac-t"


def test_match_oncology_token_accepts_direct_oncology_name(utils_mod):
    approved = ["azacitidine", "herceptin"]
    assert utils_mod.match_oncology_token("Azacitidine Injection", approved) == "Azacitidine"


def test_normalize_source_url_rewrites_openfda_json(utils_mod):
    html = utils_mod.normalize_source_url(
        "FDA_US",
        "https://api.fda.gov/drug/enforcement.json?search=event_id:86749",
    )
    assert html == "https://www.accessdata.fda.gov/scripts/ires/index.cfm?Event=86749"


def test_normalize_source_url_keeps_html(utils_mod):
    url = "https://nafdac.gov.ng/public-alert-no-011-2023-alert-on-confirmed-counterfeit-herceptin/"
    assert utils_mod.normalize_source_url("NAFDAC_NG", url) == url


def test_nci_json_matches_authoritative_tokens():
    from pathlib import Path

    from src.scrapers.utils import NON_DRUG_LEADING_TOKENS, read_json

    path = Path(__file__).resolve().parents[1] / "src" / "data" / "nci_oncology_drugs.json"
    drugs = read_json(str(path))
    assert "sterile" not in drugs
    assert "talc" in drugs
    assert "ado-trastuzumab" in drugs
    assert "amivantamab-vmjw" in drugs
    assert "5-fu" in drugs
    assert "abve-pc" in drugs
    assert "pertuzumab," not in drugs
    assert not (set(drugs) & NON_DRUG_LEADING_TOKENS)


# --- read_json ---


def test_read_json_valid_file(utils_mod):
    path = Path(__file__).parent / "test_files" / "fda_result.json"
    data = utils_mod.read_json(str(path))
    assert isinstance(data, dict)
    assert "meta" in data
    assert "results" in data


def test_read_json_file_not_found(utils_mod):
    with pytest.raises(FileNotFoundError):
        utils_mod.read_json("/nonexistent/path.json")
