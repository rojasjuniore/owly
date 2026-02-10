"""
General Q&A Service - Handles non-scenario-specific questions
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from openai import AsyncOpenAI
import json

from app.config import settings
from app.models.document import Document, Rule, Chunk


class GeneralQAService:
    """Handles general questions about lenders, products, and the system."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_model
    
    async def answer_general_question(self, question: str) -> dict:
        """
        Answer general questions like:
        - How many lenders do you have?
        - What products are available?
        - What information do you need?
        """
        # Get system stats
        stats = await self._get_system_stats()
        
        system_prompt = """You are Owly, a mortgage lending assistant. Answer the user's general question based on the available data.

Available System Data:
{stats}

Guidelines:
- Be helpful and informative
- If asked about available lenders, list them
- If asked about products, explain the types (Conventional, FHA, VA, USDA, Non-QM, etc.)
- If asked what information is needed, explain the key factors for eligibility
- Always be encouraging and helpful

For eligibility analysis, these are the key factors we consider:
1. Credit Score (FICO)
2. State/Location
3. Loan Purpose (Purchase, Refinance, Cash-Out)
4. Occupancy (Primary, Investment, Second Home)
5. Property Type (SFR, Condo, 2-4 Unit)
6. Loan Amount & LTV
7. Income Documentation Type
8. Credit Events (Bankruptcy, Foreclosure, etc.)

Respond naturally and helpfully."""

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt.format(stats=json.dumps(stats, indent=2))},
                {"role": "user", "content": question}
            ],
            temperature=0.7,
            max_tokens=500
        )
        
        return {
            "response": response.choices[0].message.content,
            "type": "general_answer",
            "citations": []
        }
    
    async def answer_product_search(
        self, 
        question: str, 
        product_type: str | None = None,
        lender_filter: str | None = None
    ) -> dict:
        """
        Answer product-specific questions like:
        - Which lender is best for bank statement loans?
        - Who offers DSCR?
        
        Args:
            question: The user's question
            product_type: Filter by product type (e.g., "bank statement", "DSCR")
            lender_filter: Optional lender to focus on (for follow-up questions)
        """
        # Get relevant rules and documents
        # Apply lender filter if provided (for context carryover in follow-ups)
        rules = await self._get_rules_by_product(product_type, lender_filter=lender_filter)
        chunks = await self._search_chunks(question, limit=5, lender_filter=lender_filter)
        
        # Format context with citations
        context_parts = []
        citations = []
        
        for i, rule in enumerate(rules[:10]):
            context_parts.append(f"[{i+1}] {rule.lender} - {rule.program or 'Standard'}: "
                               f"FICO {rule.fico_min or 'N/A'}-{rule.fico_max or 'N/A'}, "
                               f"LTV max {rule.ltv_max or 'N/A'}%, "
                               f"Doc types: {', '.join(rule.doc_types or ['Full Doc'])}")
            citations.append({
                "id": i+1,
                "lender": rule.lender,
                "program": rule.program,
                "type": "rule"
            })
        
        for i, chunk in enumerate(chunks):
            idx = len(rules) + i + 1
            # Safely access document attributes
            lender = getattr(chunk.document, 'lender', 'Unknown') if chunk.document else 'Unknown'
            filename = getattr(chunk.document, 'filename', 'Unknown') if chunk.document else 'Unknown'
            context_parts.append(f"[{idx}] From {lender} ({filename}): "
                               f"{chunk.content[:300]}...")
            citations.append({
                "id": idx,
                "lender": lender,
                "filename": filename,
                "type": "document"
            })
        
        # Handle case when no data is available
        if not context_parts:
            return {
                "response": f"""I don't have specific lender information loaded yet to answer your question about {product_type or 'this product type'}.

Once lender guidelines are uploaded, I'll be able to tell you:
- Which lenders offer the product
- Minimum FICO requirements
- LTV limits
- Documentation requirements

In general, for **bank statement loans**, look for Non-QM lenders who specialize in self-employed borrowers. Common requirements include:
- 12-24 months of bank statements
- FICO typically 620-660+
- LTV usually 80-85% max
- 2+ years self-employment history

Would you like to describe your specific scenario? I can help identify what to look for.""",
                "type": "product_search",
                "citations": []
            }
        
        system_prompt = """You are Owly, a mortgage lending assistant. Answer the user's question about specific products or lenders.

Available Information:
{context}

IMPORTANT RULES:
1. ALWAYS cite your sources using [1], [2], etc.
2. Be specific about which lenders offer what
3. Mention key requirements (FICO, LTV, etc.)
4. If you're not sure, say so and suggest what info would help

Example response format:
"Based on the guidelines, **Angel Oak** [1] and **Deephaven** [3] offer strong bank statement programs. 
Angel Oak requires minimum 660 FICO with 12-24 months statements [1], while Deephaven goes down to 620 FICO [3]."
"""

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt.format(context="\n".join(context_parts))},
                {"role": "user", "content": question}
            ],
            temperature=0.3,
            max_tokens=800
        )
        
        return {
            "response": response.choices[0].message.content,
            "type": "product_search",
            "citations": citations
        }
    
    async def answer_eligibility_check(self, question: str, entities: dict | None = None) -> dict:
        """
        Answer quick eligibility questions like:
        - Does any DSCR lender do 5 units?
        - Can I get a loan with 580 score?
        """
        # Search for relevant chunks
        chunks = await self._search_chunks(question, limit=8)
        
        # Also get relevant rules
        rules = await self._search_rules_by_criteria(entities or {})
        
        # Format context with citations
        context_parts = []
        citations = []
        
        for i, chunk in enumerate(chunks):
            # Safely access document attributes
            lender = getattr(chunk.document, 'lender', 'Unknown') if chunk.document else 'Unknown'
            filename = getattr(chunk.document, 'filename', 'Unknown') if chunk.document else 'Unknown'
            context_parts.append(f"[{i+1}] {lender} ({filename}): {chunk.content[:400]}")
            citations.append({
                "id": i+1,
                "lender": lender,
                "filename": filename,
                "type": "document"
            })
        
        for i, rule in enumerate(rules[:5]):
            idx = len(chunks) + i + 1
            context_parts.append(f"[{idx}] {rule.lender} - {rule.program or 'Standard'}: "
                               f"FICO {rule.fico_min or 'N/A'}-{rule.fico_max or 'N/A'}, LTV max {rule.ltv_max or 'N/A'}%")
            citations.append({
                "id": idx,
                "lender": rule.lender,
                "program": rule.program,
                "type": "rule"
            })
        
        # Handle case when no data is available
        if not context_parts:
            return {
                "response": f"""I don't have specific lender guidelines loaded yet to give you a definitive answer.

However, I can share general industry knowledge:

**For DSCR loans with 5+ units:**
- Many DSCR lenders DO allow 5+ units, but terms vary
- Typical requirements: DSCR 1.0-1.25+, LTV 65-75%, FICO 660+
- Some lenders cap at 4 units, others go up to 10+
- Larger properties often require lower LTV

Once I have specific lender guidelines loaded, I'll be able to tell you exactly which lenders allow this and their specific requirements.

Would you like to tell me more about your scenario? (FICO, LTV, property location, etc.)""",
                "type": "eligibility_check",
                "citations": []
            }
        
        system_prompt = """You are Owly, a mortgage lending assistant. Answer the user's eligibility question.

Available Information:
{context}

IMPORTANT RULES:
1. ALWAYS cite your sources using [1], [2], etc.
2. Give a direct YES/NO/MAYBE answer first
3. Then explain which lenders/products might work
4. Mention any conditions or limitations
5. If info is limited, say what additional details would help

Example response:
"**Yes**, several lenders accept 5+ unit properties for DSCR loans. 
Based on the guidelines, **Angel Oak** [1] allows up to 10 units with minimum 1.0 DSCR, 
and **Deephaven** [3] goes up to 8 units. Note that LTV requirements are typically lower (65-70%) for larger properties [1][3]."
"""

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt.format(context="\n".join(context_parts))},
                {"role": "user", "content": question}
            ],
            temperature=0.3,
            max_tokens=800
        )
        
        return {
            "response": response.choices[0].message.content,
            "type": "eligibility_check",
            "citations": citations
        }
    
    async def _get_system_stats(self) -> dict:
        """Get stats about available lenders and documents."""
        # Count unique lenders
        lender_result = await self.db.execute(
            select(func.count(func.distinct(Document.lender)))
        )
        lender_count = lender_result.scalar() or 0
        
        # Get lender names
        lenders_result = await self.db.execute(
            select(Document.lender).distinct()
        )
        lenders = [r[0] for r in lenders_result.fetchall() if r[0]]
        
        # Count documents
        doc_result = await self.db.execute(select(func.count(Document.id)))
        doc_count = doc_result.scalar() or 0
        
        # Count rules
        rule_result = await self.db.execute(select(func.count(Rule.id)))
        rule_count = rule_result.scalar() or 0
        
        return {
            "total_lenders": lender_count,
            "lender_names": lenders,
            "total_documents": doc_count,
            "total_rules": rule_count,
            "product_types": ["Conventional", "FHA", "VA", "USDA", "Non-QM (Bank Statement, DSCR, Asset Depletion)"]
        }
    
    async def _get_rules_by_product(
        self, 
        product_type: str | None, 
        lender_filter: str | None = None
    ) -> list[Rule]:
        """
        Get rules filtered by product type and optionally by lender.
        
        NOTE: lender_filter is only used for PRODUCT_SEARCH follow-ups,
        NOT for ELIGIBILITY_CHECK (which always searches all lenders).
        """
        query = select(Rule)
        if product_type:
            query = query.where(Rule.doc_types.contains([product_type]))
        if lender_filter:
            # Case-insensitive lender match
            query = query.where(Rule.lender.ilike(f"%{lender_filter}%"))
        query = query.limit(20)
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def _search_chunks(
        self, 
        query: str, 
        limit: int = 5,
        lender_filter: str | None = None
    ) -> list[Chunk]:
        """
        Search chunks by text (simplified - would use vector search in production).
        
        NOTE: lender_filter is only used for PRODUCT_SEARCH follow-ups,
        NOT for ELIGIBILITY_CHECK (which always searches all lenders).
        """
        from sqlalchemy.orm import selectinload
        
        stmt = select(Chunk).options(selectinload(Chunk.document))
        
        if lender_filter:
            # Filter by lender via join with Document
            stmt = stmt.join(Chunk.document).where(
                Document.lender.ilike(f"%{lender_filter}%")
            )
        
        stmt = stmt.limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
    
    async def _search_rules_by_criteria(self, criteria: dict) -> list[Rule]:
        """Search rules matching criteria."""
        query = select(Rule)
        
        if criteria.get("fico"):
            query = query.where(Rule.fico_min <= criteria["fico"])
        if criteria.get("ltv"):
            query = query.where(Rule.ltv_max >= criteria["ltv"])
        
        query = query.limit(10)
        result = await self.db.execute(query)
        return list(result.scalars().all())
