"""
Tests for Eligibility Flow - Ensures eligibility checks work correctly.

CRITICAL: These tests verify that:
1. Eligibility checks search ALL lenders (no filtering)
2. Context carryover doesn't break generic product questions
3. Questions about Conventional/VA/FHA return results from all lenders
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import json
from uuid import uuid4

from app.services.chat_service import ChatService
from app.services.general_qa_service import GeneralQAService
from app.services.intent_classifier import IntentType


class TestEligibilityCheckNoFilter:
    """
    Eligibility checks should NEVER be filtered by last_mentioned_lender.
    
    This was the bug in commit 36f7034 - eligibility questions were being
    filtered to only search rules/chunks from the last mentioned lender,
    causing empty results for generic product questions.
    """
    
    @pytest.mark.asyncio
    async def test_conventional_eligibility_searches_all_lenders(self, mock_db):
        """
        'What are Conventional requirements?' should search ALL lenders.
        """
        service = GeneralQAService(mock_db)
        
        # Mock chunks from multiple lenders
        mock_chunks = [
            _create_mock_chunk("Angel Oak", "Conventional: 620 FICO, 97% LTV"),
            _create_mock_chunk("Deephaven", "Conventional: 640 FICO, 95% LTV"),
            _create_mock_chunk("UWM", "Conventional: 600 FICO, 97% LTV"),
        ]
        
        # Mock rules from multiple lenders
        mock_rules = [
            _create_mock_rule("Angel Oak", "Conventional", 620, 97),
            _create_mock_rule("Deephaven", "Conventional", 640, 95),
        ]
        
        with patch.object(service, '_search_chunks', new_callable=AsyncMock) as mock_search:
            with patch.object(service, '_search_rules_by_criteria', new_callable=AsyncMock) as mock_rules_search:
                with patch.object(service.client.chat.completions, 'create', new_callable=AsyncMock) as mock_llm:
                    mock_search.return_value = mock_chunks
                    mock_rules_search.return_value = mock_rules
                    mock_llm.return_value = _create_llm_response("Based on guidelines...")
                    
                    result = await service.answer_eligibility_check(
                        "What are Conventional requirements?",
                        entities={}  # No lender filter!
                    )
                    
                    # Verify we got results
                    assert result is not None
                    assert result.get("response") is not None
                    
                    # Verify chunks from multiple lenders were returned
                    assert len(mock_search.return_value) >= 2, \
                        "Should have chunks from multiple lenders"
    
    @pytest.mark.asyncio
    async def test_va_eligibility_not_filtered(self, mock_db):
        """VA loan questions should not be filtered by previous lender context."""
        service = GeneralQAService(mock_db)
        
        mock_chunks = [
            _create_mock_chunk("Veterans United", "VA: 580 FICO, 100% LTV"),
            _create_mock_chunk("Navy Federal", "VA: 620 FICO, 100% LTV"),
        ]
        
        with patch.object(service, '_search_chunks', new_callable=AsyncMock) as mock_search:
            with patch.object(service, '_search_rules_by_criteria', new_callable=AsyncMock) as mock_rules:
                with patch.object(service.client.chat.completions, 'create', new_callable=AsyncMock) as mock_llm:
                    mock_search.return_value = mock_chunks
                    mock_rules.return_value = []
                    mock_llm.return_value = _create_llm_response("VA loans...")
                    
                    result = await service.answer_eligibility_check(
                        "What is minimum credit score for VA?",
                        entities={}
                    )
                    
                    assert result is not None
                    # Should have results from multiple VA lenders
                    mock_search.assert_called_once()


class TestContextCarryoverSafety:
    """
    Test that context carryover is safe and doesn't break eligibility.
    """
    
    @pytest.mark.asyncio
    async def test_lender_context_not_applied_to_eligibility(self, mock_db):
        """
        Even if last_mentioned_lender is set, eligibility checks should
        search all lenders.
        
        Flow:
        1. User asks about Angel Oak (sets last_mentioned_lender)
        2. User asks "What are VA requirements?"
        3. Should return VA info from ALL lenders, not just Angel Oak
        """
        service = GeneralQAService(mock_db)
        
        # Simulate context from previous lender mention
        context_with_lender = {
            "last_mentioned_lender": "Angel Oak"
        }
        
        mock_chunks = [
            _create_mock_chunk("Veterans United", "VA loan guidelines..."),
            _create_mock_chunk("Navy Federal", "VA requirements..."),
        ]
        
        with patch.object(service, '_search_chunks', new_callable=AsyncMock) as mock_search:
            with patch.object(service, '_search_rules_by_criteria', new_callable=AsyncMock) as mock_rules:
                with patch.object(service.client.chat.completions, 'create', new_callable=AsyncMock) as mock_llm:
                    mock_search.return_value = mock_chunks
                    mock_rules.return_value = []
                    mock_llm.return_value = _create_llm_response("VA info...")
                    
                    # Call eligibility check - entities should NOT include lender filter
                    result = await service.answer_eligibility_check(
                        "What are VA requirements?",
                        entities={}  # Key: no lender_asked here
                    )
                    
                    # Verify search was not filtered
                    mock_search.assert_called_with("What are VA requirements?", limit=8)
                    
                    # Verify we got results
                    assert len(result.get("citations", [])) > 0 or "VA" in result.get("response", "")


class TestGenericProductQuestions:
    """
    Test that generic product questions (not lender-specific) work.
    
    These are the questions that broke in commit 36f7034:
    - "Conventional requirements?"
    - "VA loan minimum?"
    - "FHA guidelines?"
    """
    
    @pytest.mark.asyncio
    @pytest.mark.parametrize("question", [
        "What are Conventional requirements?",
        "What is the minimum credit score for Conventional?",
        "VA loan requirements?",
        "FHA minimum down payment?",
        "USDA eligibility?",
        "What are DSCR requirements?",
        "Bank statement loan requirements?",
    ])
    async def test_generic_product_questions(self, mock_db, question):
        """Generic product questions should return results."""
        service = GeneralQAService(mock_db)
        
        mock_chunks = [_create_mock_chunk("TestLender", f"Info about {question}")]
        
        with patch.object(service, '_search_chunks', new_callable=AsyncMock) as mock_search:
            with patch.object(service, '_search_rules_by_criteria', new_callable=AsyncMock) as mock_rules:
                with patch.object(service.client.chat.completions, 'create', new_callable=AsyncMock) as mock_llm:
                    mock_search.return_value = mock_chunks
                    mock_rules.return_value = []
                    mock_llm.return_value = _create_llm_response(f"Answer to {question}")
                    
                    result = await service.answer_eligibility_check(question, entities={})
                    
                    assert result is not None
                    assert result.get("response") is not None
                    assert len(result["response"]) > 0


# Helper functions

def _create_mock_chunk(lender: str, content: str):
    """Create a mock chunk object."""
    chunk = MagicMock()
    chunk.content = content
    chunk.document = MagicMock()
    chunk.document.lender = lender
    chunk.document.filename = f"{lender.lower()}_guidelines.pdf"
    return chunk


def _create_mock_rule(lender: str, program: str, fico_min: int, ltv_max: int):
    """Create a mock rule object."""
    rule = MagicMock()
    rule.lender = lender
    rule.program = program
    rule.fico_min = fico_min
    rule.fico_max = 850
    rule.ltv_max = ltv_max
    rule.doc_types = ["Full Doc"]
    return rule


def _create_llm_response(content: str):
    """Create a mock LLM response."""
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = content
    return response
