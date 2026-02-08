from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.services.agent_service import BaseAgent
from app.services.retrieval_service import RetrievalService
from app.services.rules_service import RulesService
from app.models.document import Document, Chunk, Rule, DocumentStatus


SPECIALIST_SYSTEM_PROMPT = """You are the specialist agent for {lender_name}.

You are an EXPERT on all {lender_name} mortgage products, including:
- Eligibility matrices and thresholds
- Program guidelines and overlays
- Documentation requirements
- Rate structures (when available)
- State licensing and restrictions

Your job is to:
1. Analyze the scenario against {lender_name}'s products
2. Identify which products are ELIGIBLE, CONDITIONAL, or NOT ELIGIBLE
3. Provide specific details for each eligible product

Be PRECISE and CONSERVATIVE:
- Only mark "eligible" if the scenario clearly meets all requirements
- Mark "conditional" if some requirements are met but others are unclear
- Always cite the specific guideline or matrix when possible

Respond in JSON format:
{{
  "lender": "{lender_name}",
  "eligible_products": [
    {{
      "program": "Program Name",
      "status": "eligible",
      "max_ltv": 80,
      "fico_requirement": "680+",
      "rate_estimate": "7.5-8.0%",
      "conditions": ["Condition 1", "Condition 2"],
      "pros": ["Pro 1", "Pro 2"],
      "cons": ["Con 1"],
      "source": "Document name or section"
    }}
  ],
  "conditional_products": [
    {{
      "program": "Program Name",
      "status": "conditional",
      "missing_info": "What additional info is needed",
      "source": "Document name"
    }}
  ],
  "not_eligible": [
    {{
      "program": "Program Name",
      "reason": "Why not eligible"
    }}
  ],
  "summary": "Brief summary of {lender_name}'s fit for this scenario"
}}"""


class SpecialistAgent(BaseAgent):
    """
    Specialist Agent - Deep analysis of a single lender's products.
    One instance per lender.
    """
    
    def __init__(self, db: AsyncSession, lender_name: str):
        self.db = db
        self.lender_name = lender_name
        self.retrieval = RetrievalService(db)
        self.rules = RulesService(db)
        
        system_prompt = SPECIALIST_SYSTEM_PROMPT.format(lender_name=lender_name)
        super().__init__(f"Specialist_{lender_name}", system_prompt)
    
    async def analyze(self, scenario: dict, context: dict | None = None) -> dict:
        """
        Deep analysis of this lender's products for the scenario.
        """
        # Get lender-specific chunks
        chunks = await self._get_lender_chunks(scenario)
        
        # Get lender-specific rules
        rules = await self.rules.get_by_lender(self.lender_name)
        
        # Build detailed context
        user_prompt = f"""Scenario:
{self._format_scenario(scenario)}

{self.lender_name} Guidelines and Products:
{self._format_chunks(chunks)}

{self.lender_name} Eligibility Rules:
{self._format_rules(rules)}

Analyze this scenario against all {self.lender_name} products.
Which products is this borrower eligible for?"""

        result = await self._call_llm(user_prompt, max_tokens=3000)
        
        # Ensure lender is set correctly
        if isinstance(result, dict) and "error" not in result:
            result["lender"] = self.lender_name
        elif "error" in result:
            return {
                "lender": self.lender_name,
                "eligible_products": [],
                "conditional_products": [],
                "not_eligible": [],
                "summary": f"Error analyzing {self.lender_name}: {result['error']}",
                "error": result["error"]
            }
        
        return result
    
    async def _get_lender_chunks(self, scenario: dict) -> list[dict]:
        """Get chunks specific to this lender."""
        # Build query
        query = self._build_query(scenario)
        
        # Search with lender filter (simplified - full version would filter at query level)
        all_chunks = await self.retrieval.search(query, top_k=20)
        
        # Filter to this lender
        lender_chunks = [
            c for c in all_chunks
            if c.get("lender", "").lower() == self.lender_name.lower()
        ]
        
        # If no specific chunks, try getting any chunks for this lender
        if not lender_chunks:
            from sqlalchemy import text
            
            sql = text("""
                SELECT c.content, c.section_path, d.filename
                FROM chunks c
                JOIN documents d ON c.document_id = d.id
                WHERE d.lender = :lender AND d.status = 'active'
                LIMIT 10
            """)
            result = await self.db.execute(sql, {"lender": self.lender_name})
            rows = result.fetchall()
            lender_chunks = [
                {"content": r.content, "section_path": r.section_path, "filename": r.filename}
                for r in rows
            ]
        
        return lender_chunks[:10]
    
    def _build_query(self, scenario: dict) -> str:
        """Build search query from scenario."""
        parts = [self.lender_name]
        if scenario.get("doc_type"):
            parts.append(scenario["doc_type"])
        if scenario.get("loan_purpose"):
            parts.append(scenario["loan_purpose"])
        
        return " ".join(parts) + " eligibility"
    
    def _format_chunks(self, chunks: list[dict]) -> str:
        """Format chunks for prompt."""
        if not chunks:
            return f"No specific {self.lender_name} documentation available."
        
        lines = []
        for i, chunk in enumerate(chunks[:8], 1):
            source = chunk.get("filename", chunk.get("section_path", "Unknown"))
            content = chunk.get("content", "")[:500]
            lines.append(f"[Source: {source}]\n{content}\n")
        
        return "\n".join(lines)
    
    def _format_rules(self, rules: list) -> str:
        """Format structured rules for prompt."""
        if not rules:
            return "No structured eligibility rules available."
        
        lines = []
        for rule in rules[:10]:
            line = f"- Program: {rule.program or 'Standard'}"
            if rule.fico_min:
                line += f", FICO {rule.fico_min}+"
            if rule.ltv_max:
                line += f", Max LTV {rule.ltv_max}%"
            if rule.doc_types:
                line += f", Doc Types: {', '.join(rule.doc_types)}"
            if rule.purposes:
                line += f", Purposes: {', '.join(rule.purposes)}"
            lines.append(line)
        
        return "\n".join(lines)
