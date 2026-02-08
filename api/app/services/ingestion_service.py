from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import fitz  # PyMuPDF
import io
import re
import json
from openai import AsyncOpenAI

from app.models.document import Document, Chunk, Rule, DocumentStatus
from app.services.retrieval_service import RetrievalService
from app.config import settings


# Known lenders for better matching
KNOWN_LENDERS = [
    "Acra Lending",
    "A&D Mortgage", 
    "Activator",
    "AHL",
    "All Star Credit",
    "AmWest",
    "Angel Oak",
    "Athas Capital",
    "Caliber Home Loans",
    "Carrington",
    "Champions Funding",
    "Citadel Servicing",
    "Civic Financial",
    "CrossCountry Mortgage",
    "Deephaven",
    "Finance of America",
    "First National Bank of America",
    "Freedom Mortgage",
    "HomeXpress",
    "Impac Mortgage",
    "Kind Lending",
    "LoanStream",
    "New American Funding",
    "Newrez",
    "PennyMac",
    "PRMG",
    "Quontic Bank",
    "Rocket Mortgage",
    "Sprout Mortgage",
    "UWM",
    "Verus Mortgage",
]


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
        """Try to extract lender name from document (sync fallback)."""
        # Try from filename first
        parts = filename.replace(".pdf", "").replace("_", " ").split()
        if parts:
            # Common patterns: "Lender Name Matrix.pdf"
            for i, part in enumerate(parts):
                if part.lower() in ["matrix", "guide", "guidelines", "eligibility"]:
                    return " ".join(parts[:i])
            return parts[0]
        
        return "Unknown"
    
    async def detect_lender_from_content(self, content: bytes, filename: str) -> dict:
        """
        Use LLM to infer lender and program from filename.
        Returns: {"lender": str, "program": str | None, "confidence": str}
        """
        try:
            client = AsyncOpenAI(api_key=settings.openai_api_key)
            
            known_lenders_str = ", ".join(KNOWN_LENDERS)
            
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": f"""You extract mortgage lender/company names and program names from PDF filenames.

Known lenders in our system: {known_lenders_str}

IMPORTANT RULES:
1. The FIRST word(s) in the filename is usually the lender/company name
2. Match to known lenders when possible, using exact spelling from the list
3. If the lender isn't in the list, STILL extract it - use the company name from the filename
4. Program names come AFTER the lender (e.g., "Bank Statement", "DSCR", "NonQM", "Full Doc", "Alt Doc")
5. Ignore generic words like "Matrix", "Guidelines", "Guide", "Eligibility", "Client", "Summary"

Examples:
- "AHL NonQM Client Guide.pdf" → lender: "AHL", program: "NonQM"
- "AmWest Bank Statement Advantage.pdf" → lender: "AmWest", program: "Bank Statement"
- "Acra Lending Platinum Select.pdf" → lender: "Acra Lending", program: "Platinum Select"
- "A&D Mortgage NonQm Guidelines.pdf" → lender: "A&D Mortgage", program: "NonQM"

Return JSON only: {{"lender": "Lender Name", "program": "Program Name or null"}}"""
                    },
                    {
                        "role": "user", 
                        "content": f"Extract lender and program from: {filename}"
                    }
                ],
                temperature=0,
                max_tokens=100
            )
            
            result_text = response.choices[0].message.content.strip()
            
            # Parse JSON response
            if result_text.startswith("```"):
                result_text = result_text.split("```")[1]
                if result_text.startswith("json"):
                    result_text = result_text[4:]
            
            result = json.loads(result_text)
            
            lender = result.get("lender")
            program = result.get("program")
            
            confidence = "high" if lender else "low"
            
            return {
                "lender": lender,
                "program": program,
                "confidence": confidence
            }
            
        except Exception as e:
            print(f"Error detecting lender with LLM: {e}")
            # Fallback to pattern matching
            lender, program = self._extract_lender_from_filename(filename)
            return {
                "lender": lender,
                "program": program,
                "confidence": "medium" if lender else "low"
            }
    
    def _extract_lender_from_filename(self, filename: str) -> tuple[str | None, str | None]:
        """
        Extract lender name from filename.
        Common patterns:
        - "Acra Lending - Bank Statement Program.pdf"
        - "A&D_Mortgage_Guidelines.pdf"
        - "AngelOak_DSCR_Matrix.pdf"
        """
        # Clean filename
        name = filename.replace(".pdf", "").replace(".PDF", "")
        name = name.replace("_", " ").replace("-", " ")
        
        # Check against known lenders (case-insensitive)
        name_lower = name.lower()
        
        for known in KNOWN_LENDERS:
            known_lower = known.lower()
            # Check if known lender appears in filename
            if known_lower in name_lower:
                # Try to extract program name (everything after lender name)
                parts = name_lower.split(known_lower)
                program = None
                if len(parts) > 1 and parts[1].strip():
                    program_part = parts[1].strip()
                    # Clean up program name
                    program_words = program_part.split()
                    # Filter out common non-program words
                    skip_words = {"matrix", "guidelines", "guide", "eligibility", "product", "sheet"}
                    program_words = [w for w in program_words if w not in skip_words]
                    if program_words:
                        program = " ".join(program_words).title()
                
                return known, program
        
        # Try common variations
        variations = {
            "a&d": "A&D Mortgage",
            "ad mortgage": "A&D Mortgage", 
            "acra": "Acra Lending",
            "angel oak": "Angel Oak",
            "angeloak": "Angel Oak",
            "athas": "Athas Capital",
            "caliber": "Caliber Home Loans",
            "carrington": "Carrington",
            "champions": "Champions Funding",
            "citadel": "Citadel Servicing",
            "civic": "Civic Financial",
            "crosscountry": "CrossCountry Mortgage",
            "deephaven": "Deephaven",
            "foa": "Finance of America",
            "fnba": "First National Bank of America",
            "freedom": "Freedom Mortgage",
            "homexpress": "HomeXpress",
            "impac": "Impac Mortgage",
            "kind": "Kind Lending",
            "loanstream": "LoanStream",
            "naf": "New American Funding",
            "newrez": "Newrez",
            "pennymac": "PennyMac",
            "prmg": "PRMG",
            "quontic": "Quontic Bank",
            "rocket": "Rocket Mortgage",
            "sprout": "Sprout Mortgage",
            "uwm": "UWM",
            "verus": "Verus Mortgage",
        }
        
        for pattern, lender in variations.items():
            if pattern in name_lower:
                return lender, None
        
        return None, None
    
    def _find_lender_in_text(self, text: str) -> tuple[str | None, str | None]:
        """Search for known lenders in document text."""
        text_lower = text.lower()
        
        for known in KNOWN_LENDERS:
            if known.lower() in text_lower:
                return known, None
        
        return None, None
