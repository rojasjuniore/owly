import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID

from app.models.conversation import Conversation, Message, MessageRole
from app.services.agent_factory import AgentFactory
from app.services.llm_service import LLMService


REQUIRED_FIELDS = [
    "state",
    "loan_purpose",
    "occupancy",
    "property_type",
    "loan_amount",
    "ltv",
    "fico",
    "doc_type",
    "credit_events",
]

FIELD_QUESTIONS = {
    "state": "What state is the property located in?",
    "loan_purpose": "What is the loan purpose? (Purchase, Rate/Term Refinance, or Cash-Out)",
    "occupancy": "What is the occupancy type? (Primary Residence, Second Home, or Investment)",
    "property_type": "What is the property type? (Single Family, Condo, 2-4 Unit, etc.)",
    "loan_amount": "What is the target loan amount?",
    "ltv": "What is the estimated LTV (Loan-to-Value) percentage?",
    "fico": "What is the borrower's FICO score or range?",
    "doc_type": "What income documentation type? (Full Doc, Bank Statement, DSCR, etc.)",
    "credit_events": "Are there any recent credit events? (Bankruptcy, Foreclosure, Short Sale, or None)",
}

# Timeout for each specialist agent
SPECIALIST_TIMEOUT = 15  # seconds


class ChatService:
    """
    Multi-Agent Chat Service
    
    Flow:
    1. Extract facts from user message
    2. Check if we have minimum required fields
    3. If incomplete: ask follow-up
    4. If complete: run multi-agent eligibility analysis
       a. Leader Agent: pre-filter lenders (top 3-5)
       b. Specialist Agents: analyze each lender in parallel
       c. Evaluator Agent: compare and recommend
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.agent_factory = AgentFactory(db)
        self.llm = LLMService()
    
    async def process_message(
        self,
        message: str,
        conversation_id: UUID | None = None
    ) -> dict:
        """Process user message and return response."""
        
        # 1. Get or create conversation
        if conversation_id:
            result = await self.db.execute(
                select(Conversation).where(Conversation.id == conversation_id)
            )
            conversation = result.scalar_one_or_none()
            if not conversation:
                conversation = Conversation()
                self.db.add(conversation)
        else:
            conversation = Conversation()
            self.db.add(conversation)
        
        await self.db.flush()
        
        # 2. Save user message
        user_msg = Message(
            conversation_id=conversation.id,
            role=MessageRole.USER,
            content=message
        )
        self.db.add(user_msg)
        
        # 3. Extract facts from message
        current_facts = conversation.facts or {}
        
        # Get the last question field from previous missing_fields
        # This tells the LLM what field we were asking about
        last_question_field = None
        if conversation.missing_fields and len(conversation.missing_fields) > 0:
            last_question_field = conversation.missing_fields[0]
        
        extracted = await self.llm.extract_facts(
            message, 
            current_facts,
            last_question_field=last_question_field
        )
        updated_facts = {**current_facts, **extracted}
        conversation.facts = updated_facts
        
        # 4. Check missing fields
        missing = self._get_missing_fields(updated_facts)
        conversation.missing_fields = missing
        
        # 5. Generate response
        if missing:
            # Ask for most important missing field
            priority_field = missing[0]
            response = FIELD_QUESTIONS.get(
                priority_field,
                f"Could you please provide the {priority_field.replace('_', ' ')}?"
            )
            confidence = self._calculate_field_confidence(updated_facts, missing)
            citations = None
        else:
            # Run multi-agent eligibility analysis
            eligibility_result = await self._run_multi_agent_analysis(updated_facts)
            response = eligibility_result["response"]
            confidence = eligibility_result.get("confidence", 85)
            citations = eligibility_result.get("citations")
        
        # Save assistant message
        assistant_msg = Message(
            conversation_id=conversation.id,
            role=MessageRole.ASSISTANT,
            content=response,
            metadata={"citations": citations} if citations else {}
        )
        self.db.add(assistant_msg)
        
        await self.db.flush()
        
        return {
            "response": response,
            "conversation_id": conversation.id,
            "facts": updated_facts,
            "missing_fields": missing,
            "confidence": confidence,
            "citations": citations
        }
    
    def _get_missing_fields(self, facts: dict) -> list[str]:
        """Return list of required fields that are missing."""
        return [f for f in REQUIRED_FIELDS if f not in facts or facts[f] is None]
    
    def _calculate_field_confidence(self, facts: dict, missing: list[str]) -> int:
        """Calculate confidence based on field completeness."""
        total = len(REQUIRED_FIELDS)
        present = total - len(missing)
        return int((present / total) * 40)  # Max 40 points for fields
    
    async def _run_multi_agent_analysis(self, scenario: dict) -> dict:
        """
        Run the multi-agent eligibility analysis:
        1. Leader: identify top 3-5 lenders
        2. Specialists: analyze each in parallel
        3. Evaluator: compare and recommend
        """
        try:
            # 1. Leader Agent - Pre-filter lenders
            leader = await self.agent_factory.create_leader_agent()
            leader_result = await leader.analyze(scenario)
            
            top_lenders = leader_result.get("top_candidates", [])
            
            if not top_lenders:
                return {
                    "response": self._format_no_lenders_response(leader_result),
                    "confidence": 50,
                    "citations": []
                }
            
            # 2. Specialist Agents - Analyze in parallel
            specialists = await self.agent_factory.create_specialists_for_lenders(top_lenders)
            
            specialist_tasks = [
                self._run_specialist_with_timeout(agent, scenario)
                for agent in specialists.values()
            ]
            
            specialist_results = await asyncio.gather(
                *specialist_tasks,
                return_exceptions=True
            )
            
            # Filter successful results
            valid_results = [
                r for r in specialist_results
                if isinstance(r, dict) and "error" not in r
            ]
            
            if not valid_results:
                return {
                    "response": self._format_analysis_error_response(specialist_results),
                    "confidence": 40,
                    "citations": []
                }
            
            # 3. Evaluator Agent - Compare and recommend
            evaluator = self.agent_factory.create_evaluator_agent()
            evaluator_result = await evaluator.analyze(
                scenario,
                context={"specialist_analyses": valid_results}
            )
            
            # Format final response
            return {
                "response": self._format_final_response(evaluator_result, valid_results),
                "confidence": self._calculate_analysis_confidence(valid_results),
                "citations": evaluator_result.get("sources", [])
            }
            
        except Exception as e:
            return {
                "response": f"I encountered an error during analysis: {str(e)}. Please try again.",
                "confidence": 0,
                "citations": [],
                "error": str(e)
            }
    
    async def _run_specialist_with_timeout(self, agent, scenario: dict) -> dict:
        """Run specialist with timeout."""
        try:
            return await asyncio.wait_for(
                agent.analyze(scenario),
                timeout=SPECIALIST_TIMEOUT
            )
        except asyncio.TimeoutError:
            return {"error": f"Timeout analyzing {agent.lender_name}"}
        except Exception as e:
            return {"error": str(e)}
    
    def _format_no_lenders_response(self, leader_result: dict) -> str:
        """Format response when no lenders are found."""
        return f"""Based on my analysis, I couldn't identify suitable lenders for this scenario.

**Understanding:** {leader_result.get('understanding', 'N/A')}

This could mean:
- The scenario has requirements not covered by our current lender guidelines
- Some parameters may need adjustment (FICO, LTV, etc.)
- The documentation type may limit available options

Would you like to:
1. Adjust any scenario parameters?
2. Explore different documentation options?
3. Get more details on what might be limiting eligibility?"""
    
    def _format_analysis_error_response(self, results: list) -> str:
        """Format response when analysis fails."""
        errors = [r.get("error", "Unknown error") for r in results if isinstance(r, dict)]
        return f"""I encountered issues analyzing the lenders. Please try again.

Technical details: {', '.join(errors[:3])}"""
    
    def _format_final_response(self, evaluator_result: dict, specialist_results: list) -> str:
        """Format the final recommendation response."""
        analysis = evaluator_result.get("analysis", "")
        
        if analysis:
            return analysis
        
        # Fallback formatting if analysis is empty
        recommendation = evaluator_result.get("recommendation")
        alternatives = evaluator_result.get("alternatives", [])
        
        response_parts = []
        
        if recommendation:
            response_parts.append(f"## Recommendation\n\n**{recommendation['lender']} - {recommendation['program']}**\n")
        
        if alternatives:
            response_parts.append("\n### Alternatives\n")
            for alt in alternatives[:2]:
                response_parts.append(f"- {alt['lender']} - {alt['program']}")
        
        if not response_parts:
            # Last resort: list all eligible products
            response_parts.append("## Eligible Options\n")
            for result in specialist_results:
                lender = result.get("lender", "Unknown")
                for prod in result.get("eligible_products", []):
                    response_parts.append(f"- **{lender}**: {prod.get('program', 'Standard')}")
        
        return "\n".join(response_parts) if response_parts else "No eligible products found."
    
    def _calculate_analysis_confidence(self, results: list) -> int:
        """Calculate confidence based on analysis results."""
        if not results:
            return 40
        
        # Base score
        score = 50
        
        # Add points for each lender with eligible products
        for result in results:
            eligible = result.get("eligible_products", [])
            if eligible:
                score += 10
        
        # Cap at 95
        return min(95, score)
