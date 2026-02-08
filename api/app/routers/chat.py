from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from pydantic import BaseModel
from uuid import UUID

from app.db import get_db
from app.models.conversation import Conversation, Message, MessageRole, ConversationStatus
from app.services.chat_service import ChatService

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    conversation_id: UUID | None = None


class ChatResponse(BaseModel):
    message: str
    conversation_id: str
    facts: dict
    missing_fields: list[str]
    confidence: int | None = None
    citations: list[dict] | None = None


class ConversationResponse(BaseModel):
    id: str
    status: str
    facts: dict
    messages: list[dict]
    created_at: str


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest, db: AsyncSession = Depends(get_db)):
    """
    Main chat endpoint. Handles:
    1. Create/get conversation
    2. Extract facts from message
    3. Check required fields
    4. If complete: run eligibility check
    5. If incomplete: ask follow-up
    """
    try:
        chat_service = ChatService(db)
        result = await chat_service.process_message(
            message=request.message,
            conversation_id=request.conversation_id
        )
        
        return ChatResponse(
            message=result["response"],
            conversation_id=str(result["conversation_id"]),
            facts=result["facts"],
            missing_fields=result["missing_fields"],
            confidence=result.get("confidence"),
            citations=result.get("citations")
        )
    except Exception as e:
        # Log the error and return a helpful message
        import traceback
        error_detail = traceback.format_exc()
        print(f"Chat error: {error_detail}")
        
        # Return a fallback response instead of 500
        return ChatResponse(
            message=f"Sorry, I encountered an error processing your request. Please try again or rephrase your question.",
            conversation_id="",
            facts={},
            missing_fields=[],
            confidence=0,
            citations=[]
        )


@router.get("/conversations", response_model=list[ConversationResponse])
async def list_conversations(
    limit: int = 20,
    db: AsyncSession = Depends(get_db)
):
    """List recent conversations."""
    result = await db.execute(
        select(Conversation)
        .options(selectinload(Conversation.messages))
        .order_by(Conversation.updated_at.desc())
        .limit(limit)
    )
    conversations = result.scalars().all()
    
    return [
        ConversationResponse(
            id=str(c.id),
            status=c.status.value,
            facts=c.facts or {},
            messages=[
                {
                    "id": str(m.id),
                    "role": m.role.value,
                    "content": m.content,
                    "created_at": m.created_at.isoformat()
                }
                for m in c.messages
            ],
            created_at=c.created_at.isoformat()
        )
        for c in conversations
    ]


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(conversation_id: UUID, db: AsyncSession = Depends(get_db)):
    """Get a specific conversation with messages."""
    result = await db.execute(
        select(Conversation)
        .options(selectinload(Conversation.messages))
        .where(Conversation.id == conversation_id)
    )
    conversation = result.scalar_one_or_none()
    
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    return ConversationResponse(
        id=str(conversation.id),
        status=conversation.status.value,
        facts=conversation.facts or {},
        messages=[
            {
                "id": str(m.id),
                "role": m.role.value,
                "content": m.content,
                "created_at": m.created_at.isoformat()
            }
            for m in conversation.messages
        ],
        created_at=conversation.created_at.isoformat()
    )
