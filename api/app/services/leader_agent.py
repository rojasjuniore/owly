from sqlalchemy.ext.asyncio import AsyncSession

from app.services.agent_service import BaseAgent
from app.services.retrieval_service import RetrievalService


LEADER_SYSTEM_PROMPT = """You are the Lead Analyst for mortgage eligibility at Owly.

Your job is to:
1. Understand the loan scenario provided
2. Identify which lenders might have suitable products
3. Return the top 3-5 most relevant lenders to analyze in detail

Consider:
- State licensing (is the lender likely active in the state?)
- Product type match (bank statement, full doc, DSCR, etc.)
- Basic threshold fit (FICO ranges, LTV limits)
- Documentation type alignment

Be INCLUSIVE - include lenders that MIGHT work, even if uncertain.
Better to include and filter later than miss a good option.

You have access to information about these lenders:
{available_lenders}

Respond in JSON format:
{
  "understanding": "Brief summary of what the client is looking for",
  "top_candidates": ["Lender A", "Lender B", "Lender C"],
  "reasoning": "Why these lenders were selected over others"
}"""


class LeaderAgent(BaseAgent):
    """
    Leader Agent - Pre-filters lenders based on scenario.
    Returns top 3-5 candidates for specialist analysis.
    """
    
    def __init__(self, db: AsyncSession, available_lenders: list[str]):
        self.db = db
        self.retrieval = RetrievalService(db)
        self.available_lenders = available_lenders
        
        system_prompt = LEADER_SYSTEM_PROMPT.format(
            available_lenders=", ".join(available_lenders)
        )
        super().__init__("Leader", system_prompt)
    
    async def analyze(self, scenario: dict, context: dict | None = None) -> dict:
        """
        Analyze scenario and return top candidate lenders.
        """
        # Get some context from RAG to help decision
        query = self._build_query(scenario)
        chunks = await self.retrieval.search(query, top_k=10)
        
        # Build context about what lenders appear in results
        lender_mentions = {}
        for chunk in chunks:
            lender = chunk.get("lender", "Unknown")
            if lender not in lender_mentions:
                lender_mentions[lender] = []
            lender_mentions[lender].append(chunk["content"][:200])
        
        # Build user prompt
        user_prompt = f"""Scenario:
{self._format_scenario(scenario)}

Relevant information found:
{self._format_lender_mentions(lender_mentions)}

Which lenders should we analyze in detail for this scenario?
Return the top 3-5 most promising candidates."""

        result = await self._call_llm(user_prompt)
        
        # Validate response
        if "error" in result:
            # Fallback: return all available lenders
            return {
                "understanding": "Could not analyze - using all lenders",
                "top_candidates": self.available_lenders[:5],
                "reasoning": "Fallback due to error",
                "error": result["error"]
            }
        
        # Ensure top_candidates only includes available lenders
        if "top_candidates" in result:
            result["top_candidates"] = [
                l for l in result["top_candidates"]
                if l in self.available_lenders
            ][:5]
        
        return result
    
    def _build_query(self, scenario: dict) -> str:
        """Build search query from scenario."""
        parts = []
        if scenario.get("doc_type"):
            parts.append(scenario["doc_type"])
        if scenario.get("loan_purpose"):
            parts.append(scenario["loan_purpose"])
        if scenario.get("property_type"):
            parts.append(scenario["property_type"])
        if scenario.get("fico"):
            parts.append(f"FICO {scenario['fico']}")
        if scenario.get("state"):
            parts.append(scenario["state"])
        
        return " ".join(parts) + " eligibility requirements matrix"
    
    def _format_lender_mentions(self, mentions: dict) -> str:
        """Format lender mentions for prompt."""
        if not mentions:
            return "No specific lender information found in documents."
        
        lines = []
        for lender, snippets in mentions.items():
            lines.append(f"\n{lender}:")
            for snippet in snippets[:2]:
                lines.append(f"  - {snippet}...")
        
        return "\n".join(lines)
