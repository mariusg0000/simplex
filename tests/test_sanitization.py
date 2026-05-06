import pytest
from src.engine.chat import sanitize_messages

def test_sanitize_messages_preserves_reasoning():
    """
    Verifies that sanitize_messages preserves the reasoning_content field for assistant messages.
    """
    messages = [
        {"role": "user", "content": "hello"},
        {
            "role": "assistant", 
            "content": "Hi there!", 
            "reasoning_content": "I am thinking about saying hi."
        }
    ]
    
    sanitized = sanitize_messages(messages)
    
    # Check that reasoning_content is preserved in the assistant message
    assistant_msg = next(m for m in sanitized if m["role"] == "assistant")
    assert "reasoning_content" in assistant_msg
    assert assistant_msg["reasoning_content"] == "I am thinking about saying hi."
    assert assistant_msg["content"] == "Hi there!"

def test_sanitize_messages_strips_unknown_fields():
    """
    Verifies that unknown fields are still stripped.
    """
    messages = [
        {"role": "user", "content": "hello", "unknown_field": "ignore me"}
    ]
    
    sanitized = sanitize_messages(messages)
    assert "unknown_field" not in sanitized[0]
