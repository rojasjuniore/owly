from openai import AsyncOpenAI
import json

from app.config import settings
from app.models.document import Rule


class LLMService:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_model
    
    async def extract_facts(self, message: str, current_facts: dict) -> dict:
        """
        Extract scenario facts from user message.
        Returns dict of extracted fields.
        """
        system_prompt = """You are an assistant that extracts mortgage loan scenario information from user messages.

Extract the following fields if mentioned:
- state: The US state where the property is located
- loan_purpose: purchase, rate_term_refi, or cashout
- occupancy: primary, second_home, or investment
- property_type: sfr, condo, 2-4_unit, or other
- loan_amount: The loan amount (number)
- ltv: Loan-to-value percentage (number)
- fico: Credit score (number)
- doc_type: full_doc, bank_statement, dscr, 1099, wvoe, asset_utilization, or other
- credit_events: none, bankruptcy, foreclosure, short_sale, or late_payments

Current known facts: {current_facts}

Respond with a JSON object containing ONLY the newly extracted fields.
If no new information is found, respond with an empty object {{}}.
Use lowercase values and underscores for multi-word values."""

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt.format(current_facts=json.dumps(current_facts))},
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
