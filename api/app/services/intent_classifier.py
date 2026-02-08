"""
Intent Classifier - Determines the type of user question/input
"""
from openai import AsyncOpenAI
import json
from app.config import settings


class IntentType:
    GENERAL_QUESTION = "general_question"      # "How many lenders do you have?"
    PRODUCT_SEARCH = "product_search"          # "Best lender for bank statement?"
    ELIGIBILITY_CHECK = "eligibility_check"    # "Does any DSCR lender do 5 units?"
    SCENARIO_INPUT = "scenario_input"          # Borrower data input
    FOLLOW_UP = "follow_up"                    # Answer to a previous question
    CLARIFICATION = "clarification"            # "What do you mean by LTV?"
    SUMMARY_REQUEST = "summary_request"        # "Summarize what you know", "What info do you have?"


class IntentClassifier:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_model
    
    async def classify(
        self, 
        message: str, 
        last_question: str | None = None,
        current_facts: dict | None = None
    ) -> dict:
        """
        Classify the user's message intent.
        
        Returns:
            {
                "intent": "general_question|product_search|eligibility_check|scenario_input|follow_up",
                "confidence": 0.0-1.0,
                "extracted_entities": {...}  # Any entities found in the message
            }
        """
        context = ""
        if last_question:
            context += f"\nLast system question: {last_question}"
        if current_facts:
            context += f"\nKnown facts about scenario: {json.dumps(current_facts)}"
        
        system_prompt = """You are an intent classifier for a mortgage lending assistant.

Classify the user's message into one of these intents:

1. **general_question** - Questions about the system, available lenders, or general mortgage concepts
   Examples: "How many lenders do you have?", "What products are available?", "What is LTV?"

2. **product_search** - Looking for specific product types or lender capabilities
   Examples: "Best lender for bank statement loans?", "Who offers DSCR?", "Which lender has lowest rates?"

3. **eligibility_check** - Checking if a specific scenario qualifies
   Examples: "Does any lender do 5 units?", "Can I get a loan with 580 score?", "Any lender allow 85% LTV on investment?"

4. **scenario_input** - Providing borrower/property details for eligibility analysis
   Examples: "My client has 740 score, 20% down, buying in California", "FICO 680, DTI 45%, refinance"

5. **follow_up** - Direct answer to a previous question (short responses)
   Examples: "California", "Yes", "Single family", "80%", "Purchase"
   IMPORTANT: If there was a previous question and the answer is short/direct, this is likely follow_up.

6. **summary_request** - Asking for a summary of current information or what's missing
   Examples: "Summarize what you know", "What info do you have?", "What am I missing?", "Show me the client profile", "What information have I provided?"

Also extract any mortgage-related entities found in the message.
{context}

Respond with JSON:
{{
    "intent": "<intent_type>",
    "confidence": <0.0-1.0>,
    "reasoning": "<brief explanation>",
    "extracted_entities": {{
        "fico": <number or null>,
        "state": "<string or null>",
        "loan_purpose": "<string or null>",
        "property_type": "<string or null>",
        "ltv": <number or null>,
        "loan_amount": <number or null>,
        "doc_type": "<string or null>",
        "product_type_asked": "<string or null>",
        "lender_asked": "<string or null>"
    }}
}}"""

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt.format(context=context)},
                {"role": "user", "content": message}
            ],
            response_format={"type": "json_object"},
            temperature=0
        )
        
        try:
            result = json.loads(response.choices[0].message.content)
            return result
        except json.JSONDecodeError:
            return {
                "intent": IntentType.SCENARIO_INPUT,
                "confidence": 0.5,
                "extracted_entities": {}
            }
