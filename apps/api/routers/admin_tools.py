"""Admin-only triggers for existing GitHub Actions collection workflows."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from ..core import content
from ..dependencies import ADMIN
from ..schemas.drugs import DrugsSyncResult
from ..schemas.tools import CollectionRunResult, CollectionToolsResponse
from ..services import collection_jobs, drugs

router = APIRouter(tags=["admin-tools"], dependencies=ADMIN)


@router.post("/api/admin/drugs/sync", response_model=DrugsSyncResult)
def sync_drugs() -> dict:
    """Reload the Atlas drug collection from the committed NCI JSON file."""
    try:
        payload = drugs.sync_from_file()
    except drugs.Missing as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=content.ERRORS["drugs_unavailable"],
        ) from error
    except drugs.StoreUnavailable as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=content.ERRORS["auth_store_unavailable"],
        ) from error
    return {
        "source": payload["source"],
        "source_url": payload["source_url"],
        "count": payload["count"],
        "storage": payload["storage"],
        "updated_at": payload.get("updated_at"),
    }


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
