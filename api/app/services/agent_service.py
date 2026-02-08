from abc import ABC, abstractmethod
from openai import AsyncOpenAI
import json
from typing import Any

from app.config import settings


class BaseAgent(ABC):
    """Base class for all agents in the multi-agent system."""
    
    def __init__(self, name: str, system_prompt: str):
        self.name = name
        self.system_prompt = system_prompt
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_model
    
    @abstractmethod
    async def analyze(self, scenario: dict, context: dict | None = None) -> dict:
        """Analyze scenario and return structured response."""
        pass
    
    async def _call_llm(
        self,
        user_prompt: str,
        response_format: str = "json",
        temperature: float = 0.3,
        max_tokens: int = 2000
    ) -> str | dict:
        """Make LLM call with standard error handling."""
        try:
            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            
            kwargs = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens
            }
            
            if response_format == "json":
                kwargs["response_format"] = {"type": "json_object"}
            
            response = await self.client.chat.completions.create(**kwargs)
            content = response.choices[0].message.content
            
            if response_format == "json":
                return json.loads(content)
            return content
            
        except json.JSONDecodeError as e:
            return {"error": f"JSON parse error: {str(e)}", "raw": content}
        except Exception as e:
            return {"error": str(e)}
    
    def _format_scenario(self, scenario: dict) -> str:
        """Format scenario dict into readable text."""
        lines = []
        field_labels = {
            "state": "State",
            "loan_purpose": "Loan Purpose",
            "occupancy": "Occupancy",
            "property_type": "Property Type",
            "loan_amount": "Loan Amount",
            "ltv": "LTV",
            "fico": "FICO Score",
            "doc_type": "Documentation Type",
            "credit_events": "Credit Events"
        }
        
        for key, label in field_labels.items():
            if key in scenario and scenario[key]:
                value = scenario[key]
                if key == "loan_amount":
                    value = f"${value:,}" if isinstance(value, (int, float)) else value
                elif key == "ltv":
                    value = f"{value}%"
                lines.append(f"- {label}: {value}")
        
        return "\n".join(lines) if lines else "No scenario details provided"
