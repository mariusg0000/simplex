"""
tests/test_engine.py · Unit tests for the chat engine · Mocks LiteLLM to verify stream handling.
"""

import pytest
from src.engine.chat import stream_chat


@pytest.mark.asyncio
async def test_stream_chat_mock(mocker):
    """
    WHAT:    Tests the stream_chat function using a mock for litellm.acompletion.
    WHY:     Verifies that the engine correctly yields content chunks from the LLM response.
    HOW:     Mocks the async iterator returned by litellm, filters for content chunks.
    """
    class MockDelta:
        def __init__(self, content):
            self.content = content
            self.tool_calls = None

    class MockChoice:
        def __init__(self, content):
            self.delta = MockDelta(content)
            self.finish_reason = None

    class MockChunk:
        def __init__(self, content):
            self.choices = [MockChoice(content)]

    class MockFinalChunk:
        def __init__(self):
            self.choices = [MockFinalChoice()]

    class MockFinalChoice:
        def __init__(self):
            self.delta = MockDelta("")
            self.finish_reason = "stop"

    async def mock_acompletion(*args, **kwargs):
        yield MockChunk("Hello")
        yield MockChunk(" world!")
        yield MockFinalChunk()

    mocker.patch("litellm.acompletion", side_effect=mock_acompletion)

    messages = [{"role": "user", "content": "hi"}]
    content_chunks = []
    async for chunk in stream_chat(messages):
        if chunk.get("type") == "content":
            content_chunks.append(chunk["content"])

    assert "".join(content_chunks) == "Hello world!"
