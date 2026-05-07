"""
src/engine/tools.py · Tool System · Provides decorators and registry for LLM tools.
"""

import inspect
import functools
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set, get_type_hints, get_origin


class ToolRegistry:
    """
    WHAT:    Registry for LLM-accessible tools.
    WHY:     Centralizes tool management and schema generation.
    HOW:     Stores functions and generates OpenAI tool definitions.
    """
    def __init__(self):
        self.tools: Dict[str, Callable] = {}
        self.schemas: List[Dict[str, Any]] = []
        self.disabled_tools: Set[str] = set()

        # Event-driven confirmation callback (set by UI layer)
        self.on_confirmation_required: Optional[Callable[[str, str, str], Awaitable[bool]]] = None

    def register(self, func: Callable) -> Callable:
        """Registers a function as a tool."""
        name = func.__name__
        
        # Prevent duplicate registrations
        if name in self.tools:
            return func

        doc = func.__doc__ or f"Tool for {name}"
        
        # Parse parameters using inspection
        sig = inspect.signature(func)
        type_hints = get_type_hints(func)
        
        properties = {}
        required = []
        
        # Simple docstring parser for parameters
        doc_lines = doc.split("\n")
        param_docs = {}
        for line in doc_lines:
            if ":" in line and any(p in line for p in sig.parameters):
                parts = line.split(":", 1)
                p_name = parts[0].strip().split()[-1] # Usually the last word before :
                if p_name in sig.parameters:
                    param_docs[p_name] = parts[1].strip()

        for param_name, param in sig.parameters.items():
            param_type = type_hints.get(param_name, str)
            origin = get_origin(param_type) or param_type
            
            # Map Python types to JSON schema types
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
        
        self.tools[name] = func
        self.schemas.append(schema)
        return func

    def disable(self, name: str) -> None:
        """Disable a tool so it won't be exposed to the LLM or callable."""
        self.disabled_tools.add(name)

    def enable(self, name: str) -> None:
        """Re-enable a previously disabled tool."""
        self.disabled_tools.discard(name)

    def is_disabled(self, name: str) -> bool:
        """Check if a tool is disabled."""
        return name in self.disabled_tools

    def get_schemas(self) -> List[Dict[str, Any]]:
        """Returns schemas for all registered tools (excluding disabled ones)."""
        return [s for s in self.schemas if s["function"]["name"] not in self.disabled_tools]

    async def call(self, name: str, arguments: Dict[str, Any]) -> Any:
        """Executes a registered tool by name with provided arguments."""
        if name not in self.tools:
            return f"Error: Tool '{name}' not found."
        
        if name in self.disabled_tools:
            return f"Error: Tool '{name}' is disabled."
        
        func = self.tools[name]
        try:
            if inspect.iscoroutinefunction(func):
                return await func(**arguments)
            return func(**arguments)
        except Exception as e:
            return f"Error executing tool '{name}': {str(e)}"


# Global registry instance
registry = ToolRegistry()

def tool(func: Callable) -> Callable:
    """Decorator to register a function as a tool."""
    return registry.register(func)
