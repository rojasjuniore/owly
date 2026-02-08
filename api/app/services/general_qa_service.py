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
    
    async def answer_product_search(self, question: str, product_type: str | None = None) -> dict:
        """
        Answer product-specific questions like:
        - Which lender is best for bank statement loans?
        - Who offers DSCR?
        """
        # Get relevant rules and documents
        rules = await self._get_rules_by_product(product_type)
        chunks = await self._search_chunks(question, limit=5)
        
        # Format context with citations
        context_parts = []
        citations = []
        
        for i, rule in enumerate(rules[:10]):
            context_parts.append(f"[{i+1}] {rule.lender} - {rule.program or 'Standard'}: "
                               f"FICO {rule.fico_min}-{rule.fico_max}, "
                               f"LTV max {rule.ltv_max}%, "
                               f"Doc types: {', '.join(rule.doc_types or ['Full Doc'])}")
            citations.append({
                "id": i+1,
                "lender": rule.lender,
                "program": rule.program,
                "type": "rule"
            })
        
        for i, chunk in enumerate(chunks):
            idx = len(rules) + i + 1
            context_parts.append(f"[{idx}] From {chunk.document.lender} ({chunk.document.filename}): "
                               f"{chunk.content[:300]}...")
            citations.append({
                "id": idx,
                "lender": chunk.document.lender,
                "filename": chunk.document.filename,
                "type": "document"
            })
        
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
            context_parts.append(f"[{i+1}] {chunk.document.lender} ({chunk.document.filename}): {chunk.content[:400]}")
            citations.append({
                "id": i+1,
                "lender": chunk.document.lender,
                "filename": chunk.document.filename,
                "type": "document"
            })
        
        for i, rule in enumerate(rules[:5]):
            idx = len(chunks) + i + 1
            context_parts.append(f"[{idx}] {rule.lender} - {rule.program}: "
                               f"FICO {rule.fico_min}-{rule.fico_max}, LTV max {rule.ltv_max}%")
            citations.append({
                "id": idx,
                "lender": rule.lender,
                "program": rule.program,
                "type": "rule"
            })
        
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
    
    async def _get_rules_by_product(self, product_type: str | None) -> list[Rule]:
        """Get rules filtered by product type."""
        query = select(Rule)
        if product_type:
            query = query.where(Rule.doc_types.contains([product_type]))
        query = query.limit(20)
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def _search_chunks(self, query: str, limit: int = 5) -> list[Chunk]:
        """Search chunks by text (simplified - would use vector search in production)."""
        # For now, just get recent chunks - in production, use pgvector similarity search
        from sqlalchemy.orm import selectinload
        result = await self.db.execute(
            select(Chunk)
            .options(selectinload(Chunk.document))
            .limit(limit)
        )
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
