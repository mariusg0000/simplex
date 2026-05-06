"""
tests/test_engine.py · Unit tests for the chat engine · Mocks LiteLLM to verify stream handling.
"""

import pytest
from src.engine.chat import stream_chat

@pytest.mark.asyncio
async def test_stream_chat_mock(mocker):
    """
    WHAT:    Tests the stream_chat function using a mock for litellm.acompletion.
    WHY:     Verifies that the engine correctly yields chunks from the LLM response.
    HOW:     Mocks the async iterator returned by litellm.
    """
    # Mock chunk structure
    class MockDelta:
        def __init__(self, content):
            self.content = content

    class MockChoice:
        def __init__(self, content):
            self.delta = MockDelta(content)

    class MockChunk:
        def __init__(self, content):
            self.choices = [MockChoice(content)]

    async def mock_acompletion(*args, **kwargs):
        chunks = [MockChunk("Hello"), MockChunk(" world!")]
        for chunk in chunks:
            yield chunk

    mocker.patch("litellm.acompletion", side_effect=mock_acompletion)
    
    messages = [{"role": "user", "content": "hi"}]
    collected_chunks = []
    async for chunk in stream_chat(messages):
        collected_chunks.append(chunk)
        
    assert collected_chunks == ["Hello", " world!"]
