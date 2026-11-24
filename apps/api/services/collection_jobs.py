"""Dispatch existing GitHub Actions workflows for collection tools."""

from __future__ import annotations

import json
import logging
import time
from typing import Any
from urllib import error, parse, request

from ..core import content, settings

logger = logging.getLogger(__name__)

_LAST_RUN_AT: dict[str, float] = {}

_WORKFLOW_BY_TOOL = {
    "weekly_scrape": lambda: settings.GITHUB_WORKFLOW_WEEKLY_SCRAPE,
    "drug_database": lambda: settings.GITHUB_WORKFLOW_DRUG_DATABASE,
}

_ACTIVE_STATUSES = frozenset({"queued", "waiting", "requested", "pending", "in_progress"})


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
        latest = _latest_run(tool_id) if ready else None
        active = bool(latest and latest["status"] in _ACTIVE_STATUSES)
        rows.append(
            {
                **meta,
                "configured": ready,
                "busy": ready and (active or (now - last) < cooldown),
                "latest_run": latest,
            }
        )
    return rows


def _headers(*, json_body: bool = False) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {settings.github_actions_token()}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "EveryDoseMatters-AdminTools",
    }
    if json_body:
        headers["Content-Type"] = "application/json"
    return headers


def _dispatch_url(workflow_file: str) -> str:
    repo = settings.github_actions_repo()
    return (
        f"{settings.GITHUB_API_URL}/repos/{repo}/actions/workflows/"
        f"{workflow_file}/dispatches"
    )


def _runs_url(workflow_file: str) -> str:
    repo = settings.github_actions_repo()
    query = parse.urlencode(
        {
            "per_page": "1",
            "branch": settings.GITHUB_ACTIONS_REF,
        }
    )
    return (
        f"{settings.GITHUB_API_URL}/repos/{repo}/actions/workflows/"
        f"{workflow_file}/runs?{query}"
    )


def _run_label(status: str, conclusion: str | None) -> str:
    if status in _ACTIVE_STATUSES:
        if status == "in_progress":
            return "In progress"
        return "Queued"
    if status == "completed":
        mapping = {
            "success": "Succeeded",
            "failure": "Failed",
            "cancelled": "Cancelled",
            "timed_out": "Timed out",
            "skipped": "Skipped",
        }
        return mapping.get(conclusion or "", "Completed")
    return status.replace("_", " ").title() if status else "Unknown"


def _latest_run(tool_id: str) -> dict[str, Any] | None:
    workflow = _WORKFLOW_BY_TOOL.get(tool_id)
    if not workflow:
        return None
    req = request.Request(_runs_url(workflow()), headers=_headers(), method="GET")
    try:
        with request.urlopen(req, timeout=12) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:200]
        logger.warning(
            "GitHub runs lookup failed for %s: %s %s",
            tool_id,
            exc.code,
            detail,
        )
        return None
    except (error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
        logger.warning("GitHub runs lookup transport error for %s: %s", tool_id, exc)
        return None

    runs = payload.get("workflow_runs") or []
    if not runs:
        return {
            "status": "none",
            "conclusion": None,
            "label": "No runs yet",
            "run_number": None,
            "html_url": None,
            "updated_at": None,
        }

    run = runs[0]
    status = str(run.get("status") or "")
    conclusion = run.get("conclusion")
    conclusion_s = str(conclusion) if conclusion else None
    return {
        "status": status,
        "conclusion": conclusion_s,
        "label": _run_label(status, conclusion_s),
        "run_number": run.get("run_number"),
        "html_url": run.get("html_url"),
        "updated_at": run.get("updated_at") or run.get("created_at"),
    }


def run(tool_id: str) -> dict[str, Any]:
    if tool_id not in _WORKFLOW_BY_TOOL:
        raise UnknownTool(tool_id)
    if not configured():
        raise NotConfigured("missing token or repo")

    now = time.monotonic()
    last = _LAST_RUN_AT.get(tool_id, 0.0)
    if (now - last) < settings.COLLECTION_JOB_COOLDOWN_SECONDS:
        raise ToolBusy(tool_id)

    latest = _latest_run(tool_id)
    if latest and latest["status"] in _ACTIVE_STATUSES:
        raise ToolBusy(tool_id)

    workflow = _WORKFLOW_BY_TOOL[tool_id]()
    url = _dispatch_url(workflow)
    payload = {"ref": settings.GITHUB_ACTIONS_REF}
    body = json.dumps(payload).encode()
    req = request.Request(url, data=body, headers=_headers(json_body=True), method="POST")
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
    # Dispatch is async; the new run may take a moment to appear in the list.
    refreshed = _latest_run(tool_id) or {
        "status": "queued",
        "conclusion": None,
        "label": "Queued",
        "run_number": None,
        "html_url": actions_url(),
        "updated_at": None,
    }
    return {
        "tool_id": tool_id,
        "status": "queued",
        "message": f"{label} was started. Progress updates below.",
        "actions_url": refreshed.get("html_url") or actions_url(),
        "latest_run": refreshed,
    }
