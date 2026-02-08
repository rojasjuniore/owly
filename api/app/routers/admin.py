from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from uuid import UUID
from typing import Optional
import hashlib

from app.db import get_db
from app.models.document import Document, DocumentStatus, DocumentArchetype, Chunk, Rule
from app.models.conversation import Conversation
from app.models.feedback import Feedback, ThumbsRating
from app.services.ingestion_service import IngestionService

router = APIRouter()


# --- Documents ---

class DocumentResponse(BaseModel):
    id: str
    filename: str
    lender: str | None
    program: str | None
    archetype: str | None
    status: str
    chunks_count: int
    rules_count: int
    created_at: str


class DocumentUpdate(BaseModel):
    lender: str | None = None
    program: str | None = None
    archetype: str | None = None
    status: str | None = None


@router.get("/documents", response_model=list[DocumentResponse])
async def list_documents(db: AsyncSession = Depends(get_db)):
    """List all documents with chunk/rule counts."""
    result = await db.execute(
        select(Document).order_by(Document.created_at.desc())
    )
    documents = result.scalars().all()
    
    response = []
    for doc in documents:
        # Get counts
        chunks_result = await db.execute(
            select(func.count(Chunk.id)).where(Chunk.document_id == doc.id)
        )
        chunks_count = chunks_result.scalar() or 0
        
        rules_result = await db.execute(
            select(func.count(Rule.id)).where(Rule.document_id == doc.id)
        )
        rules_count = rules_result.scalar() or 0
        
        response.append(DocumentResponse(
            id=str(doc.id),
            filename=doc.filename,
            lender=doc.lender,
            program=doc.program,
            archetype=doc.archetype.value if doc.archetype else None,
            status=doc.status.value,
            chunks_count=chunks_count,
            rules_count=rules_count,
            created_at=doc.created_at.isoformat()
        ))
    
    return response


@router.post("/documents", response_model=DocumentResponse)
async def upload_document(
    file: UploadFile = File(...),
    lender: str = Form(None),
    program: str = Form(None),
    archetype: str = Form(None),
    db: AsyncSession = Depends(get_db)
):
    """Upload and process a PDF document."""
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")
    
    # Read file content
    content = await file.read()
    file_hash = hashlib.sha256(content).hexdigest()
    
    # Check for duplicate
    existing = await db.execute(
        select(Document).where(Document.file_hash == file_hash)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Document already exists")
    
    # Create document record
    doc = Document(
        filename=file.filename,
        lender=lender,
        program=program,
        archetype=DocumentArchetype(archetype) if archetype else None,
        file_hash=file_hash,
        status=DocumentStatus.ACTIVE
    )
    db.add(doc)
    await db.flush()
    
    # Process document (extract text, chunk, embed)
    ingestion_service = IngestionService(db)
    await ingestion_service.process_document(doc.id, content)
    
    return DocumentResponse(
        id=str(doc.id),
        filename=doc.filename,
        lender=doc.lender,
        program=doc.program,
        archetype=doc.archetype.value if doc.archetype else None,
        status=doc.status.value,
        chunks_count=0,  # Will be updated after processing
        rules_count=0,
        created_at=doc.created_at.isoformat()
    )


@router.patch("/documents/{document_id}", response_model=DocumentResponse)
async def update_document(
    document_id: UUID,
    update: DocumentUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update document metadata or status."""
    result = await db.execute(
        select(Document).where(Document.id == document_id)
    )
    doc = result.scalar_one_or_none()
    
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    if update.lender is not None:
        doc.lender = update.lender
    if update.program is not None:
        doc.program = update.program
    if update.archetype is not None:
        doc.archetype = DocumentArchetype(update.archetype)
    if update.status is not None:
        doc.status = DocumentStatus(update.status)
    
    await db.flush()
    
    return DocumentResponse(
        id=str(doc.id),
        filename=doc.filename,
        lender=doc.lender,
        program=doc.program,
        archetype=doc.archetype.value if doc.archetype else None,
        status=doc.status.value,
        chunks_count=0,
        rules_count=0,
        created_at=doc.created_at.isoformat()
    )


@router.delete("/documents/{document_id}")
async def delete_document(document_id: UUID, db: AsyncSession = Depends(get_db)):
    """Delete a document and its chunks/rules."""
    result = await db.execute(
        select(Document).where(Document.id == document_id)
    )
    doc = result.scalar_one_or_none()
    
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    await db.delete(doc)
    return {"status": "deleted"}


# --- Rules ---

class RuleResponse(BaseModel):
    id: str
    document_id: str
    lender: str
    program: str | None
    fico_min: int | None
    fico_max: int | None
    ltv_max: float | None
    loan_min: float | None
    loan_max: float | None
    purposes: list[str] | None
    occupancies: list[str] | None
    property_types: list[str] | None
    doc_types: list[str] | None
    notes: str | None
    status: str


class RuleUpdate(BaseModel):
    fico_min: int | None = None
    fico_max: int | None = None
    ltv_max: float | None = None
    loan_min: float | None = None
    loan_max: float | None = None
    purposes: list[str] | None = None
    occupancies: list[str] | None = None
    property_types: list[str] | None = None
    doc_types: list[str] | None = None
    notes: str | None = None
    status: str | None = None


@router.get("/rules", response_model=list[RuleResponse])
async def list_rules(
    lender: str | None = None,
    status: str | None = None,
    db: AsyncSession = Depends(get_db)
):
    """List all rules with optional filters."""
    query = select(Rule)
    
    if lender:
        query = query.where(Rule.lender == lender)
    if status:
        query = query.where(Rule.status == DocumentStatus(status))
    
    result = await db.execute(query.order_by(Rule.lender, Rule.program))
    rules = result.scalars().all()
    
    return [
        RuleResponse(
            id=str(r.id),
            document_id=str(r.document_id),
            lender=r.lender,
            program=r.program,
            fico_min=r.fico_min,
            fico_max=r.fico_max,
            ltv_max=float(r.ltv_max) if r.ltv_max else None,
            loan_min=float(r.loan_min) if r.loan_min else None,
            loan_max=float(r.loan_max) if r.loan_max else None,
            purposes=r.purposes,
            occupancies=r.occupancies,
            property_types=r.property_types,
            doc_types=r.doc_types,
            notes=r.notes,
            status=r.status.value
        )
        for r in rules
    ]


@router.patch("/rules/{rule_id}", response_model=RuleResponse)
async def update_rule(
    rule_id: UUID,
    update: RuleUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update a rule's thresholds or status."""
    result = await db.execute(select(Rule).where(Rule.id == rule_id))
    rule = result.scalar_one_or_none()
    
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    
    for field, value in update.model_dump(exclude_unset=True).items():
        if field == "status" and value:
            setattr(rule, field, DocumentStatus(value))
        elif value is not None:
            setattr(rule, field, value)
    
    await db.flush()
    
    return RuleResponse(
        id=str(rule.id),
        document_id=str(rule.document_id),
        lender=rule.lender,
        program=rule.program,
        fico_min=rule.fico_min,
        fico_max=rule.fico_max,
        ltv_max=float(rule.ltv_max) if rule.ltv_max else None,
        loan_min=float(rule.loan_min) if rule.loan_min else None,
        loan_max=float(rule.loan_max) if rule.loan_max else None,
        purposes=rule.purposes,
        occupancies=rule.occupancies,
        property_types=rule.property_types,
        doc_types=rule.doc_types,
        notes=rule.notes,
        status=rule.status.value
    )


# --- Stats ---

class StatsResponse(BaseModel):
    total_conversations: int
    total_messages: int
    total_documents: int
    total_rules: int
    thumbs_up: int
    thumbs_down: int
    feedback_rate: float


@router.get("/stats", response_model=StatsResponse)
async def get_stats(db: AsyncSession = Depends(get_db)):
    """Get dashboard statistics."""
    # Conversations
    conv_result = await db.execute(select(func.count(Conversation.id)))
    total_conversations = conv_result.scalar() or 0
    
    # Messages (from Message table)
    from app.models.conversation import Message
    msg_result = await db.execute(select(func.count(Message.id)))
    total_messages = msg_result.scalar() or 0
    
    # Documents
    doc_result = await db.execute(select(func.count(Document.id)))
    total_documents = doc_result.scalar() or 0
    
    # Rules
    rule_result = await db.execute(select(func.count(Rule.id)))
    total_rules = rule_result.scalar() or 0
    
    # Feedback
    up_result = await db.execute(
        select(func.count(Feedback.id)).where(Feedback.thumbs == ThumbsRating.UP)
    )
    thumbs_up = up_result.scalar() or 0
    
    down_result = await db.execute(
        select(func.count(Feedback.id)).where(Feedback.thumbs == ThumbsRating.DOWN)
    )
    thumbs_down = down_result.scalar() or 0
    
    total_feedback = thumbs_up + thumbs_down
    feedback_rate = (thumbs_up / total_feedback * 100) if total_feedback > 0 else 0
    
    return StatsResponse(
        total_conversations=total_conversations,
        total_messages=total_messages,
        total_documents=total_documents,
        total_rules=total_rules,
        thumbs_up=thumbs_up,
        thumbs_down=thumbs_down,
        feedback_rate=round(feedback_rate, 1)
    )
