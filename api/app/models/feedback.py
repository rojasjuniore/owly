from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
import enum

from app.db import Base


class ThumbsRating(str, enum.Enum):
    UP = "up"
    DOWN = "down"


class Feedback(Base):
    __tablename__ = "feedback"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id"))
    message_id = Column(UUID(as_uuid=True), ForeignKey("messages.id"))
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    thumbs = Column(Enum(ThumbsRating))
    reason = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
