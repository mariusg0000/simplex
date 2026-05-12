# Custom Agents — ~/.simplexai/agents/

Agents are declarative Markdown files. Each `.md` file must have these sections:

## `## enabled`
`enabled` or `disabled`

## `## agent_description`
One-liner describing what the agent does. Shown to the main LLM.

## `## allowed_tools`
One tool name per line from the available tool pool (e.g. `bash`, `read_document`, `generate_pdf`, `task_done`, `write_html`, `read_file`).

## `## role_prompt`
The system prompt for the sub-agent. Be detailed — this is the agent's personality and workflow.

## `## execute_script` (optional)
A Python script that runs before the agent starts. Must print valid JSON to stdout. The JSON keys become agent parameters accessible to tools via `_agent_params`:

```python
import json, secrets
print(json.dumps({
    "key1": "value1",
    "key2": "value2",
}))
```

## `## done_tool` (optional)
Which tool signals agent completion. Default is `task_done`. Set to a custom tool name (e.g. `pdf_done`) for agents with a dedicated termination tool.

## Example (`my_agent.md`)

```markdown
## enabled
enabled

## agent_description
Handles data analysis tasks using bash.

## allowed_tools
bash
task_done

## role_prompt
You are a data analyst. Use bash to explore and process data.
When finished, call task_done(result='...').
```

The agent name = filename (without `.md`). Overrides of built-in agents are supported.

## Auto-terminare (_AGENT_DONE_)

Orice tool poate întrerupe automat agentul părinte returnând un string
care începe cu prefixul `_AGENT_DONE_:`. Când bucla agentului detectează
acest prefix după un apel de tool, iese imediat (fără un nou LLM call)
și returnează restul stringului ca rezultat final al agentului.

Exemplu — un tool care returnează:
    _AGENT_DONE_: /path/to/fisier.pdf

→ Agentul se termină automat cu rezultatul "/path/to/fisier.pdf".

Atenție: Dacă un tool declară în descrierea sa că auto-termină agentul
(ex: `generate_pdf`), agentul NU trebuie să mai sune `task_done()` sau
un alt tool de finalizare după acesta.
