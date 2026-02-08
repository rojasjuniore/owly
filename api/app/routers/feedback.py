from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from uuid import UUID

from app.db import get_db
from app.models.feedback import Feedback, ThumbsRating
from app.models.conversation import Message

router = APIRouter()


class FeedbackRequest(BaseModel):
    message_id: UUID
    thumbs: str  # "up" or "down"
    reason: str | None = None


class FeedbackResponse(BaseModel):
    id: str
    message_id: str
    thumbs: str
    reason: str | None


@router.post("", response_model=FeedbackResponse)
async def submit_feedback(request: FeedbackRequest, db: AsyncSession = Depends(get_db)):
    """Submit feedback for a message."""
    # Verify message exists
    result = await db.execute(select(Message).where(Message.id == request.message_id))
    message = result.scalar_one_or_none()
    
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    
    # Check for existing feedback
    existing = await db.execute(
        select(Feedback).where(Feedback.message_id == request.message_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Feedback already submitted for this message")
    
    # Create feedback
    feedback = Feedback(
        message_id=request.message_id,
        conversation_id=message.conversation_id,
        thumbs=ThumbsRating(request.thumbs),
        reason=request.reason
    )
    db.add(feedback)
    await db.flush()
    
    return FeedbackResponse(
        id=str(feedback.id),
        message_id=str(feedback.message_id),
        thumbs=feedback.thumbs.value,
        reason=feedback.reason
    )


@router.get("", response_model=list[FeedbackResponse])
async def list_feedback(
    thumbs: str | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db)
):
    """List feedback entries."""
    query = select(Feedback).order_by(Feedback.created_at.desc()).limit(limit)
    
    if thumbs:
        query = query.where(Feedback.thumbs == ThumbsRating(thumbs))
    
    result = await db.execute(query)
    feedbacks = result.scalars().all()
    
    return [
        FeedbackResponse(
            id=str(f.id),
            message_id=str(f.message_id),
            thumbs=f.thumbs.value,
            reason=f.reason
        )
        for f in feedbacks
    ]
