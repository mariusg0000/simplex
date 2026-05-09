"""
src/engine/agents.py · Sub-agent architecture + AgentRegistry for .md agents.
"""

import json
import asyncio
import logging
import re
import secrets
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Callable
import litellm
from src.config import settings
from src.engine.tools import registry

log = logging.getLogger("simplex.engine.agents")

AGENTS_BUILTIN_DIR = Path(__file__).resolve().parent.parent / "agents"
AGENTS_CUSTOM_DIR = Path.home() / ".simplexai" / "agents"

SELF_LEARNING_PROMPT = """
Analizează conversația agentului PDF de mai jos.

Identifică greșeli, eșecuri, și pattern-uri care merită documentate.
Scrie DOAR eșecuri și guideline-uri, NU pași generici de workflow.
Dacă toate lecțiile există deja în fișierul de experiență, nu face nimic.

EXPERIENCE FILE:
{exp_content}

CONVERSATION:
{messages}

Răspunde cu UPDATE_EXPERIENCE: ... sau NO_UPDATE
"""


@dataclass
class AgentDef:
    name: str
    enabled: bool
    description: str
    allowed_tools: list[str]
    role_prompt: str


def _parse_agent_md(content: str) -> dict:
    sections = {}
    pattern = r'^##\s+(\S+)\s*$'
    lines = content.split('\n')
    current_section = None
    current_lines = []

    for line in lines:
        m = re.match(pattern, line.strip())
        if m:
            if current_section:
                sections[current_section] = '\n'.join(current_lines).strip()
            current_section = m.group(1).lower()
            current_lines = []
        else:
            current_lines.append(line)

    if current_section:
        sections[current_section] = '\n'.join(current_lines).strip()

    return sections


class AgentRegistry:
    def __init__(self):
        self._agents: dict[str, AgentDef] = {}
        self._disabled: set[str] = set()
        self._discover(AGENTS_BUILTIN_DIR, "built-in")
        self._discover(AGENTS_CUSTOM_DIR, "custom")

    def _discover(self, directory: Path, source_label: str):
        if not directory.exists():
            return
        for filepath in sorted(directory.iterdir()):
            if filepath.suffix != ".md":
                continue
            try:
                content = filepath.read_text(encoding="utf-8")
                sections = _parse_agent_md(content)

                required = {"enabled", "agent_description", "allowed_tools", "role_prompt"}
                missing = required - set(sections.keys())
                if missing:
                    log.warning(
                        f"Agent {filepath.name} missing sections: {missing} — skipped"
                    )
                    continue

                name = filepath.stem
                enabled = sections["enabled"].strip().lower() == "enabled"
                description = sections["agent_description"].strip()
                allowed_tools = [
                    line.strip()
                    for line in sections["allowed_tools"].strip().split('\n')
                    if line.strip()
                ]
                role_prompt = sections["role_prompt"].strip()

                agent_def = AgentDef(
                    name=name,
                    enabled=enabled,
                    description=description,
                    allowed_tools=allowed_tools,
                    role_prompt=role_prompt,
                )

                self._agents[name] = agent_def
                log.info(f"Loaded agent '{name}' from {source_label}")
            except Exception as e:
                log.error(f"Failed to load agent {filepath.name}: {e}")

    def get_descriptions(self) -> str:
        parts = []
        for name, agent in self._agents.items():
            if agent.enabled and name not in self._disabled:
                parts.append(f"[Agent: {name}]\n{agent.description}")
        return "\n\n".join(parts)

    def get_schemas(self) -> list[dict]:
        schemas = []
        for name, agent in self._agents.items():
            if agent.enabled and name not in self._disabled:
                schemas.append({
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": agent.description,
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "task": {
                                    "type": "string",
                                    "description": f"Task for the {name} agent. Describe what you need in detail."
                                }
                            },
                            "required": ["task"],
                        },
                    },
                })
        return schemas

    async def _self_learning_phase(self, messages: list[dict], exp_path: Path):
        exp_path.parent.mkdir(parents=True, exist_ok=True)
        exp_content = exp_path.read_text() if exp_path.exists() else "None yet - first task."

        messages_text = json.dumps(messages, indent=2, ensure_ascii=False)
        prompt = SELF_LEARNING_PROMPT.format(
            exp_content=exp_content,
            messages=messages_text
        )

        try:
            response = await litellm.acompletion(
                model=settings.model,
                messages=[
                    {"role": "system", "content": "You are a PDF experience analyst."},
                    {"role": "user", "content": prompt}
                ],
                api_key=settings.openai_api_key,
                api_base=settings.openai_api_base,
                temperature=0.1
            )
            result = response.choices[0].message.content.strip()
        except Exception:
            return

        if result.startswith("UPDATE_EXPERIENCE:"):
            new_content = result[len("UPDATE_EXPERIENCE:"):].strip()
            combined = exp_content + "\n" + new_content
            exp_path.write_text(combined)

    async def call(self, name: str, arguments: dict) -> str:
        agent = self._agents.get(name)
        if not agent:
            return f"Error: Agent '{name}' not found."

        task = arguments.get("task", "")

        dynamic_context = ""
        if name == "create_pdf":
            temp_id = secrets.token_hex(8)
            tmp_dir = Path.home() / ".simplexai" / "tmp" / "pdf"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            temp_html_path = tmp_dir / f"{temp_id}.html"
            temp_pdf_path = tmp_dir / f"{temp_id}.pdf"
            dynamic_context = (
                f"TEMP FILE PATHS:\n"
                f"- Write HTML to: {temp_html_path}\n"
                f"- Final PDF will be at: {temp_pdf_path}\n"
                f"- Call generate_pdf(html_path='{temp_html_path}') after writing the HTML file."
            )

        tc_agent = ToolCapableAgent(
            name=name,
            role_prompt=agent.role_prompt,
            allowed_tools=agent.allowed_tools,
        )

        on_step = activity_callback.get()
        result = await tc_agent.run(task, on_step=on_step, dynamic_context=dynamic_context)

        if name == "create_pdf":
            exp_file = Path.home() / ".simplexai" / "experience" / "pdf_agent.md"
            await self._self_learning_phase(tc_agent.messages, exp_file)

        return result

    def disable(self, name: str):
        self._disabled.add(name)

    def enable(self, name: str):
        self._disabled.discard(name)

    def is_disabled(self, name: str) -> bool:
        return name in self._disabled

    def __contains__(self, name: str) -> bool:
        return name in self._agents


agent_registry = AgentRegistry()


@dataclass
class AgentStep:
    agent_name: str
    round: int
    step_type: str
    content: str
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().strftime("%H:%M:%S")


activity_callback: ContextVar[Optional[Callable[[AgentStep], None]]] = (
    ContextVar("activity_callback", default=None)
)


class SubAgent:
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
    def __init__(
        self,
        name: str,
        role_prompt: str,
        allowed_tools: Optional[list[str]] = None,
        allowed_cli: Optional[list[str]] = None,
        max_rounds: int = 20,
    ):
        self.name = name
        self.role_prompt = role_prompt
        self.allowed_tools: Set[str] = set(allowed_tools or [])
        self.allowed_cli: Set[str] = set(allowed_cli or [])
        self.max_rounds = max_rounds
        self.messages: list[dict] = []

    def _build_system_prompt(self) -> str:
        from src.prompts import load_cli_prompts
        prompts = load_cli_prompts()
        cli_sections = [prompts[k] for k in self.allowed_cli if k in prompts]
        cli_part = "\n\n".join(cli_sections) if cli_sections else ""
        if cli_part:
            return self.role_prompt + "\n\n" + cli_part
        return self.role_prompt

    def _get_allowed_schemas(self) -> list[dict]:
        if not self.allowed_tools:
            return registry.get_schemas()
        return [s for s in registry.schemas if s["function"]["name"] in self.allowed_tools]

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
        self.messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task_input},
        ]

        round_num = 1
        gave_fallback = False
        while round_num <= self.max_rounds:
            try:
                schemas = self._get_allowed_schemas()

                response = await litellm.acompletion(
                    model=model_override or settings.model,
                    messages=self.messages,
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
            self.messages.append(assistant_msg)

            for tc in formatted_calls:
                name = tc["function"]["name"]
                raw_args = tc["function"]["arguments"]

                if name == "task_done":
                    args = json.loads(raw_args)
                    result = args.get("result", "")
                    if on_step:
                        on_step(AgentStep(self.name, round_num, "tool_call", f"task_done({result[:100]})"))
                    if on_step:
                        on_step(AgentStep(self.name, round_num, "done", result[:200]))
                    return result

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

                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "name": name,
                    "content": result_str,
                })

            if round_num == self.max_rounds and not gave_fallback:
                self.messages.append({
                    "role": "user",
                    "content": "Maximum attempts reached. Document any new lessons in the experience file, then call task_done(result='...'). Do NOT continue working on the task — just document and exit."
                })
                self.max_rounds += 1
                gave_fallback = True

            round_num += 1

        msg = "Error: Max rounds reached without final response."
        if on_step:
            on_step(AgentStep(self.name, self.max_rounds, "error", msg))
        return msg
