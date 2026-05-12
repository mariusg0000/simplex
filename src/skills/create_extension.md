## enabled
enabled

## skill_description
Use this skill when the user asks you to create a new tool, skill, or sub-agent for the Simplex AI system. This skill teaches you the exact file format and conventions for each extension type.

## skill_prompt
You are now in EXTENSION CREATION mode. You can create new tools, skills, or sub-agents. Below are the complete specifications for each type.

### GENERAL RULES

- Write files using `bash` heredoc: `cat > /path/to/file << 'EOF' ... EOF`
- All output paths are absolute, under `~/.simplexai/`
- Extensions are loaded at app startup — the user must restart after creation
- Filenames: only lowercase letters, numbers, and underscores. Python files use snake_case.
- Custom files override built-in files with the same name
- After writing, tell the user what you created and remind them to restart

---

### TYPE 1: TOOLS

**Where:** `~/.simplexai/tools/<name>.py`

**What:** A Python module that the LLM can call to perform an action. The tool name is the filename without `.py`.

**Required exports — two functions:**

**Function 1: `get_description()`** — Returns a Python dict that is the JSON schema describing the tool. The dict must have keys: `"description"` (a string explaining what the tool does and when to use it), and `"parameters"` (a JSON Schema object with `"type": "object"`, `"properties"` mapping each parameter name to its `{"type": "...", "description": "..."}`, and `"required"` listing mandatory parameter names).

**Function 2: `execute()`** — The actual implementation. Can be sync or async. Receives keyword arguments matching the parameters defined in get_description. Returns a string result.

**Optional: `_agent_params`** — If the execute function has a parameter `_agent_params: dict = None`, the framework will automatically inject agent bootstrap parameters when the tool runs inside an agent. Use this for fallback values.

**Optional: `get_visibility()`** — Control where the tool is available:
- Return `{"main_agent": False}` if the tool should ONLY be usable inside sub-agents
- Return `{"main_agent": True}` (or omit the function entirely) if the main agent can also use it
- Example: A PDF-conversion helper tool should set `main_agent: False`

**Optional: auto-termination** — Return a string starting with `_AGENT_DONE_:` to immediately end the agent loop without an extra LLM round. Only use this when the tool is the final step of the agent's workflow. If the tool can fail and need retries, return a plain error string instead.

**Concrete example of a tool file (use this structure):**

The file looks like this (I'll describe it in prose since the markdown parser can't show raw section headers):

First, import any needed modules (os, pathlib, json, etc). Then define get_description() returning a dict with "description" and "parameters" as described above. Optionally define get_visibility() to restrict the tool to sub-agents only. Then define execute() — can be async or sync — taking the parameters you declared plus optionally _agent_params. Inside execute, implement the logic in a try/except, returning a success message or an error string.

A minimal tool for greeting someone would have:
- get_description returns `{"description": "Greets a person by name.", "parameters": {"type": "object", "properties": {"name": {"type": "string", "description": "The name to greet"}}, "required": ["name"]}}`
- async execute(name) returns `f"Hello, {name}!"`
- (get_visibility() and _agent_params are optional — omit them for tools usable everywhere)

---

### TYPE 2: SKILLS

**Where:** `~/.simplexai/skills/<name>.md`

**What:** A markdown file that provides specialized instructions. When the LLM invokes a skill, the skill's prompt content is injected into the conversation to guide the LLM.

**Section headers:** All section headers in a skill `.md` file use the double-hash format (two hash characters followed by a space and the section name). Do NOT use single hash.

**Required sections:**

1. A section called **enabled** — content must be the word "enabled" (or "disabled" to deactivate).

2. A section called **skill_description** — content is a one-line description telling the LLM when to invoke this skill. This appears in the function schema.

3. A section called **skill_prompt** — content is the full instructional text that gets injected when the skill is called. Write detailed methodology and guidelines here. IMPORTANT: inside this section, never put double-hash at the start of a line. Use triple-hash for sub-headings (which is safe), or just use bold text with `**`.

**Concrete example** — a skill file for greeting would contain three sections:

- The enabled section, containing just the word "enabled"
- The skill_description section, containing: "Use this skill when someone needs to be greeted."
- The skill_prompt section, containing: "You are in GREETING mode. Always be warm and friendly. Ask how their day is going."

---

### TYPE 3: AGENTS

**Where:** `~/.simplexai/agents/<name>.md`

**What:** A markdown file defining an autonomous sub-agent that runs in its own tool loop. The agent name is the filename without `.md`.

**Section headers:** All section headers in an agent `.md` file use the double-hash format. Do NOT use single hash.

**Required sections:**

1. **enabled** — content must be "enabled" or "disabled".

2. **agent_description** — content is a one-liner describing what the agent does. This is shown to the main LLM so it knows when to delegate to this agent.

3. **allowed_tools** — content lists one tool name per line. The agent can ONLY call these tools. Common tools: `bash`, `read_file`, `read_document`, `write_html`, `generate_pdf`, `task_done`. Check what tools exist before listing them.

4. **role_prompt** — content is the full system prompt for the sub-agent. This defines the agent's personality, responsibilities, and exact workflow step by step. Be very detailed. Include what to do on errors, when to retry, and how to signal completion.

**Optional sections:**

5. **model** (optional) — content specifies which LLM model this agent uses. Format: `provider/model-name` (examples: `openai/gpt-4o`, `anthropic/claude-sonnet-4-20250514`). If this section is missing or empty, the agent uses the default system model.

6. **execute_script** (optional) — content is a Python script that runs before the agent starts. It must print valid JSON to stdout. The JSON keys become agent parameters accessible to tools via `_agent_params`. Example script:

```python
import json, secrets, os
from pathlib import Path
d = Path(os.path.expanduser("~/.simplexai/tmp/agent"))
d.mkdir(parents=True, exist_ok=True)
print(json.dumps({"work_dir": str(d), "id": secrets.token_hex(4)}))
```

7. **done_tool** (optional) — content is the name of the tool that signals the agent is finished. Default is `task_done`. Set this only if the agent uses a custom completion tool.

**Auto-termination:** Any tool used by the agent can end the agent immediately by returning a string starting with `_AGENT_DONE_:`. The agent loop exits without an extra LLM round, and the rest of the string becomes the agent's final result.

**Concrete example** — an agent file for data analysis would contain:

- The enabled section, containing "enabled"
- The agent_description section, containing: "Handles data analysis tasks. Use when the user asks to analyze CSV, JSON, or log files."
- The allowed_tools section, listing `bash` on one line and `task_done` on the next
- The role_prompt section, containing detailed instructions: "You are a data analyst. Use bash to explore and process data files. When the user provides a file path, first inspect it with head/file/wc, then run the appropriate analysis. When finished, call task_done with a result string summarizing your findings."
- Optionally, a model section containing `openai/gpt-4o`

---

### CHECKLIST

1. Decide which type (tool, skill, or agent) fits the user's need
2. Ask the user for the name and any specifics
3. Write the file using `bash` to the correct directory under `~/.simplexai/`
4. Remind the user to **restart the app** to activate the new extension
