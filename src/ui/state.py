"""
src/ui/state.py · Shared application state · Holds globals accessed by UI components.
"""

import uuid
import asyncio
from typing import Any, Optional

current_session_id: str = str(uuid.uuid4())
chat_title: str = "New Chat"
messages: list = []
active_task: Optional[asyncio.Task] = None

scroll_area: Any = None
chat_content: Any = None
message_input: Any = None
drawer: Any = None
sidebar_content: Any = None
show_reasoning_checkbox: Any = None

from src.config import settings


def get_system_prompt() -> dict:
    """Returns the current system prompt with strategic guidelines."""
    return {
        "role": "system",
        "content": settings.system_prompt + (
            "\n\nSTRATEGIC GUIDELINES:\n"
            "1. BE EFFICIENT: Do not perform more than 2 search attempts for the same request.\n"
            "2. TRUST THE TOOLS: If a search tool returns results, those are the best matches. Present them immediately.\n"
            "3. NO REDUNDANCY: Do not call the same tool with slightly different parameters if you already have relevant data.\n"
            "4. RERANKER TRUST: The file search tool uses an internal Reranker. The top results it returns are the final candidates."
        )
    }


def init_messages():
    """Initializes messages with the dynamic system prompt."""
    import src.ui.state as state
    state.messages = [get_system_prompt()]
