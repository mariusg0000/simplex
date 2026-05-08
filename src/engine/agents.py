"""
src/engine/agents.py · Sub-agent architecture · Base classes for specialized internal agents.
"""

import json
import asyncio
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional, Set, Callable
import litellm
from src.config import settings
from src.engine.tools import registry


@dataclass
class AgentStep:
    agent_name: str
    round: int
    step_type: str  # "llm_call" | "tool_call" | "tool_result" | "error" | "done"
    content: str
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().strftime("%H:%M:%S")


activity_callback: ContextVar[Optional[Callable[[AgentStep], None]]] = (
    ContextVar("activity_callback", default=None)
)


class SubAgent:
    """
    WHAT:    Base class for internal specialized agents.
    WHY:     Encapsulates isolated LLM tasks (reranking, analysis, etc.) without polluting chat history.
    HOW:     Uses a private litellm call with a specific system prompt.
    """
    def __init__(self, name: str, system_prompt: str):
        self.name = name
        self.system_prompt = system_prompt

    async def run(self, task_input: str, model_override: Optional[str] = None) -> str:
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": task_input}
        ]

        response = await litellm.acompletion(
            model=model_override or settings.model,
            messages=messages,
            api_key=settings.openai_api_key,
            api_base=settings.openai_api_base,
            temperature=0.1
        )

        return response.choices[0].message.content


class RerankerAgent(SubAgent):
    def __init__(self):
        super().__init__(
            name="Reranker",
            system_prompt=(
                "You are an expert File System Analyst. Your task is to look at a list of raw file paths "
                "and select the most relevant ones based on the user's search context.\n"
                "RULES:\n"
                "1. Return a comma-separated list of ONLY the best paths (max 10).\n"
                "2. Prioritize files that look like source documents, code, or data (PDF, DOCX, MD, PY, CSV).\n"
                "3. Ignore temporary, cache, or build-related files if others are available.\n"
                "4. If nothing seems relevant, return 'NONE'.\n"
                "5. Output ONLY the paths, nothing else."
            )
        )

    async def rerank_files(self, query: str, file_paths: List[str]) -> List[str]:
        if not file_paths:
            return []

        task_input = f"User is searching for: '{query}'\nRaw results found:\n" + "\n".join(file_paths)
        result = await self.run(task_input)

        if "NONE" in result:
            return []

        cleaned_paths = [p.strip().strip("'\"") for p in result.replace("\n", ",").split(",") if p.strip()]
        return cleaned_paths[:10]


class ToolCapableAgent:
    """
    Standalone agent with multi-round tool loop.
    Runs its own LLM conversation with a filtered set of tools and CLI prompts.
    """
    def __init__(
        self,
        name: str,
        role_prompt: str,
        allowed_tools: Optional[list[str]] = None,
        allowed_cli: Optional[list[str]] = None,
        max_rounds: int = 15,
    ):
        self.name = name
        self.role_prompt = role_prompt
        self.allowed_tools: Set[str] = set(allowed_tools or [])
        self.allowed_cli: Set[str] = set(allowed_cli or [])
        self.max_rounds = max_rounds

    def _build_system_prompt(self) -> str:
        from src.prompts import load_cli_prompts
        prompts = load_cli_prompts()
        cli_sections = [prompts[k] for k in self.allowed_cli if k in prompts]
        cli_part = "\n\n".join(cli_sections) if cli_sections else ""
        if cli_part:
            return self.role_prompt + "\n\n" + cli_part
        return self.role_prompt

    def _get_allowed_schemas(self) -> list[dict]:
        all_schemas = registry.get_schemas()
        if not self.allowed_tools:
            return all_schemas
        return [s for s in all_schemas if s["function"]["name"] in self.allowed_tools]

    async def run(
        self,
        task_input: str,
        model_override: Optional[str] = None,
        on_step: Optional[Callable[[AgentStep], None]] = None,
        dynamic_context: Optional[str] = None,
    ) -> str:
        system_prompt = self._build_system_prompt()
        if dynamic_context:
            system_prompt += "\n\n" + dynamic_context
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task_input},
        ]

        for round_num in range(1, self.max_rounds + 1):
            try:
                schemas = self._get_allowed_schemas()

                response = await litellm.acompletion(
                    model=model_override or settings.model,
                    messages=messages,
                    api_key=settings.openai_api_key,
                    api_base=settings.openai_api_base,
                    temperature=0.1,
                    tools=schemas if schemas else None,
                    tool_choice="auto" if schemas else None,
                )
            except asyncio.CancelledError:
                if on_step:
                    on_step(AgentStep(self.name, round_num, "error", "Task cancelled by user."))
                return "Error: Task cancelled by user."
            except Exception as e:
                if on_step:
                    on_step(AgentStep(self.name, round_num, "error", str(e)))
                return f"Error: {str(e)}"

            choice = response.choices[0]
            msg = choice.message
            reasoning = getattr(msg, "reasoning_content", None) or ""

            if on_step:
                detail = f"Think: {reasoning[:180]}..." if reasoning else "Calling LLM..."
                on_step(AgentStep(self.name, round_num, "llm_call", detail))

            if not msg.tool_calls:
                content = msg.content or ""
                if on_step:
                    on_step(AgentStep(self.name, round_num, "done", content[:200]))
                return content

            assistant_msg = {"role": "assistant", "content": msg.content or None}
            if reasoning:
                assistant_msg["reasoning_content"] = reasoning

            formatted_calls = []
            for tc in msg.tool_calls:
                formatted_calls.append({
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                })
            assistant_msg["tool_calls"] = formatted_calls
            messages.append(assistant_msg)

            for tc in formatted_calls:
                name = tc["function"]["name"]
                raw_args = tc["function"]["arguments"]
                if on_step:
                    snippet = raw_args[:200] if name == "bash" else ""
                    label = f"bash: {snippet}..." if snippet else f"{name}(...)"
                    on_step(AgentStep(self.name, round_num, "tool_call", label))

                try:
                    args = json.loads(raw_args)
                except json.JSONDecodeError:
                    args = {}

                result = await registry.call(name, args)
                result_str = str(result)

                if on_step:
                    trunc = result_str[:200]
                    on_step(AgentStep(self.name, round_num, "tool_result", trunc))

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "name": name,
                    "content": result_str,
                })

        msg = "Error: Max rounds reached without final response."
        if on_step:
            on_step(AgentStep(self.name, self.max_rounds, "error", msg))
        return msg
