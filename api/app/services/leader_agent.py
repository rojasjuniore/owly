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

IMPORTANT: For each candidate, cite the source of information using [source_id].

You have access to information about these lenders:
{available_lenders}

Respond in JSON format:
{{
  "understanding": "Brief summary of what the client is looking for",
  "top_candidates": [
    {{"lender": "Lender A", "reason": "Reason with [1] citation"}},
    {{"lender": "Lender B", "reason": "Reason with [2] citation"}},
    {{"lender": "Lender C", "reason": "Reason with [3] citation"}}
  ],
  "reasoning": "Overall rationale for selections"
}}"""


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
        Analyze scenario and return top candidate lenders with citations.
        """
        # Get some context from RAG to help decision
        query = self._build_query(scenario)
        chunks = await self.retrieval.search(query, top_k=10)
        
        # Build context about what lenders appear in results - with source IDs for citations
        lender_mentions = {}
        sources = []
        
        for i, chunk in enumerate(chunks):
            lender = chunk.get("lender", "Unknown")
            source_id = i + 1
            
            # Track source for citations
            sources.append({
                "id": source_id,
                "lender": lender,
                "filename": chunk.get("filename", "Unknown"),
                "content_preview": chunk["content"][:100]
            })
            
            if lender not in lender_mentions:
                lender_mentions[lender] = []
            lender_mentions[lender].append({
                "source_id": source_id,
                "content": chunk["content"][:200]
            })
        
        # Build user prompt with source IDs
        user_prompt = f"""Scenario:
{self._format_scenario(scenario)}

Relevant information found (use [source_id] to cite):
{self._format_lender_mentions_with_ids(lender_mentions)}

Which lenders should we analyze in detail for this scenario?
Return the top 3-5 most promising candidates with citations."""

        result = await self._call_llm(user_prompt)
        
        # Add sources to result
        result["sources"] = sources
        
        # Validate response
        if "error" in result:
            return {
                "understanding": "Could not analyze - using all lenders",
                "top_candidates": [{"lender": l, "reason": "Included for analysis"} for l in self.available_lenders[:5]],
                "reasoning": "Fallback due to error",
                "sources": sources,
                "error": result["error"]
            }
        
        # Ensure top_candidates only includes available lenders
        if "top_candidates" in result:
            valid_candidates = []
            for candidate in result["top_candidates"]:
                lender_name = candidate.get("lender") if isinstance(candidate, dict) else candidate
                if lender_name in self.available_lenders:
                    if isinstance(candidate, dict):
                        valid_candidates.append(candidate)
                    else:
                        valid_candidates.append({"lender": candidate, "reason": ""})
            result["top_candidates"] = valid_candidates[:5]
        
        return result
    
    def _format_lender_mentions_with_ids(self, mentions: dict) -> str:
        """Format lender mentions with source IDs for citations."""
        if not mentions:
            return "No specific lender information found in documents."
        
        lines = []
        for lender, items in mentions.items():
            lines.append(f"\n{lender}:")
            for item in items[:2]:
                lines.append(f"  - [{item['source_id']}] {item['content']}...")
        
        return "\n".join(lines)
    
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
    
    # _format_lender_mentions_with_ids is used instead
