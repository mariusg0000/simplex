"""
src/engine/tools.py · Tool System · Provides decorators and registry for LLM tools.
"""

import inspect
import functools
from typing import Any, Callable, Dict, List, Optional, get_type_hints, get_origin


class ToolRegistry:
    """
    WHAT:    Registry for LLM-accessible tools.
    WHY:     Centralizes tool management and schema generation.
    HOW:     Stores functions and generates OpenAI tool definitions.
    """
    def __init__(self):
        self.tools: Dict[str, Callable] = {}
        self.schemas: List[Dict[str, Any]] = []

    def register(self, func: Callable) -> Callable:
        """Registers a function as a tool."""
        name = func.__name__
        
        # Prevent duplicate registrations
        if name in self.tools:
            return func

        doc = func.__doc__ or "No description provided."
        
        # Parse parameters using inspection
        sig = inspect.signature(func)
        type_hints = get_type_hints(func)
        
        properties = {}
        required = []
        
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
            
            properties[param_name] = {
                "type": json_type,
                "description": f"Parameter {param_name}"
            }
            
            if json_type == "array":
                properties[param_name]["items"] = {"type": "string"}
            
            if param.default is inspect.Parameter.empty:
                required.append(param_name)
        
        schema = {
            "type": "function",
            "function": {
                "name": name,
                "description": doc.split('\n')[0], # Use first line of docstring
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

    def get_schemas(self) -> List[Dict[str, Any]]:
        """Returns schemas for all registered tools."""
        return self.schemas

    async def call(self, name: str, arguments: Dict[str, Any]) -> Any:
        """Executes a registered tool by name with provided arguments."""
        if name not in self.tools:
            return f"Error: Tool '{name}' not found."
        
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
