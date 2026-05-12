# Custom Tools — ~/.simplexai/tools/

Tools are auto-discovered Python modules. Each `.py` file must implement:

## `get_description() -> dict`
Returns a JSON schema for the LLM describing the tool and its parameters.

## `execute(**kwargs) -> str`
The actual implementation. Receives the arguments the LLM chose based on the schema.

## Agent Parameters (`_agent_params`)

When a tool runs inside an agent, it can optionally receive agent-level bootstrap parameters. If your `execute()` function has an `_agent_params: dict = None` parameter, the framework will inject the agent's parameters automatically. Use this for fallback values:

```python
async def execute(path: str = None, _agent_params: dict = None) -> str:
    if _agent_params and not path:
        path = _agent_params.get("html_path")
    ...
```

## Example (`my_tool.py`)

```python
def get_description() -> dict:
    return {
        "description": "Briefly what this tool does.",
        "parameters": {
            "type": "object",
            "properties": {
                "param1": {"type": "string", "description": "What param1 is for"},
            },
            "required": ["param1"],
        },
    }

async def execute(param1: str) -> str:
    return f"Hello, {param1}!"
```

The tool name = filename (without `.py`). Overrides of built-in tools are supported — your custom file replaces the built-in one with the same name.

## Auto-terminare agent (_AGENT_DONE_)

Orice tool poate semnala buclei agentului că sarcina acestuia s-a încheiat,
întrerupându-l imediat fără un tur LLM suplimentar. Pentru asta,
funcția `execute()` trebuie să returneze un string de forma:

    _AGENT_DONE_: <rezultatul final>

Exemplu — un tool de procesare care, după ce termină, auto-termină agentul:

```python
async def execute(input_path: str) -> str:
    ok, msg = proceseaza_fisier(input_path)
    if not ok:
        return f"ERROR: {msg}"
    return f"_AGENT_DONE_: {input_path}.output"
```

Când să folosești:
- Când tool-ul însuși reprezintă ultimul pas din workflow-ul agentului.
- Când vrei să economisești un LLM call (agentul nu mai trebuie să sune
  `task_done()` după tool).

Când să NU folosești:
- Când tool-ul poate eșua, iar agentul trebuie să poată reîncerca.
  În caz de eroare, returnează un mesaj de eroare simplu (fără prefix),
  iar agentul va vedea eroarea și va decide ce să facă.
