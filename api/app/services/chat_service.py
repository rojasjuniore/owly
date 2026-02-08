"""
Chat Service - Orchestrates the conversation flow

NEW FLEXIBLE FLOW:
1. Classify user intent (general question, product search, eligibility, scenario input)
2. Route to appropriate handler
3. Always try to be helpful, even with incomplete data
4. Always cite sources
"""
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID

from app.models.conversation import Conversation, Message, MessageRole
from app.services.intent_classifier import IntentClassifier, IntentType
from app.services.general_qa_service import GeneralQAService
from app.services.agent_factory import AgentFactory
from app.services.llm_service import LLMService


# Minimum fields for a preliminary recommendation
MINIMUM_FIELDS = ["fico"]  # We can give suggestions with just credit score

# All fields for complete analysis
ALL_FIELDS = [
    "state", "loan_purpose", "occupancy", "property_type",
    "loan_amount", "ltv", "fico", "doc_type", "credit_events"
]

FIELD_DESCRIPTIONS = {
    "state": "property state",
    "loan_purpose": "loan purpose (purchase/refi/cash-out)",
    "occupancy": "occupancy type (primary/investment/second home)",
    "property_type": "property type (SFR/condo/multi-unit)",
    "loan_amount": "loan amount",
    "ltv": "LTV percentage",
    "fico": "credit score",
    "doc_type": "income documentation type",
    "credit_events": "recent credit events"
}

SPECIALIST_TIMEOUT = 15


class ChatService:
    """
    Flexible Multi-Agent Chat Service
    
    Handles:
    - General questions about lenders/products
    - Product searches ("best lender for bank statement")
    - Quick eligibility checks ("does any lender do X")
    - Full scenario analysis (with preliminary suggestions when incomplete)
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.intent_classifier = IntentClassifier()
        self.general_qa = GeneralQAService(db)
        self.agent_factory = AgentFactory(db)
        self.llm = LLMService()
    
    async def process_message(
        self,
        message: str,
        conversation_id: UUID | None = None
    ) -> dict:
        """Process user message with flexible routing."""
        
        # 1. Get or create conversation
        conversation = await self._get_or_create_conversation(conversation_id)
        await self.db.flush()
        
        # 2. Save user message
        user_msg = Message(
            conversation_id=conversation.id,
            role=MessageRole.USER,
            content=message
        )
        self.db.add(user_msg)
        
        # 3. Get current state
        current_facts = conversation.facts or {}
        last_question_field = None
        if conversation.missing_fields and len(conversation.missing_fields) > 0:
            last_question_field = conversation.missing_fields[0]
        
        # 4. Classify intent
        last_assistant_msg = await self._get_last_assistant_message(conversation.id)
        intent_result = await self.intent_classifier.classify(
            message,
            last_question=last_assistant_msg,
            current_facts=current_facts
        )
        
        intent = intent_result.get("intent", IntentType.SCENARIO_INPUT)
        entities = intent_result.get("extracted_entities", {})
        
        # 5. Route based on intent
        if intent == IntentType.GENERAL_QUESTION:
            result = await self.general_qa.answer_general_question(message)
            response = result["response"]
            citations = result.get("citations", [])
            # Don't update facts for general questions
            updated_facts = current_facts
            
        elif intent == IntentType.PRODUCT_SEARCH:
            product_type = entities.get("product_type_asked") or entities.get("doc_type")
            result = await self.general_qa.answer_product_search(message, product_type)
            response = result["response"]
            citations = result.get("citations", [])
            updated_facts = current_facts
            
        elif intent == IntentType.ELIGIBILITY_CHECK:
            result = await self.general_qa.answer_eligibility_check(message, entities)
            response = result["response"]
            citations = result.get("citations", [])
            # Merge any extracted entities
            updated_facts = {**current_facts, **self._clean_entities(entities)}
        
        elif intent == IntentType.SUMMARY_REQUEST:
            # User wants a summary of what we know and what's missing
            updated_facts = current_facts
            response = self._format_summary_response(current_facts)
            citations = []
            
        else:
            # SCENARIO_INPUT or FOLLOW_UP - Extract facts and give recommendations
            try:
                extracted = await self.llm.extract_facts(
                    message, 
                    current_facts,
                    last_question_field=last_question_field
                )
            except Exception as e:
                extracted = {}
            
            # Also merge entities from intent classification
            updated_facts = {**current_facts, **extracted, **self._clean_entities(entities)}
            
            # Generate response based on completeness
            try:
                result = await self._generate_scenario_response(updated_facts)
                response = result["response"]
                citations = result.get("citations", [])
            except Exception as e:
                # Fallback on any error
                response = f"I understood your scenario. {self._format_facts_summary(updated_facts)}"
                citations = []
        
        # 6. Update conversation
        conversation.facts = updated_facts
        missing = self._get_missing_fields(updated_facts)
        conversation.missing_fields = missing
        
        # 7. Calculate confidence
        confidence = self._calculate_confidence(updated_facts, missing)
        
        # 8. Save assistant message
        assistant_msg = Message(
            conversation_id=conversation.id,
            role=MessageRole.ASSISTANT,
            content=response,
            extra_data={"citations": citations, "intent": intent}
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
    
    async def _get_or_create_conversation(self, conversation_id: UUID | None) -> Conversation:
        """Get existing conversation or create new one."""
        if conversation_id:
            result = await self.db.execute(
                select(Conversation).where(Conversation.id == conversation_id)
            )
            conversation = result.scalar_one_or_none()
            if conversation:
                return conversation
        
        conversation = Conversation()
        self.db.add(conversation)
        return conversation
    
    async def _get_last_assistant_message(self, conversation_id: UUID) -> str | None:
        """Get the last assistant message for context."""
        result = await self.db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .where(Message.role == MessageRole.ASSISTANT)
            .order_by(Message.created_at.desc())
            .limit(1)
        )
        msg = result.scalar_one_or_none()
        return msg.content if msg else None
    
    def _clean_entities(self, entities: dict) -> dict:
        """Remove None values from entities."""
        return {k: v for k, v in entities.items() if v is not None}
    
    def _format_facts_summary(self, facts: dict) -> str:
        """Format facts as a simple summary."""
        if not facts:
            return "Please tell me about the loan scenario."
        parts = []
        for key, value in facts.items():
            if value:
                label = FIELD_DESCRIPTIONS.get(key, key.replace("_", " ")).title()
                parts.append(f"{label}: {value}")
        if parts:
            return "Here's what I have: " + ", ".join(parts) + "."
        return ""
    
    def _format_summary_response(self, facts: dict) -> str:
        """Format a detailed summary of client profile and missing information."""
        response_parts = []
        
        # Client Profile section
        response_parts.append("## 📋 Client Profile\n")
        if facts:
            for key, value in facts.items():
                if value is not None:
                    label = FIELD_DESCRIPTIONS.get(key, key.replace("_", " ")).title()
                    response_parts.append(f"- **{label}:** {value}")
        else:
            response_parts.append("*No information provided yet.*")
        
        # Missing Information section
        missing = self._get_missing_fields(facts)
        if missing:
            response_parts.append("\n\n## ❓ Missing Information\n")
            for field in missing:
                label = FIELD_DESCRIPTIONS.get(field, field.replace("_", " ")).title()
                response_parts.append(f"- {label}")
        
        # Confidence
        confidence = self._calculate_confidence(facts, missing)
        response_parts.append(f"\n\n**Confidence Level:** {confidence}%")
        
        if confidence >= 70:
            response_parts.append("\n\n*I have enough information to provide recommendations. Just ask!*")
        else:
            response_parts.append("\n\n*Please provide more details for better recommendations.*")
        
        return "\n".join(response_parts)
    
    def _get_missing_fields(self, facts: dict) -> list[str]:
        """Return list of fields that are missing."""
        return [f for f in ALL_FIELDS if f not in facts or facts[f] is None]
    
    def _calculate_confidence(self, facts: dict, missing: list[str]) -> int:
        """Calculate confidence score based on available data."""
        total = len(ALL_FIELDS)
        present = total - len(missing)
        
        # Base score from field completeness (0-60)
        field_score = int((present / total) * 60)
        
        # Bonus for critical fields (0-40)
        critical_bonus = 0
        if facts.get("fico"):
            critical_bonus += 15
        if facts.get("ltv"):
            critical_bonus += 10
        if facts.get("state"):
            critical_bonus += 5
        if facts.get("loan_purpose"):
            critical_bonus += 5
        if facts.get("doc_type"):
            critical_bonus += 5
        
        return min(95, field_score + critical_bonus)
    
    async def _generate_scenario_response(self, facts: dict) -> dict:
        """
        Generate response based on scenario completeness.
        
        - If minimal data: Give preliminary suggestions + ask what's missing
        - If good data: Run multi-agent analysis
        - Always cite sources
        """
        missing = self._get_missing_fields(facts)
        confidence = self._calculate_confidence(facts, missing)
        
        # Check if we have minimum data for a preliminary response
        has_minimum = bool(facts.get("fico") or facts.get("doc_type") or facts.get("loan_purpose"))
        
        if not has_minimum:
            # Not enough data - ask for basics
            return {
                "response": self._format_initial_prompt(),
                "citations": []
            }
        
        if confidence >= 70:
            # Enough data for full analysis
            return await self._run_multi_agent_analysis(facts)
        else:
            # Give preliminary suggestions + mention what's missing
            return await self._generate_preliminary_response(facts, missing)
    
    def _format_initial_prompt(self) -> str:
        """Format initial prompt when we have no data."""
        return """👋 I'm Owly, your mortgage eligibility assistant!

I can help you find the right lender programs. Here's what I can do:

**Ask me anything:**
- "Which lenders offer bank statement loans?"
- "Does any DSCR lender accept 5 units?"
- "What's the minimum score for FHA?"

**Or describe your scenario:**
Tell me about your client's situation - credit score, property type, loan purpose, etc. I'll suggest matching programs even with partial information!

What would you like to know?"""
    
    async def _generate_preliminary_response(self, facts: dict, missing: list[str]) -> dict:
        """Generate preliminary suggestions with incomplete data."""
        
        # Check if we have any lenders in the system
        available_lenders = await self.agent_factory.get_available_lenders()
        
        if not available_lenders:
            # No lenders in system - give general guidance
            return self._format_no_lenders_response(facts, missing)
        
        # Run a simplified analysis
        try:
            leader = await self.agent_factory.create_leader_agent()
            leader_result = await leader.analyze(facts)
            
            top_lenders = leader_result.get("top_candidates", [])
            understanding = leader_result.get("understanding", "")
            
            # Format response
            response_parts = ["## Preliminary Analysis\n"]
            
            if understanding:
                response_parts.append(f"**Understanding:** {understanding}\n")
            
            if top_lenders:
                response_parts.append("\n**Potential Matches:**")
                for lender in top_lenders[:3]:
                    if isinstance(lender, dict):
                        response_parts.append(f"- **{lender.get('lender', 'Unknown')}** - {lender.get('reason', '')}")
                    else:
                        response_parts.append(f"- {lender}")
            else:
                response_parts.append("\n*I need a bit more information to identify specific lenders.*")
            
            # Add what's missing
            if missing:
                response_parts.append("\n\n**Missing Information:**")
                top_missing = missing[:3]
                for field in top_missing:
                    desc = FIELD_DESCRIPTIONS.get(field, field.replace("_", " "))
                    response_parts.append(f"- {desc}")
            
            return {
                "response": "\n".join(response_parts),
                "citations": leader_result.get("sources", [])
            }
            
        except Exception as e:
            # Fallback response on error
            missing_text = ""
            if missing:
                missing_text = f"To give better recommendations, could you tell me:\n- {FIELD_DESCRIPTIONS.get(missing[0], 'more details')}"
            return {
                "response": f"I'm analyzing your scenario. {missing_text}",
                "citations": []
            }
    
    def _format_no_lenders_response(self, facts: dict, missing: list[str]) -> dict:
        """Format response when no lenders are loaded in the system."""
        response_parts = ["## Scenario Analysis\n"]
        
        # Show what we understood
        response_parts.append("**Client Profile:**")
        for key, value in facts.items():
            if value:
                label = FIELD_DESCRIPTIONS.get(key, key.replace("_", " ")).title()
                response_parts.append(f"- {label}: {value}")
        
        # General guidance based on facts
        fico = facts.get("fico")
        if fico:
            response_parts.append(f"\n**General Guidance for FICO {fico}:**")
            if fico >= 740:
                response_parts.append("- Excellent credit! You should qualify for the best rates and terms.")
                response_parts.append("- Conventional, FHA, VA, and most Non-QM products should be available.")
            elif fico >= 680:
                response_parts.append("- Good credit. Most conventional and government programs available.")
                response_parts.append("- Some rate adjustments may apply for Non-QM products.")
            elif fico >= 620:
                response_parts.append("- FHA is likely your best option (minimum 580 with 3.5% down).")
                response_parts.append("- Some conventional lenders may work, but expect higher rates.")
                response_parts.append("- Non-QM options available but with stricter terms.")
            else:
                response_parts.append("- Limited options. FHA may work with 10% down (500-579 score).")
                response_parts.append("- Consider credit repair before applying.")
        
        # What's missing
        if missing:
            response_parts.append("\n**To provide specific lender recommendations, I need:**")
            for field in missing[:4]:
                desc = FIELD_DESCRIPTIONS.get(field, field.replace("_", " "))
                response_parts.append(f"- {desc}")
        
        response_parts.append("\n*Note: No lender guidelines are loaded yet. Once they are, I can give specific recommendations.*")
        
        return {
            "response": "\n".join(response_parts),
            "citations": []
        }
    
    async def _run_multi_agent_analysis(self, scenario: dict) -> dict:
        """
        Run the full multi-agent eligibility analysis with citations.
        """
        try:
            # 1. Leader Agent - Pre-filter lenders
            leader = await self.agent_factory.create_leader_agent()
            leader_result = await leader.analyze(scenario)
            
            top_candidates = leader_result.get("top_candidates", [])
            all_citations = leader_result.get("sources", [])
            
            # Extract lender names from candidates (can be dicts or strings)
            top_lenders = []
            for candidate in top_candidates:
                if isinstance(candidate, dict):
                    lender_name = candidate.get("lender")
                    if lender_name:
                        top_lenders.append(lender_name)
                elif isinstance(candidate, str):
                    top_lenders.append(candidate)
            
            if not top_lenders:
                missing = self._get_missing_fields(scenario)
                missing_text = ""
                if missing:
                    missing_text = "\n\n**Missing Information:**\n"
                    for f in missing[:3]:
                        missing_text += f"- {FIELD_DESCRIPTIONS.get(f, f)}\n"
                
                return {
                    "response": f"Based on the criteria provided, I couldn't identify strongly matching lenders.\n\n"
                              f"**Client Profile:**\n{self._format_facts(scenario)}"
                              f"{missing_text}",
                    "citations": all_citations
                }
            
            # 2. Specialist Agents - Analyze in parallel
            specialists = await self.agent_factory.create_specialists_for_lenders(top_lenders)
            
            specialist_tasks = [
                self._run_specialist_with_timeout(agent, scenario)
                for agent in specialists.values()
            ]
            
            specialist_results = await asyncio.gather(*specialist_tasks, return_exceptions=True)
            
            # Collect valid results and citations
            valid_results = []
            for r in specialist_results:
                if isinstance(r, dict) and "error" not in r:
                    valid_results.append(r)
                    if r.get("sources"):
                        all_citations.extend(r["sources"])
            
            if not valid_results:
                return {
                    "response": "I encountered issues analyzing the lenders. Please try again.",
                    "citations": all_citations
                }
            
            # 3. Evaluator Agent - Compare and recommend
            evaluator = self.agent_factory.create_evaluator_agent()
            evaluator_result = await evaluator.analyze(
                scenario,
                context={"specialist_analyses": valid_results}
            )
            
            if evaluator_result.get("sources"):
                all_citations.extend(evaluator_result["sources"])
            
            # Format final response with citations
            response = self._format_final_response(evaluator_result, valid_results, scenario)
            
            return {
                "response": response,
                "citations": all_citations
            }
            
        except Exception as e:
            return {
                "response": f"I encountered an error during analysis: {str(e)}. Please try again.",
                "citations": []
            }
    
    async def _run_specialist_with_timeout(self, agent, scenario: dict) -> dict:
        """Run specialist with timeout."""
        try:
            return await asyncio.wait_for(
                agent.analyze(scenario),
                timeout=SPECIALIST_TIMEOUT
            )
        except asyncio.TimeoutError:
            return {"error": f"Timeout analyzing {getattr(agent, 'lender_name', 'lender')}"}
        except Exception as e:
            return {"error": str(e)}
    
    def _format_facts(self, facts: dict) -> str:
        """Format facts as readable summary."""
        lines = []
        for key, value in facts.items():
            if value is not None:
                label = FIELD_DESCRIPTIONS.get(key, key.replace("_", " ")).title()
                lines.append(f"- {label}: {value}")
        return "\n".join(lines) if lines else "No details provided yet."
    
    def _format_final_response(self, evaluator_result: dict, specialist_results: list, scenario: dict) -> str:
        """Format the final recommendation with citations."""
        analysis = evaluator_result.get("analysis", "")
        
        if analysis:
            # Add scenario summary at the end
            response = analysis
            response += f"\n\n---\n**Client Profile:**\n{self._format_facts(scenario)}"
            return response
        
        # Fallback formatting
        response_parts = []
        recommendation = evaluator_result.get("recommendation")
        alternatives = evaluator_result.get("alternatives", [])
        
        if recommendation:
            response_parts.append(f"## ✅ Recommended\n\n**{recommendation.get('lender', 'Unknown')}** - {recommendation.get('program', 'Standard')}")
            if recommendation.get("reason"):
                response_parts.append(f"\n{recommendation['reason']}")
        
        if alternatives:
            response_parts.append("\n\n### Alternatives")
            for alt in alternatives[:2]:
                response_parts.append(f"\n- **{alt.get('lender', '')}**: {alt.get('program', '')} - {alt.get('reason', '')}")
        
        if not response_parts:
            # List eligible products from specialists
            response_parts.append("## Eligible Options\n")
            for result in specialist_results:
                lender = result.get("lender", "Unknown")
                for prod in result.get("eligible_products", []):
                    response_parts.append(f"- **{lender}**: {prod.get('program', 'Standard')}")
        
        response_parts.append(f"\n\n---\n**Client Profile:**\n{self._format_facts(scenario)}")
        
        return "\n".join(response_parts)
