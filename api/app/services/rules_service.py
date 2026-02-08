from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from decimal import Decimal

from app.models.document import Rule, DocumentStatus
from app.db import async_session


class RulesService:
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def match(self, facts: dict) -> list[Rule]:
        """
        Match scenario facts against structured rules.
        Returns list of matching rules sorted by relevance.
        """
        try:
            query = select(Rule).where(Rule.status == DocumentStatus.ACTIVE)
            
            # Build filters based on available facts
            filters = []
            
            # FICO filter
            if facts.get("fico"):
                try:
                    fico = int(facts["fico"])
                    filters.append(
                        or_(
                            Rule.fico_min.is_(None),
                            Rule.fico_min <= fico
                        )
                    )
                    filters.append(
                        or_(
                            Rule.fico_max.is_(None),
                            Rule.fico_max >= fico
                        )
                    )
                except (ValueError, TypeError):
                    pass
            
            # LTV filter
            if facts.get("ltv"):
                try:
                    ltv = Decimal(str(facts["ltv"]))
                    filters.append(
                        or_(
                            Rule.ltv_max.is_(None),
                            Rule.ltv_max >= ltv
                        )
                    )
                except (ValueError, TypeError):
                    pass
            
            # Loan amount filter
            if facts.get("loan_amount"):
                try:
                    # Parse loan amount (handle formats like "$500,000" or "500000")
                    amount_str = str(facts["loan_amount"]).replace("$", "").replace(",", "")
                    amount = Decimal(amount_str)
                    filters.append(
                        or_(
                            Rule.loan_min.is_(None),
                            Rule.loan_min <= amount
                        )
                    )
                    filters.append(
                        or_(
                            Rule.loan_max.is_(None),
                            Rule.loan_max >= amount
                        )
                    )
                except (ValueError, TypeError):
                    pass
            
            # Apply filters
            if filters:
                query = query.where(and_(*filters))
            
            # Use separate session to avoid transaction conflicts
            async with async_session() as session:
                result = await session.execute(query)
                rules = result.scalars().all()
            
            # Post-filter and score rules
            scored_rules = []
            for rule in rules:
                score = self._score_rule(rule, facts)
                if score > 0:
                    scored_rules.append((score, rule))
            
            # Sort by score descending
            scored_rules.sort(key=lambda x: x[0], reverse=True)
            
            return [rule for _, rule in scored_rules]
        except Exception as e:
            print(f"RulesService.match error: {e}")
            return []
    
    def _score_rule(self, rule: Rule, facts: dict) -> int:
        """
        Score a rule based on how well it matches the facts.
        Higher score = better match.
        """
        score = 0
        
        # Purpose match
        if rule.purposes and facts.get("loan_purpose"):
            purpose = facts["loan_purpose"].lower()
            if any(p.lower() in purpose or purpose in p.lower() for p in rule.purposes):
                score += 20
        
        # Occupancy match
        if rule.occupancies and facts.get("occupancy"):
            occupancy = facts["occupancy"].lower()
            if any(o.lower() in occupancy or occupancy in o.lower() for o in rule.occupancies):
                score += 20
        
        # Property type match
        if rule.property_types and facts.get("property_type"):
            prop_type = facts["property_type"].lower()
            if any(p.lower() in prop_type or prop_type in p.lower() for p in rule.property_types):
                score += 15
        
        # Doc type match
        if rule.doc_types and facts.get("doc_type"):
            doc_type = facts["doc_type"].lower()
            if any(d.lower() in doc_type or doc_type in d.lower() for d in rule.doc_types):
                score += 25
        
        # FICO comfort (how much room above minimum)
        if rule.fico_min and facts.get("fico"):
            try:
                fico = int(facts["fico"])
                if fico >= rule.fico_min:
                    comfort = min(20, (fico - rule.fico_min) // 10)
                    score += comfort
            except (ValueError, TypeError):
                pass
        
        # LTV comfort (how much room below maximum)
        if rule.ltv_max and facts.get("ltv"):
            try:
                ltv = float(facts["ltv"])
                ltv_max = float(rule.ltv_max)
                if ltv <= ltv_max:
                    comfort = min(10, int((ltv_max - ltv) / 2))
                    score += comfort
            except (ValueError, TypeError):
                pass
        
        return score
    
    async def get_by_lender(self, lender: str) -> list[Rule]:
        """Get all active rules for a specific lender."""
        try:
            # Use separate session to avoid transaction conflicts
            async with async_session() as session:
                result = await session.execute(
                    select(Rule)
                    .where(Rule.lender == lender)
                    .where(Rule.status == DocumentStatus.ACTIVE)
                )
                return result.scalars().all()
        except Exception as e:
            print(f"RulesService.get_by_lender error for {lender}: {e}")
            return []
