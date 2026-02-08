from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import fitz  # PyMuPDF
import io
import re

from app.models.document import Document, Chunk, Rule, DocumentStatus
from app.services.retrieval_service import RetrievalService


class IngestionService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.retrieval = RetrievalService(db)
    
    async def process_document(self, document_id: str, content: bytes) -> None:
        """
        Process a PDF document:
        1. Extract text
        2. Chunk content
        3. Generate embeddings
        4. Extract rules (if matrix)
        """
        # Get document record
        result = await self.db.execute(
            select(Document).where(Document.id == document_id)
        )
        document = result.scalar_one()
        
        # Extract text from PDF
        text, tables = self._extract_pdf_content(content)
        
        # Chunk the text
        chunks = self._chunk_text(text, document.filename)
        
        # Add table content as separate chunks
        for table in tables:
            chunks.append({
                "content": table,
                "section_path": "table",
                "is_table": True
            })
        
        # Generate embeddings and store chunks
        await self.retrieval.embed_and_store(document_id, chunks)
        
        # Try to extract structured rules if it looks like a matrix
        if self._is_matrix_document(document.filename, text):
            await self._extract_rules(document, text, tables)
    
    def _extract_pdf_content(self, content: bytes) -> tuple[str, list[str]]:
        """Extract text and tables from PDF."""
        doc = fitz.open(stream=content, filetype="pdf")
        
        full_text = []
        tables = []
        
        for page in doc:
            # Extract text
            text = page.get_text()
            full_text.append(text)
            
            # Try to detect tables (simplified)
            # A real implementation would use pdfplumber or similar
            if self._looks_like_table(text):
                tables.append(text)
        
        doc.close()
        
        return "\n\n".join(full_text), tables
    
    def _looks_like_table(self, text: str) -> bool:
        """Simple heuristic to detect if text contains a table."""
        # Look for patterns common in mortgage matrices
        patterns = [
            r'\d{3}\s*[-–]\s*\d{3}',  # FICO ranges like "680 - 719"
            r'\d+\.?\d*\s*%',  # Percentages
            r'LTV|CLTV|DTI',  # Common mortgage terms
            r'Primary|Investment|Second',  # Occupancy types
        ]
        
        matches = sum(1 for p in patterns if re.search(p, text, re.IGNORECASE))
        return matches >= 2
    
    def _chunk_text(self, text: str, filename: str, chunk_size: int = 1000) -> list[dict]:
        """Split text into chunks with overlap."""
        chunks = []
        
        # Split by paragraphs first
        paragraphs = text.split('\n\n')
        
        current_chunk = ""
        current_section = ""
        
        for para in paragraphs:
            # Detect section headers
            if self._is_section_header(para):
                current_section = para.strip()[:100]
            
            # Add to current chunk
            if len(current_chunk) + len(para) < chunk_size:
                current_chunk += para + "\n\n"
            else:
                # Save current chunk
                if current_chunk.strip():
                    chunks.append({
                        "content": current_chunk.strip(),
                        "section_path": current_section,
                        "is_table": False
                    })
                current_chunk = para + "\n\n"
        
        # Save last chunk
        if current_chunk.strip():
            chunks.append({
                "content": current_chunk.strip(),
                "section_path": current_section,
                "is_table": False
            })
        
        return chunks
    
    def _is_section_header(self, text: str) -> bool:
        """Check if text looks like a section header."""
        text = text.strip()
        # Short, possibly numbered, often in caps
        if len(text) < 100:
            if text.isupper() or text[0].isdigit() or text.startswith("Section"):
                return True
        return False
    
    def _is_matrix_document(self, filename: str, text: str) -> bool:
        """Check if document is likely an eligibility matrix."""
        filename_lower = filename.lower()
        if any(term in filename_lower for term in ["matrix", "eligibility", "table"]):
            return True
        
        # Check content patterns
        matrix_patterns = [
            r'FICO\s+Score',
            r'Max\s+LTV',
            r'Loan\s+Amount',
            r'Primary.*Investment',
        ]
        
        matches = sum(1 for p in matrix_patterns if re.search(p, text, re.IGNORECASE))
        return matches >= 2
    
    async def _extract_rules(
        self,
        document: Document,
        text: str,
        tables: list[str]
    ) -> None:
        """
        Extract structured rules from matrix document.
        This is a simplified implementation - production would need
        more sophisticated table parsing.
        """
        # For Phase 0, we'll create some basic rules based on patterns
        # A real implementation would use table extraction libraries
        
        lender = document.lender or self._extract_lender_name(text, document.filename)
        
        # Look for common patterns
        fico_pattern = r'(\d{3})\s*[-–]\s*(\d{3})'
        ltv_pattern = r'(\d+(?:\.\d+)?)\s*%\s*(?:LTV|Max)'
        
        fico_matches = re.findall(fico_pattern, text)
        ltv_matches = re.findall(ltv_pattern, text)
        
        # Create rules based on found patterns
        if fico_matches and ltv_matches:
            for fico_range in fico_matches[:3]:  # Limit to avoid too many rules
                for ltv in ltv_matches[:3]:
                    rule = Rule(
                        document_id=document.id,
                        lender=lender,
                        program=document.program,
                        fico_min=int(fico_range[0]),
                        fico_max=int(fico_range[1]),
                        ltv_max=float(ltv),
                        status=DocumentStatus.ACTIVE
                    )
                    self.db.add(rule)
        
        await self.db.flush()
    
    def _extract_lender_name(self, text: str, filename: str) -> str:
        """Try to extract lender name from document."""
        # Try from filename first
        parts = filename.replace(".pdf", "").replace("_", " ").split()
        if parts:
            # Common patterns: "Lender Name Matrix.pdf"
            for i, part in enumerate(parts):
                if part.lower() in ["matrix", "guide", "guidelines", "eligibility"]:
                    return " ".join(parts[:i])
            return parts[0]
        
        return "Unknown"
