"""Dispatch existing GitHub Actions workflows for collection tools."""

from __future__ import annotations

import json
import logging
import time
from typing import Any
from urllib import error, request

from ..core import content, settings

logger = logging.getLogger(__name__)

_LAST_RUN_AT: dict[str, float] = {}

_WORKFLOW_BY_TOOL = {
    "weekly_scrape": lambda: settings.GITHUB_WORKFLOW_WEEKLY_SCRAPE,
    "drug_database": lambda: settings.GITHUB_WORKFLOW_DRUG_DATABASE,
}


class NotConfigured(RuntimeError):
    """Token or repo is missing, so jobs cannot be dispatched."""


class UnknownTool(RuntimeError):
    """The requested tool id is not in the catalog."""


class ToolBusy(RuntimeError):
    """A run was started too recently for this tool."""


class DispatchFailed(RuntimeError):
    """GitHub rejected or failed the workflow_dispatch call."""


def configured() -> bool:
    return bool(settings.github_actions_token() and settings.github_actions_repo())


def actions_url() -> str | None:
    repo = settings.github_actions_repo()
    if not repo:
        return None
    return f"https://github.com/{repo}/actions"


def catalog() -> list[dict[str, Any]]:
    ready = configured()
    now = time.monotonic()
    cooldown = settings.COLLECTION_JOB_COOLDOWN_SECONDS
    rows: list[dict[str, Any]] = []
    for tool_id, meta in content.TOOLS.items():
        last = _LAST_RUN_AT.get(tool_id, 0.0)
        rows.append(
            {
                **meta,
                "configured": ready,
                "busy": ready and (now - last) < cooldown,
            }
        )
    return rows


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.github_actions_token()}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "EveryDoseMatters-AdminTools",
        "Content-Type": "application/json",
    }


def _dispatch_url(workflow_file: str) -> str:
    repo = settings.github_actions_repo()
    return (
        f"{settings.GITHUB_API_URL}/repos/{repo}/actions/workflows/"
        f"{workflow_file}/dispatches"
    )


def run(tool_id: str) -> dict[str, Any]:
    if tool_id not in _WORKFLOW_BY_TOOL:
        raise UnknownTool(tool_id)
    if not configured():
        raise NotConfigured("missing token or repo")

    now = time.monotonic()
    last = _LAST_RUN_AT.get(tool_id, 0.0)
    if (now - last) < settings.COLLECTION_JOB_COOLDOWN_SECONDS:
        raise ToolBusy(tool_id)

    workflow = _WORKFLOW_BY_TOOL[tool_id]()
    url = _dispatch_url(workflow)
    payload = {"ref": settings.GITHUB_ACTIONS_REF}
    body = json.dumps(payload).encode()
    req = request.Request(url, data=body, headers=_headers(), method="POST")
    try:
        with request.urlopen(req, timeout=20) as response:
            status_code = getattr(response, "status", 200)
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        logger.warning(
            "GitHub dispatch rejected for %s: %s %s",
            tool_id,
            exc.code,
            detail,
        )
        raise DispatchFailed(f"status {exc.code}") from exc
    except error.URLError as exc:
        logger.warning("GitHub dispatch transport error for %s: %s", tool_id, exc)
        raise DispatchFailed(str(exc.reason)) from exc

    if status_code not in (200, 201, 204):
        raise DispatchFailed(f"status {status_code}")

    _LAST_RUN_AT[tool_id] = time.monotonic()
    label = content.TOOLS[tool_id]["label"]
    return {
        "tool_id": tool_id,
        "status": "queued",
        "message": f"{label} was started. Check GitHub Actions for progress.",
        "actions_url": actions_url(),
    }
