"""
src/engine/tools.py · ToolRegistry singleton + _agent_params injection.
Discovers tool modules dynamically (built-in and custom), manages visibility
scopes, injects sub-agent context via ContextVar. Depends on: importlib, inspect.
"""

import asyncio
import importlib.util
import inspect
import logging
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set, get_type_hints, get_origin

log = logging.getLogger("simplex.engine.tools")

agent_params_ctx: ContextVar[Optional[dict]] = ContextVar("agent_params", default=None)
"""
ContextVar carrying the active sub-agent's parameters (work_dir, etc.).
Set by AgentRegistry.call() before running a sub-agent; read by ToolRegistry.call()
to inject _agent_params into tool executors that accept it (e.g. bash, task_done).
"""

BUILTIN_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
CUSTOM_TOOLS_DIR = Path.home() / ".simplexai" / "tools"


def _make_async_wrapper(execute_fn: Callable) -> Callable:
    """
    WHAT:    Wraps a sync or async execute() function into a standardised async callable.
    WHY:     ToolRegistry stores a uniform async interface; raw modules may have
             sync or async execute(). This wrapper normalises both to async → str.
    HOW:     Calls the original function, awaits if it returns a coroutine, wraps
             the result in str(). Preserves __name__ and __qualname__ for logging.
    PARAMS:  execute_fn: Callable — the module's execute() function
    RETURNS: Callable — async wrapper with signature **kwargs → str
    """
    async def wrapper(**kwargs):
        result = execute_fn(**kwargs)
        if asyncio.iscoroutine(result):
            result = await result
        return str(result)
    wrapper.__name__ = getattr(execute_fn, "__name__", "execute")
    wrapper.__qualname__ = getattr(execute_fn, "__qualname__", "execute")
    return wrapper


class ToolRegistry:
    """
    WHAT:    Singleton registry that discovers, registers, and invokes LLM-accessible tools.
    WHY:     Centralises tool lifecycle: filesystem discovery (src/tools/, ~/.simplexai/tools/),
             schema generation for the LLM, visibility filtering (main-agent vs sub-agent),
             and _agent_params injection for sandbox enforcement.
    HOW:     On first access, scans tool directories for .py modules with get_description()
             and execute() exports. Each tool is wrapped in an async callable and registered
             with its OpenAI function schema. The @tool decorator provides runtime registration
             as an alternative. call() handles _agent_params injection from the ContextVar.
    """

    _instance = None

    def __new__(cls) -> "ToolRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """
        INIT:   _tools — dict[name → async_callable]
                _tool_executors — dict[name → raw module.execute] (for sig inspection)
                schemas — list of OpenAI function schemas
                _tool_visibility — dict[name → {"main_agent": bool}]
                _disabled — set of tool names disabled at runtime
                _discovered — one-shot flag (avoids re-scanning filesystem)
                on_confirmation_required — UI hook for destructive command approval
        """
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        self._tools: Dict[str, Callable] = {}
        self._tool_executors: Dict[str, Callable] = {}
        self.schemas: List[Dict[str, Any]] = []
        self._tool_visibility: Dict[str, dict] = {}
        self._disabled: Set[str] = set()
        self._discovered = False
        self.on_confirmation_required: Optional[Callable[[str, str, str], Awaitable[bool]]] = None

    def _ensure_discovered(self) -> None:
        """
        WHAT:    One-shot lazy trigger for filesystem discovery.
        WHY:     Discovery runs on first tool access (not on __init__) so that
                 config and directories are ready. Subsequent calls are no-ops.
        """
        if self._discovered:
            return
        self._discovered = True
        self._discover(BUILTIN_TOOLS_DIR, "built-in")
        self._discover(CUSTOM_TOOLS_DIR, "custom")

    def _discover(self, directory: Path, source_label: str) -> None:
        """
        WHAT:    Scans a directory for .py tool modules and registers valid ones.
        WHY:     Plugin system — drop a .py file with get_description() + execute()
                 and the tool is immediately available. Custom tools in
                 ~/.simplexai/tools/ override built-ins with the same name.
        HOW:     Dynamically imports each .py via importlib. Validates required exports
                 (get_description, execute). Reads optional get_visibility() for
                 main-agent filtering. Duplicate names replace the existing schema.
        PARAMS:  directory: Path — folder to scan
                 source_label: str — "built-in" or "custom" (for logging)
        """
        if not directory.exists():
            return
        for filepath in sorted(directory.iterdir()):
            if filepath.suffix != ".py" or filepath.name == "__init__.py":
                continue
            try:
                spec = importlib.util.spec_from_file_location(
                    f"tool_{filepath.stem}", filepath
                )
                if not spec or not spec.loader:
                    continue
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                if not hasattr(module, "get_description") or not hasattr(module, "execute"):
                    log.warning(
                        f"Tool {filepath.name} missing get_description() or execute() — skipped"
                    )
                    continue

                name = filepath.stem
                if hasattr(module, "get_visibility"):
                    self._tool_visibility[name] = module.get_visibility()
                else:
                    self._tool_visibility[name] = {"main_agent": True}

                async_wrapper = _make_async_wrapper(module.execute)
                desc = module.get_description()
                desc["name"] = name

                if name in self._tools:
                    self.schemas[:] = [s for s in self.schemas if s["function"]["name"] != name]

                self._tools[name] = async_wrapper
                self._tool_executors[name] = module.execute
                self.schemas.append({"type": "function", "function": desc})
                log.info(f"Loaded tool '{name}' from {source_label}")
            except Exception as e:
                log.error(f"Failed to load tool {filepath.name}: {e}")

    def register(self, func: Callable) -> Callable:
        """
        WHAT:    Registers a function as a tool at runtime (alternative to filesystem discovery).
        WHY:     Backward-compatible @tool decorator support. Allows lightweight tools
                 defined inline without a separate .py file on disk.
        HOW:     Infers the OpenAI schema from the function's signature and docstring:
                 parameter types → JSON types, default-less params → required.
                 If a tool with the same name already exists, it's NOT replaced
                 (filesystem discovery has priority).
        PARAMS:  func: Callable — the tool function (sync or async)
        RETURNS: Callable — the same func, unchanged
        """
        self._ensure_discovered()
        name = func.__name__
        if name in self._tools:
            return func

        doc = func.__doc__ or f"Tool for {name}"

        sig = inspect.signature(func)
        type_hints = get_type_hints(func)

        properties = {}
        required = []

        doc_lines = doc.split("\n")
        param_docs = {}
        for line in doc_lines:
            if ":" in line and any(p in line for p in sig.parameters):
                parts = line.split(":", 1)
                p_name = parts[0].strip().split()[-1]
                if p_name in sig.parameters:
                    param_docs[p_name] = parts[1].strip()

        for param_name, param in sig.parameters.items():
            param_type = type_hints.get(param_name, str)
            origin = get_origin(param_type) or param_type

            json_type = "string"
            if origin == int: json_type = "integer"
            elif origin == float: json_type = "number"
            elif origin == bool: json_type = "boolean"
            elif origin in (list, List): json_type = "array"
            elif origin in (dict, Dict): json_type = "object"

            p_desc = param_docs.get(param_name, f"The {param_name} to use for {name}")
            properties[param_name] = {
                "type": json_type,
                "description": p_desc
            }

            if json_type == "array":
                properties[param_name]["items"] = {"type": "string"}

            if param.default is inspect.Parameter.empty:
                required.append(param_name)

        schema = {
            "type": "function",
            "function": {
                "name": name,
                "description": doc.strip().split('\n')[0],
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }

        self._tools[name] = func
        self.schemas.append(schema)
        return func

    def disable(self, name: str) -> None:
        self._ensure_discovered()
        self._disabled.add(name)

    def enable(self, name: str) -> None:
        self._ensure_discovered()
        self._disabled.discard(name)

    def is_disabled(self, name: str) -> bool:
        self._ensure_discovered()
        return name in self._disabled

    def __contains__(self, name: str) -> bool:
        self._ensure_discovered()
        return name in self._tools

    def get_schemas(self) -> List[Dict[str, Any]]:
        self._ensure_discovered()
        return [s for s in self.schemas if s["function"]["name"] not in self._disabled]

    def get_main_agent_schemas(self) -> List[Dict[str, Any]]:
        """
        WHAT:    Returns schemas for tools visible to the main agent.
        WHY:     Sub-agent-only tools (e.g. task_done, generate_pdf) must be hidden
                 from the main agent's LLM to prevent incorrect invocations.
        HOW:     Filters self.schemas by _tool_visibility: tools with
                 get_visibility() returning {"main_agent": False} are excluded.
        PARAMS:  none (uses self.schemas, self._tool_visibility, self._disabled)
        RETURNS: list[dict] — filtered OpenAI tool schemas
        """
        self._ensure_discovered()
        main_tools = {name for name, vis in self._tool_visibility.items()
                      if vis.get("main_agent", True)}
        return [s for s in self.schemas
                if s["function"]["name"] not in self._disabled
                and s["function"]["name"] in main_tools]

    def get_main_agent_text_descriptions(self) -> str:
        """
        WHAT:    Returns compact text descriptions of all visible tools for
                 inclusion in the system prompt when using XML text-based tooling.
        WHY:     When function-calling is disabled, the LLM needs tool descriptions
                 in the system prompt to know which tools exist and how to use them.
        HOW:     Converts each tool schema into a compact text format:
                 • tool_name(param1, param2) — description
                   param1: param description
                   param2: param description
        PARAMS:  none
        RETURNS: str — plain-text tool descriptions for system prompt
        """
        self._ensure_discovered()
        schemas = self.get_main_agent_schemas()
        if not schemas:
            return ""

        lines = [
            "## AVAILABLE TOOLS",
            "",
            "Call tools with XML blocks:",
            "<tool_name>",
            "  <param_name>value</param_name>",
            "</tool_name>",
            "",
            "Tools:",
        ]
        for s in schemas:
            fn = s["function"]
            name = fn["name"]
            desc = fn.get("description", "").strip()
            params = fn.get("parameters", {}).get("properties", {})
            required = set(fn.get("parameters", {}).get("required", []))

            if params:
                lines.append(f"• {name} — {desc}")
                for pname, pinfo in params.items():
                    req = " (required)" if pname in required else ""
                    pdesc = pinfo.get("description", "")
                    lines.append(f"  <{pname}>{req} — {pdesc}")
            else:
                lines.append(f"• {name} — {desc}")

        lines.append("")
        lines.append("IMPORTANT: Return ONLY ONE tool block per response.")
        lines.append("Output the XML block without surrounding explanation or markdown fences.")
        return "\n".join(lines)

    async def call(self, name: str, arguments: Dict[str, Any]) -> str:
        """
        WHAT:    Invokes a registered tool by name with the given arguments.
        WHY:     Entry point for both main-agent and sub-agent tool execution.
                 Handles _agent_params injection (sub-agent sandbox context)
                 and normalises sync/async execution behind a uniform awaitable.
        HOW:     1. Looks up the tool by name; returns error if not found.
                 2. Reads agent_params_ctx; if present and the tool's raw execute()
                    accepts _agent_params, injects it into arguments.
                 3. Calls the registered async wrapper (sync → str normalised).
                 4. Catches all exceptions and returns them as error strings
                    (tools never raise — they always return strings).
        PARAMS:  name: str — tool name (filename stem or @tool function name)
                 arguments: Dict[str, Any] — keyword arguments for the tool
        RETURNS: str — tool output (file content, command result, or error message)
        ERRORS:  Tool not found → "Error: Tool '...' not found."
                 Execution exception → "Error executing tool '...': {details}"
        """
        self._ensure_discovered()
        if name not in self._tools:
            return f"Error: Tool '{name}' not found."

        agent_params = agent_params_ctx.get()
        if agent_params is not None and name in self._tool_executors:
            sig = inspect.signature(self._tool_executors[name])
            if '_agent_params' in sig.parameters:
                log.info("→ injecting _agent_params into tool '%s'", name)
                arguments = {**arguments, '_agent_params': agent_params}

        func = self._tools[name]
        log.info("→ tool call: %s(%s)", name, arguments)
        try:
            if inspect.iscoroutinefunction(func):
                result = await func(**arguments)
            else:
                result = func(**arguments)
            log.info("← tool result: %s[:200] = %s", name, str(result)[:200])
            return result
        except Exception as e:
            log.error("! tool error: %s - %s", name, e)
            return f"Error executing tool '{name}': {str(e)}"


registry = ToolRegistry()


def tool(func: Callable) -> Callable:
    """
    WHAT:    Decorator that registers a function as a tool at runtime.
    WHY:     Provides an inline alternative to filesystem-based tool discovery
             for simple tools defined within the codebase.
    PARAMS:  func: Callable — the tool function
    RETURNS: Callable — the same func (registry stores a copy)
    """
    return registry.register(func)
