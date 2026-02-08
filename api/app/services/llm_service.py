from openai import AsyncOpenAI
import json

from app.config import settings
from app.models.document import Rule


class LLMService:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_model
    
    async def extract_facts(
        self, 
        message: str, 
        current_facts: dict,
        last_question_field: str | None = None
    ) -> dict:
        """
        Extract scenario facts from user message.
        Returns dict of extracted fields.
        """
        # Build context about what field we're asking for
        field_context = ""
        if last_question_field:
            field_context = f"""
IMPORTANT: The user was just asked about "{last_question_field}".
If the user's message is a short answer (like "Single family", "California", "Purchase", etc.), 
map it to the appropriate "{last_question_field}" field value.
"""

        system_prompt = """You are an assistant that extracts mortgage loan scenario information from user messages.

Extract the following fields if mentioned:
- state: The US state where the property is located (e.g., "California" → "california", "CA" → "california")
- loan_purpose: purchase, rate_term_refi, or cashout
- occupancy: primary, second_home, or investment  
- property_type: sfr (Single Family, SFR, House), condo (Condo, Condominium), 2-4_unit (Duplex, Triplex, Fourplex), or other
- loan_amount: The loan amount (number only, no $ or commas)
- ltv: Loan-to-value percentage (number only, no %)
- fico: Credit score (number, e.g., 740)
- doc_type: full_doc (W-2, Full Doc), bank_statement (Bank Statement), dscr (DSCR, rental income), 1099, wvoe, asset_utilization, or other
- credit_events: none (No, None, Clean), bankruptcy, foreclosure, short_sale, or late_payments
{field_context}
Current known facts: {current_facts}

MAPPING GUIDE for short answers:
- "Single family", "SFR", "House", "Single-family home" → property_type: "sfr"
- "Condo", "Condominium" → property_type: "condo"  
- "Duplex", "2-unit", "Triplex", "3-unit", "Fourplex", "4-unit" → property_type: "2-4_unit"
- "Primary", "Primary residence", "Owner occupied" → occupancy: "primary"
- "Investment", "Rental", "NOO" → occupancy: "investment"
- "Purchase", "Buying" → loan_purpose: "purchase"
- "Refi", "Refinance", "Rate and term" → loan_purpose: "rate_term_refi"
- "Cash out", "Cash-out refi" → loan_purpose: "cashout"
- "W-2", "Full doc", "Tax returns" → doc_type: "full_doc"
- "Bank statements", "Self-employed" → doc_type: "bank_statement"
- "None", "No", "Clean credit" → credit_events: "none"

Respond with a JSON object containing ONLY the newly extracted fields.
If no new information is found, respond with an empty object {{}}.
Use lowercase values and underscores for multi-word values."""

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt.format(
                    current_facts=json.dumps(current_facts),
                    field_context=field_context
                )},
                {"role": "user", "content": message}
            ],
            response_format={"type": "json_object"},
            temperature=0
        )
        
        try:
            extracted = json.loads(response.choices[0].message.content)
            return extracted
        except json.JSONDecodeError:
            return {}
    
    async def generate_eligibility_response(
        self,
        facts: dict,
        rules: list[Rule],
        chunks: list[dict]
    ) -> str:
        """
        Generate an eligibility response based on matched rules and retrieved content.
        """
        # Format rules for the prompt
        rules_text = ""
        for i, rule in enumerate(rules[:5], 1):
            rules_text += f"""
{i}. {rule.lender} - {rule.program or 'Standard Program'}
   - FICO: {rule.fico_min or 'N/A'} - {rule.fico_max or 'N/A'}
   - Max LTV: {rule.ltv_max or 'N/A'}%
   - Loan Range: ${rule.loan_min or 'N/A'} - ${rule.loan_max or 'N/A'}
   - Purposes: {', '.join(rule.purposes) if rule.purposes else 'All'}
   - Doc Types: {', '.join(rule.doc_types) if rule.doc_types else 'All'}
   - Notes: {rule.notes or 'None'}
"""
        
        # Format chunks for context
        context_text = "\n\n".join([
            f"[{c['lender']} - {c['filename']}]\n{c['content'][:500]}"
            for c in chunks[:5]
        ])
        
        system_prompt = """You are Owly, an AI assistant helping Loan Officers find eligible mortgage programs.

Based on the scenario and matching rules, provide:
1. A clear eligibility assessment (Eligible / Conditional / Not Eligible)
2. Top 1-3 recommended programs with brief explanations
3. Key factors that support eligibility
4. Any conditions or warnings ("what could break")

Be concise and professional. Always cite the lender/program name."""

        user_prompt = f"""Scenario:
{json.dumps(facts, indent=2)}

Matching Programs:
{rules_text}

Additional Context:
{context_text}

Provide the eligibility assessment:"""

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,
            max_tokens=1000
        )
        
        return response.choices[0].message.content
