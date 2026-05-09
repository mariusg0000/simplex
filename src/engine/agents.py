"""
src/engine/agents.py · Sub-agent architecture + AgentRegistry for .md agents.
"""

import asyncio
import json
import logging
import re
import time
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import List, Dict, Any, Optional, Set, Callable

import litellm
from src.config import settings
from src.engine.tools import registry, agent_params_ctx

log = logging.getLogger("simplex.engine.agents")

AGENTS_BUILTIN_DIR = Path(__file__).resolve().parent.parent / "agents"
AGENTS_CUSTOM_DIR = Path.home() / ".simplexai" / "agents"

@dataclass
class AgentDef:
    name: str
    enabled: bool
    description: str
    allowed_tools: list[str]
    role_prompt: str
    execute_script: str = ""
    done_tool: str = "task_done"


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
            if filepath.suffix != ".md" or filepath.name.lower() == "readme.md":
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
                execute_script = sections.get("execute_script", "").strip()
                done_tool_raw = sections.get("done_tool", "").strip()
                done_tool = done_tool_raw if done_tool_raw else "task_done"

                agent_def = AgentDef(
                    name=name,
                    enabled=enabled,
                    description=description,
                    allowed_tools=allowed_tools,
                    role_prompt=role_prompt,
                    execute_script=execute_script,
                    done_tool=done_tool,
                )

                self._agents[name] = agent_def
                log.info("Loaded agent '%s' from %s (tools=%s, done='%s', has_exec=%s)",
                         name, source_label, allowed_tools, done_tool,
                         "yes" if execute_script else "no")
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

    async def call(self, name: str, arguments: dict) -> str:
        agent = self._agents.get(name)
        if not agent:
            return f"Error: Agent '{name}' not found."

        task = arguments.get("task", "")
        log.info("=== Agent '%s' called ===", name)
        log.info("task (first 300): %s", task[:300])

        dynamic_context = ""
        token = None
        if agent.execute_script:
            log.info("▶ running execute_script for '%s'", name)
            try:
                proc = await asyncio.create_subprocess_exec(
                    "python3", "-c", agent.execute_script,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()
                if proc.returncode == 0 and stdout:
                    output = stdout.decode().strip()
                    log.info("✓ execute_script output: %s", output)
                    params_dict = json.loads(output)
                    token = agent_params_ctx.set(params_dict)
                    dynamic_context = "Agent session initialized."
                else:
                    err_msg = stderr.decode().strip() or f"exit code {proc.returncode}"
                    log.error("✗ execute_script for '%s' failed: %s", name, err_msg)
            except Exception as e:
                log.error("✗ execute_script for '%s' error: %s", name, e)

        tc_agent = ToolCapableAgent(
            name=name,
            role_prompt=agent.role_prompt,
            allowed_tools=agent.allowed_tools,
            done_tool_name=agent.done_tool,
        )

        on_step = activity_callback.get()
        on_stream = agent_stream_callback.get()
        try:
            log.info("▶ running agent '%s' (max_rounds=%d, done_tool='%s')",
                     name, tc_agent.max_rounds, tc_agent.done_tool_name)
            result = await tc_agent.run(task, on_step=on_step, on_stream=on_stream, dynamic_context=dynamic_context)
            log.info("=== Agent '%s' done ===", name)
            log.info("result: %s", result[:500])
            return result
        finally:
            if token is not None:
                agent_params_ctx.reset(token)

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


@dataclass
class AgentStreamChunk:
    """A chunk of streaming LLM output (reasoning or content) for live display."""
    agent_name: str
    round: int
    chunk_type: str  # "reasoning" or "content"
    content: str
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().strftime("%H:%M:%S")


agent_stream_callback: ContextVar[Optional[Callable[[AgentStreamChunk], None]]] = (
    ContextVar("agent_stream_callback", default=None)
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
        done_tool_name: str = "task_done",
    ):
        self.name = name
        self.role_prompt = role_prompt
        self.allowed_tools: Set[str] = set(allowed_tools or [])
        self.allowed_cli: Set[str] = set(allowed_cli or [])
        self.max_rounds = max_rounds
        self.done_tool_name = done_tool_name
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

    _COALESCE_SEC = 0.3  # Streaming chunk emit interval

    async def run(
        self,
        task_input: str,
        model_override: Optional[str] = None,
        on_step: Optional[Callable[[AgentStep], None]] = None,
        on_stream: Optional[Callable[[AgentStreamChunk], None]] = None,
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
            log.info("┌─ %s round %d/%d", self.name, round_num, self.max_rounds)

            # --- STREAMING LLM CALL ---
            schemas = self._get_allowed_schemas()
            if on_step:
                on_step(AgentStep(self.name, round_num, "llm_call", "Thinking..."))

            response = None
            try:
                response = await litellm.acompletion(
                    model=model_override or settings.model,
                    messages=self.messages,
                    api_key=settings.openai_api_key,
                    api_base=settings.openai_api_base,
                    temperature=0.1,
                    tools=schemas if schemas else None,
                    tool_choice="auto" if schemas else None,
                    stream=True,
                )
            except asyncio.CancelledError:
                log.warning("! agent '%s' cancelled by user", self.name)
                if on_step:
                    on_step(AgentStep(self.name, round_num, "error", "Task cancelled by user."))
                return "Error: Task cancelled by user."
            except Exception as e:
                log.error("! agent '%s' LLM error: %s", self.name, e)
                if on_step:
                    on_step(AgentStep(self.name, round_num, "error", str(e)))
                return f"Error: {str(e)}"

            # --- CONSUME STREAM ---
            full_reasoning = ""
            full_content = ""
            tool_calls_stream: dict[int, dict] = {}
            buf = {"reasoning": "", "content": ""}
            last_emit = 0.0
            try:
                async for chunk in response:
                    delta = chunk.choices[0].delta

                    r = getattr(delta, "reasoning_content", None)
                    if r:
                        full_reasoning += r
                        buf["reasoning"] += r
                    if delta.content:
                        full_content += delta.content
                        buf["content"] += delta.content
                    if delta.tool_calls:
                        for tc in delta.tool_calls:
                            idx = tc.index
                            if idx not in tool_calls_stream:
                                tool_calls_stream[idx] = {
                                    "id": "", "function": {"name": "", "arguments": ""},
                                }
                            if tc.id:
                                tool_calls_stream[idx]["id"] = tc.id
                            if tc.function:
                                if tc.function.name:
                                    tool_calls_stream[idx]["function"]["name"] += tc.function.name
                                if tc.function.arguments:
                                    tool_calls_stream[idx]["function"]["arguments"] += tc.function.arguments

                    now = time.monotonic()
                    if (buf["reasoning"] or buf["content"]) and (now - last_emit) >= self._COALESCE_SEC:
                        if on_stream:
                            for ct in ("reasoning", "content"):
                                if buf[ct]:
                                    on_stream(AgentStreamChunk(self.name, round_num, ct, buf[ct]))
                                    buf[ct] = ""
                        last_emit = now

            except asyncio.CancelledError:
                log.warning("! agent '%s' streaming cancelled", self.name)
                if on_step:
                    on_step(AgentStep(self.name, round_num, "error", "Streaming cancelled."))
                return "Error: Task cancelled."
            except Exception as e:
                log.error("! agent '%s' streaming error: %s", self.name, e)
                if on_step:
                    on_step(AgentStep(self.name, round_num, "error", f"Stream error: {e}"))
                return f"Error: Streaming failed: {e}"

            # Flush remaining stream buffer
            if on_stream:
                for ct in ("reasoning", "content"):
                    if buf[ct]:
                        on_stream(AgentStreamChunk(self.name, round_num, ct, buf[ct]))

            # --- RECONSTRUCT MESSAGE FROM STREAM ---
            reasoning = full_reasoning or ""
            tc_list = []
            for idx in sorted(tool_calls_stream.keys()):
                tc_data = tool_calls_stream[idx]
                tc_list.append(SimpleNamespace(
                    id=tc_data["id"],
                    function=SimpleNamespace(
                        name=tc_data["function"]["name"],
                        arguments=tc_data["function"]["arguments"],
                    ),
                ))

            has_tool_calls = bool(tc_list)
            log.info("│ %s round %d: reasoning=%d chars, content=%d chars, tool_calls=%d",
                     self.name, round_num, len(full_reasoning), len(full_content), len(tc_list))

            if not has_tool_calls:
                output = full_content or ""
                log.info("└─ %s done (no tool calls, %d chars)", self.name, len(output))
                if on_step:
                    on_step(AgentStep(self.name, round_num, "done", output[:200]))
                return output

            # Build assistant message for history (identical format to non-streaming)
            assistant_msg = {"role": "assistant", "content": full_content or None}
            if reasoning:
                assistant_msg["reasoning_content"] = reasoning

            formatted_calls = []
            for tc in tc_list:
                fmt = {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                formatted_calls.append(fmt)
            assistant_msg["tool_calls"] = formatted_calls
            self.messages.append(assistant_msg)

            log.info("│ %s round %d: %d tool call(s)", self.name, round_num, len(formatted_calls))
            if reasoning:
                log.info("│ reasoning: %s...", reasoning[:200])

            for tc in formatted_calls:
                name = tc["function"]["name"]
                raw_args = tc["function"]["arguments"]

                if name == self.done_tool_name:
                    args = json.loads(raw_args)
                    result = args.get("result", "")
                    log.info("│ %s → done_tool '%s' with result=%s",
                             self.name, name, result[:150])
                    if on_step:
                        on_step(AgentStep(self.name, round_num, "tool_call", f"{name}({result[:100]})"))
                    if on_step:
                        on_step(AgentStep(self.name, round_num, "done", result[:200]))
                    log.info("└─ %s finished (done_tool)", self.name)
                    return result

                if on_step:
                    snippet = raw_args[:200] if name == "bash" else ""
                    label = f"bash: {snippet}..." if snippet else f"{name}(...)"
                    on_step(AgentStep(self.name, round_num, "tool_call", label))

                try:
                    args = json.loads(raw_args)
                except json.JSONDecodeError:
                    log.warning("! JSON decode error for tool '%s': %s", name, raw_args[:100])
                    args = {}

                log.info("│   %s → calling %s(args=%s)", self.name, name, args)
                result = await registry.call(name, args)
                result_str = str(result)
                log.info("│   %s ← %s", self.name, result_str[:250])

                if on_step:
                    trunc = result_str[:200]
                    on_step(AgentStep(self.name, round_num, "tool_result", trunc))

                # _AGENT_DONE_ prefix signals that the tool has completed the
                # agent's task successfully. Any tool can use this to auto-
                # terminate, eliminating an unnecessary LLM round. Example:
                # generate_pdf returns "_AGENT_DONE_: /path/to/file.pdf"
                # on success — the agent exits immediately without LLM
                # needing to call a separate done tool.
                if result_str.startswith("_AGENT_DONE_:"):
                    done_result = result_str.split(":", 1)[1].strip()
                    log.info("│ %s ← _AGENT_DONE_ from tool '%s': %s",
                             self.name, name, done_result[:300])
                    if on_step:
                        on_step(AgentStep(self.name, round_num, "done", done_result[:200]))
                    log.info("└─ %s finished (_AGENT_DONE_)", self.name)
                    return done_result

                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "name": name,
                    "content": result_str,
                })

            if round_num == self.max_rounds and not gave_fallback:
                log.warning("! %s hit max_rounds, injecting fallback prompt", self.name)
                self.messages.append({
                    "role": "user",
                    "content": f"Maximum attempts reached. Call {self.done_tool_name}(result='...') with what you have. Do NOT continue working on the task."
                })
                self.max_rounds += 1
                gave_fallback = True

            round_num += 1

        log.error("! %s exhausted all %d rounds", self.name, self.max_rounds)
        msg = "Error: Max rounds reached without final response."
        if on_step:
            on_step(AgentStep(self.name, self.max_rounds, "error", msg))
        return msg
