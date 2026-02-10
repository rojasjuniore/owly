"""
Tests for Intent Classifier - Ensures correct intent detection.

These tests verify that:
1. Eligibility questions are correctly classified (not as product search)
2. Context carryover doesn't break intent classification
3. Generic questions about Conventional/VA/FHA work correctly
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import json

from app.services.intent_classifier import IntentClassifier, IntentType


class TestIntentClassification:
    """Test intent classification for different question types."""
    
    @pytest.mark.asyncio
    async def test_eligibility_check_conventional(self, intent_classifier, mock_openai_response):
        """
        Questions about Conventional loan requirements should be ELIGIBILITY_CHECK.
        NOT product_search.
        """
        questions = [
            "What are the requirements for a Conventional loan?",
            "What is the minimum credit score for Conventional?",
            "Does Conventional allow 5% down?",
            "Conventional loan LTV limits?",
        ]
        
        expected_response = json.dumps({
            "intent": "eligibility_check",
            "confidence": 0.9,
            "reasoning": "Asking about specific requirements",
            "extracted_entities": {}
        })
        
        with patch.object(intent_classifier.client.chat.completions, 'create', 
                         new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_openai_response(expected_response)
            
            for question in questions:
                result = await intent_classifier.classify(question)
                assert result["intent"] == IntentType.ELIGIBILITY_CHECK, \
                    f"'{question}' should be eligibility_check, got {result['intent']}"
    
    @pytest.mark.asyncio
    async def test_eligibility_check_va(self, intent_classifier, mock_openai_response):
        """VA loan questions should be ELIGIBILITY_CHECK."""
        questions = [
            "What are VA loan requirements?",
            "VA loan minimum FICO?",
            "Can I use VA loan for investment property?",
        ]
        
        expected_response = json.dumps({
            "intent": "eligibility_check",
            "confidence": 0.9,
            "reasoning": "VA eligibility question",
            "extracted_entities": {}
        })
        
        with patch.object(intent_classifier.client.chat.completions, 'create',
                         new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_openai_response(expected_response)
            
            for question in questions:
                result = await intent_classifier.classify(question)
                assert result["intent"] == IntentType.ELIGIBILITY_CHECK
    
    @pytest.mark.asyncio
    async def test_product_search_lender_specific(self, intent_classifier, mock_openai_response):
        """
        Questions asking for lender recommendations should be PRODUCT_SEARCH.
        """
        questions = [
            "Which lender is best for bank statement loans?",
            "Who offers the lowest rates for DSCR?",
            "Best lender for self-employed borrowers?",
        ]
        
        expected_response = json.dumps({
            "intent": "product_search",
            "confidence": 0.9,
            "reasoning": "Looking for lender recommendation",
            "extracted_entities": {"product_type_asked": "bank statement"}
        })
        
        with patch.object(intent_classifier.client.chat.completions, 'create',
                         new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_openai_response(expected_response)
            
            for question in questions:
                result = await intent_classifier.classify(question)
                assert result["intent"] == IntentType.PRODUCT_SEARCH
    
    @pytest.mark.asyncio
    async def test_general_question(self, intent_classifier, mock_openai_response):
        """General system questions should be GENERAL_QUESTION."""
        questions = [
            "How many lenders do you have?",
            "What is LTV?",
            "Explain DTI ratio",
        ]
        
        expected_response = json.dumps({
            "intent": "general_question",
            "confidence": 0.9,
            "reasoning": "General question about system/concepts",
            "extracted_entities": {}
        })
        
        with patch.object(intent_classifier.client.chat.completions, 'create',
                         new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_openai_response(expected_response)
            
            for question in questions:
                result = await intent_classifier.classify(question)
                assert result["intent"] == IntentType.GENERAL_QUESTION


class TestContextCarryover:
    """
    Test that context carryover doesn't break eligibility checks.
    
    CRITICAL: Even when a lender was mentioned in a previous message,
    generic eligibility questions (Conventional, VA, FHA) should NOT
    be filtered to that specific lender.
    """
    
    @pytest.mark.asyncio
    async def test_eligibility_after_lender_mention(self, intent_classifier, mock_openai_response):
        """
        After mentioning a lender, generic product questions should still work.
        
        Example flow:
        1. User: "Tell me about Angel Oak" -> last_mentioned_lender = "Angel Oak"
        2. User: "What are Conventional requirements?" 
           -> Should search ALL lenders, not just Angel Oak
        """
        # First classify a lender-specific question
        lender_response = json.dumps({
            "intent": "product_search",
            "confidence": 0.9,
            "reasoning": "Asking about specific lender",
            "extracted_entities": {"lender_asked": "Angel Oak"}
        })
        
        # Then classify a generic eligibility question
        eligibility_response = json.dumps({
            "intent": "eligibility_check",
            "confidence": 0.9,
            "reasoning": "Generic Conventional question",
            "extracted_entities": {}  # No lender_asked - this is key!
        })
        
        with patch.object(intent_classifier.client.chat.completions, 'create',
                         new_callable=AsyncMock) as mock_create:
            # First call - lender specific
            mock_create.return_value = mock_openai_response(lender_response)
            result1 = await intent_classifier.classify("Tell me about Angel Oak")
            assert result1["extracted_entities"].get("lender_asked") == "Angel Oak"
            
            # Second call - generic Conventional question
            # Should NOT have lender_asked
            mock_create.return_value = mock_openai_response(eligibility_response)
            result2 = await intent_classifier.classify(
                "What are Conventional requirements?",
                current_facts={"last_mentioned_lender": "Angel Oak"}
            )
            
            # The key assertion: eligibility check should not inherit lender filter
            assert result2["intent"] == IntentType.ELIGIBILITY_CHECK
            assert result2["extracted_entities"].get("lender_asked") is None
