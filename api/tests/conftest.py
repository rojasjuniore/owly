"""
Pytest configuration and fixtures for Owly tests.
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.intent_classifier import IntentClassifier, IntentType
from app.services.general_qa_service import GeneralQAService
from app.services.chat_service import ChatService


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_db():
    """Mock database session."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def mock_openai_response():
    """Factory for mock OpenAI responses."""
    def _create_response(content: str):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = content
        return mock_response
    return _create_response


@pytest.fixture
def intent_classifier():
    """Create IntentClassifier instance."""
    return IntentClassifier()


@pytest.fixture
def general_qa_service(mock_db):
    """Create GeneralQAService with mocked DB."""
    return GeneralQAService(mock_db)


@pytest.fixture
def chat_service(mock_db):
    """Create ChatService with mocked DB."""
    return ChatService(mock_db)
