"""
src/engine/tools.py · Tool System · ToolRegistry with dynamic discovery + @tool decorator.
"""

import asyncio
import importlib.util
import inspect
import logging
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set, get_type_hints, get_origin

log = logging.getLogger("simplex.engine.tools")

BUILTIN_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
CUSTOM_TOOLS_DIR = Path.home() / ".simplexai" / "tools"


def _make_async_wrapper(execute_fn):
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
    Registry for LLM-accessible tools.
    Discovers tool modules from src/tools/ and ~/.simplexai/tools/ automatically.
    Also supports the @tool decorator for backward compatibility.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        self._tools: Dict[str, Callable] = {}
        self.schemas: List[Dict[str, Any]] = []
        self._disabled: Set[str] = set()
        self._discovered = False
        self.on_confirmation_required: Optional[Callable[[str, str, str], Awaitable[bool]]] = None

    def _ensure_discovered(self):
        if self._discovered:
            return
        self._discovered = True
        self._discover(BUILTIN_TOOLS_DIR, "built-in")
        self._discover(CUSTOM_TOOLS_DIR, "custom")

    def _discover(self, directory: Path, source_label: str):
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
                async_wrapper = _make_async_wrapper(module.execute)
                desc = module.get_description()
                desc["name"] = name

                if name in self._tools:
                    self.schemas[:] = [s for s in self.schemas if s["function"]["name"] != name]

                self._tools[name] = async_wrapper
                self.schemas.append({"type": "function", "function": desc})
                log.info(f"Loaded tool '{name}' from {source_label}")
            except Exception as e:
                log.error(f"Failed to load tool {filepath.name}: {e}")

    def register(self, func: Callable) -> Callable:
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

    async def call(self, name: str, arguments: Dict[str, Any]) -> str:
        self._ensure_discovered()
        if name not in self._tools:
            return f"Error: Tool '{name}' not found."

        func = self._tools[name]
        try:
            if inspect.iscoroutinefunction(func):
                return await func(**arguments)
            return func(**arguments)
        except Exception as e:
            return f"Error executing tool '{name}': {str(e)}"


registry = ToolRegistry()


def tool(func: Callable) -> Callable:
    return registry.register(func)
