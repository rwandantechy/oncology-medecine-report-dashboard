"""Admin-only triggers for existing GitHub Actions collection workflows."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from ..core import content
from ..dependencies import ADMIN
from ..schemas.tools import CollectionRunResult, CollectionToolsResponse
from ..services import collection_jobs

router = APIRouter(tags=["admin-tools"], dependencies=ADMIN)


@router.get("/api/admin/tools", response_model=CollectionToolsResponse)
def list_tools() -> dict:
    return {
        "configured": collection_jobs.configured(),
        "tools": collection_jobs.catalog(),
        "actions_url": collection_jobs.actions_url(),
    }


@router.post("/api/admin/tools/{tool_id}/run", response_model=CollectionRunResult)
def run_tool(tool_id: str) -> dict:
    try:
        return collection_jobs.run(tool_id)
    except collection_jobs.UnknownTool as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=content.ERRORS["tool_unknown"],
        ) from error
    except collection_jobs.NotConfigured as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=content.ERRORS["tools_not_configured"],
        ) from error
    except collection_jobs.ToolBusy as error:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=content.ERRORS["tool_busy"],
        ) from error
    except collection_jobs.DispatchFailed as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=content.ERRORS["tool_dispatch_failed"],
        ) from error
