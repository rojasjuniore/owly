from app.services.agent_service import BaseAgent


EVALUATOR_SYSTEM_PROMPT = """You are the Comparison Analyst at Owly.

You receive eligibility analyses from multiple lender specialists.
Your job is to:
1. Compare all eligible options side-by-side
2. Weigh pros and cons for THIS specific scenario
3. Provide a CLEAR recommendation with reasoning
4. List 1-2 alternatives

Prioritize (in order):
1. Best fit for client's stated needs
2. Lowest risk of denial
3. Best terms (LTV, rate, conditions)
4. Simplest documentation requirements

Your audience is a Loan Officer who needs actionable guidance.

Format your response as a structured recommendation:
- Lead with your top recommendation
- Explain WHY it's the best choice
- List pros and cons
- Provide alternatives
- Include source citations

Be direct, confident, and helpful. The LO is relying on your expertise."""


class EvaluatorAgent(BaseAgent):
    """
    Evaluator Agent - Compares specialist analyses and recommends best option.
    """
    
    def __init__(self):
        super().__init__("Evaluator", EVALUATOR_SYSTEM_PROMPT)
    
    async def analyze(self, scenario: dict, context: dict | None = None) -> dict:
        """
        Compare specialist analyses and generate recommendation.
        
        Args:
            scenario: The loan scenario
            context: Must contain 'specialist_analyses' list
        """
        specialist_analyses = context.get("specialist_analyses", []) if context else []
        
        if not specialist_analyses:
            return {
                "recommendation": None,
                "message": "No lender analyses available to compare.",
                "error": "No specialist data"
            }
        
        # Build comparison prompt
        user_prompt = f"""Scenario:
{self._format_scenario(scenario)}

Lender Analyses:
{self._format_analyses(specialist_analyses)}

Based on these analyses, provide your recommendation for the best lender/product for this scenario."""

        # Get text response (not JSON) for more natural recommendation
        response = await self._call_llm(
            user_prompt,
            response_format="text",
            max_tokens=2000,
            temperature=0.4
        )
        
        if isinstance(response, dict) and "error" in response:
            return response
        
        # Extract structured data from response
        return {
            "recommendation": self._extract_recommendation(specialist_analyses),
            "analysis": response,
            "alternatives": self._extract_alternatives(specialist_analyses),
            "sources": self._extract_sources(specialist_analyses)
        }
    
    def _format_analyses(self, analyses: list[dict]) -> str:
        """Format specialist analyses for comparison."""
        lines = []
        
        for analysis in analyses:
            lender = analysis.get("lender", "Unknown")
            lines.append(f"\n### {lender}")
            
            # Eligible products
            eligible = analysis.get("eligible_products", [])
            if eligible:
                lines.append("**Eligible Products:**")
                for prod in eligible:
                    program = prod.get("program", "Standard")
                    lines.append(f"  - {program}")
                    if prod.get("max_ltv"):
                        lines.append(f"    - Max LTV: {prod['max_ltv']}%")
                    if prod.get("rate_estimate"):
                        lines.append(f"    - Rate: {prod['rate_estimate']}")
                    if prod.get("pros"):
                        lines.append(f"    - Pros: {', '.join(prod['pros'])}")
                    if prod.get("cons"):
                        lines.append(f"    - Cons: {', '.join(prod['cons'])}")
            
            # Conditional products
            conditional = analysis.get("conditional_products", [])
            if conditional:
                lines.append("**Conditional:**")
                for prod in conditional:
                    lines.append(f"  - {prod.get('program', 'Unknown')}: {prod.get('missing_info', 'Info needed')}")
            
            # Summary
            if analysis.get("summary"):
                lines.append(f"**Summary:** {analysis['summary']}")
        
        return "\n".join(lines)
    
    def _extract_recommendation(self, analyses: list[dict]) -> dict | None:
        """Extract the best recommendation from analyses."""
        best = None
        best_score = 0
        
        for analysis in analyses:
            eligible = analysis.get("eligible_products", [])
            for prod in eligible:
                # Simple scoring
                score = 0
                if prod.get("status") == "eligible":
                    score += 10
                if prod.get("max_ltv"):
                    score += prod["max_ltv"] / 10
                if prod.get("pros"):
                    score += len(prod["pros"]) * 2
                if prod.get("cons"):
                    score -= len(prod["cons"])
                
                if score > best_score:
                    best_score = score
                    best = {
                        "lender": analysis.get("lender"),
                        "program": prod.get("program"),
                        "details": prod
                    }
        
        return best
    
    def _extract_alternatives(self, analyses: list[dict]) -> list[dict]:
        """Extract alternative options."""
        alternatives = []
        
        for analysis in analyses:
            eligible = analysis.get("eligible_products", [])
            for prod in eligible:
                alternatives.append({
                    "lender": analysis.get("lender"),
                    "program": prod.get("program"),
                    "max_ltv": prod.get("max_ltv"),
                    "rate_estimate": prod.get("rate_estimate")
                })
        
        # Return all except the first (which is likely the recommendation)
        return alternatives[1:4] if len(alternatives) > 1 else []
    
    def _extract_sources(self, analyses: list[dict]) -> list[str]:
        """Extract source citations."""
        sources = set()
        
        for analysis in analyses:
            for prod in analysis.get("eligible_products", []):
                if prod.get("source"):
                    sources.add(prod["source"])
        
        return list(sources)
