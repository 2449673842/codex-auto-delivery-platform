"""Review Packet API Router — stateless PR review preview."""

from fastapi import APIRouter

from app.schemas.common import ApiEnvelope
from app.schemas.review_packet import ReviewPacketRequest
from app.services import review_packet_service

router = APIRouter(tags=["review_packet"])


@router.post("/api/review-packets/preview")
async def preview_review_packet(body: ReviewPacketRequest):
    result = review_packet_service.generate_review_packet_preview(
        repo=body.repo,
        pr_number=body.pr_number,
        reported_head=body.reported_head,
        reported_pytest=body.reported_pytest,
        reported_compileall=body.reported_compileall,
        reported_npm_build=body.reported_npm_build,
        reported_playwright=body.reported_playwright,
        reported_changed_file_count=body.reported_changed_file_count,
    )
    return ApiEnvelope(
        data=result.model_dump(),
        message="Review packet generated",
    )
