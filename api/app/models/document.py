from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Integer, Boolean, Numeric, Enum
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
import uuid
import enum

from app.db import Base


class DocumentStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"


class DocumentArchetype(str, enum.Enum):
    A = "A"  # Eligibility Matrix
    B = "B"  # Program Guide
    C = "C"  # Long-form Guidelines
    D = "D"  # Announcements
    E = "E"  # State Licensing


class Document(Base):
    __tablename__ = "documents"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename = Column(String(255), nullable=False)
    lender = Column(String(255))
    program = Column(String(255))
    archetype = Column(Enum(DocumentArchetype))
    status = Column(Enum(DocumentStatus), default=DocumentStatus.ACTIVE)
    file_path = Column(String(500))
    file_hash = Column(String(64))
    effective_date = Column(DateTime(timezone=True))
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Chunk(Base):
    __tablename__ = "chunks"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    content = Column(Text, nullable=False)
    section_path = Column(Text)
    chunk_index = Column(Integer)
    is_table = Column(Boolean, default=False)
    embedding = Column(Vector(1536))
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Rule(Base):
    __tablename__ = "rules"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    lender = Column(String(255), nullable=False)
    program = Column(String(255))
    
    # Thresholds
    fico_min = Column(Integer)
    fico_max = Column(Integer)
    ltv_max = Column(Numeric(5, 2))
    loan_min = Column(Numeric(15, 2))
    loan_max = Column(Numeric(15, 2))
    dti_max = Column(Numeric(5, 2))
    
    # Allowed values
    purposes = Column(ARRAY(String))  # purchase, refi, cashout
    occupancies = Column(ARRAY(String))  # primary, second_home, investment
    property_types = Column(ARRAY(String))  # sfr, condo, 2-4unit
    doc_types = Column(ARRAY(String))  # full_doc, bank_statement, dscr
    
    # Additional
    notes = Column(Text)
    footnotes = Column(ARRAY(String))
    status = Column(Enum(DocumentStatus), default=DocumentStatus.ACTIVE)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
