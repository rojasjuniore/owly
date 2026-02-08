from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, distinct

from app.models.document import Document, DocumentStatus
from app.services.leader_agent import LeaderAgent
from app.services.specialist_agent import SpecialistAgent
from app.services.evaluator_agent import EvaluatorAgent


class AgentFactory:
    """
    Factory for creating agents dynamically based on available lenders.
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self._specialist_cache: dict[str, SpecialistAgent] = {}
        self._available_lenders: list[str] | None = None
    
    async def get_available_lenders(self) -> list[str]:
        """Get list of lenders with active documents."""
        if self._available_lenders is None:
            result = await self.db.execute(
                select(distinct(Document.lender))
                .where(Document.status == DocumentStatus.ACTIVE)
                .where(Document.lender.isnot(None))
            )
            self._available_lenders = [row[0] for row in result.fetchall()]
        
        return self._available_lenders
    
    async def create_leader_agent(self) -> LeaderAgent:
        """Create the leader agent with knowledge of available lenders."""
        lenders = await self.get_available_lenders()
        return LeaderAgent(self.db, lenders)
    
    async def create_specialist_agent(self, lender: str) -> SpecialistAgent:
        """Create or get cached specialist agent for a lender."""
        if lender not in self._specialist_cache:
            self._specialist_cache[lender] = SpecialistAgent(self.db, lender)
        return self._specialist_cache[lender]
    
    def create_evaluator_agent(self) -> EvaluatorAgent:
        """Create the evaluator agent."""
        return EvaluatorAgent()
    
    async def create_specialists_for_lenders(
        self,
        lenders: list[str]
    ) -> dict[str, SpecialistAgent]:
        """Create specialist agents for a list of lenders."""
        available = await self.get_available_lenders()
        
        agents = {}
        for lender in lenders:
            # Only create if lender has documents
            if lender in available:
                agents[lender] = await self.create_specialist_agent(lender)
        
        return agents
    
    def clear_cache(self):
        """Clear cached agents (useful after document updates)."""
        self._specialist_cache.clear()
        self._available_lenders = None
