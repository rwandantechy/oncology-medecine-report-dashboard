"""Research workspace reads. Every route here requires a verified access token."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from ..core import content, settings
from ..dependencies import WORKSPACE
from ..schemas.drugs import DrugsResponse
from ..schemas.research import ResearchQuestion
from ..schemas.review import ReviewActionResult, ReviewItem, ReviewPage, ReviewUpdate
from ..services import alerts, drugs, insights, research, review

router = APIRouter(tags=["workspace"], dependencies=WORKSPACE)


@router.get("/api/drugs", response_model=DrugsResponse)
def oncology_drugs() -> dict:
    """NCI oncology drug names used for notice matching."""
    try:
        return drugs.catalog()
    except drugs.Missing as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=content.ERRORS["drugs_unavailable"],
        ) from error


@router.get("/api/dataset")
def dataset() -> dict:
    found = insights.dataset()
    if found is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=content.ERRORS["no_active_snapshot"],
        )
    return found


@router.get("/api/insights/summary")
def insights_summary() -> dict:
    return insights.summary()


@router.get("/api/insights/sources")
def insight_sources() -> list[dict]:
    return insights.sources()


@router.get("/api/insights/timeline")
def insight_timeline() -> dict:
    return insights.timeline()


@router.get("/api/insights/completeness")
def insight_completeness() -> list[dict]:
    return insights.completeness()


@router.get("/api/insights/research")
def insight_research() -> dict:
    return insights.research_brief()


@router.get("/api/insights/report.csv")
def download_report() -> StreamingResponse:
    return StreamingResponse(
        iter([alerts.report_csv()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={settings.REPORT_FILENAME}"},
    )


@router.post("/api/research/ask")
def ask_research_question(payload: ResearchQuestion) -> dict:
    return research.answer(payload.question.strip())


@router.get("/api/review/pending", response_model=ReviewPage)
def review_pending() -> dict:
    return review.pending()


def _review_write_error(error: Exception) -> HTTPException:
    if isinstance(error, review.WriteUnavailable):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error) or content.ERRORS["review_write_unavailable"],
        )
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=content.ERRORS["review_not_found"],
    )


@router.patch("/api/review/{record_id}", response_model=ReviewItem)
def review_update(record_id: str, payload: ReviewUpdate) -> dict:
    fields = payload.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=content.ERRORS["invalid_request"].format(reason="no fields to update"),
        )
    try:
        return review.update(record_id, fields)
    except (review.NotFound, review.WriteUnavailable) as error:
        raise _review_write_error(error) from error


@router.post("/api/review/{record_id}/approve", response_model=ReviewActionResult)
def review_approve(record_id: str) -> dict:
    try:
        return review.approve(record_id)
    except (review.NotFound, review.WriteUnavailable) as error:
        raise _review_write_error(error) from error


@router.post("/api/review/{record_id}/reject", response_model=ReviewActionResult)
def review_reject(record_id: str) -> dict:
    try:
        return review.reject(record_id)
    except (review.NotFound, review.WriteUnavailable) as error:
        raise _review_write_error(error) from error


@router.delete("/api/review/{record_id}", response_model=ReviewActionResult)
def review_delete(record_id: str) -> dict:
    try:
        return review.remove(record_id)
    except (review.NotFound, review.WriteUnavailable) as error:
        raise _review_write_error(error) from error
