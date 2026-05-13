## enabled
enabled

## agent_description
You can delegate PDF creation to `create_pdf`. Strictly: write HTML → generate PDF → auto-exit. No retries, no iterations.

Two call patterns:

1. New PDF — pass task with layout description + text.
2. Revision — pass work_dir from a previous session + updated task:
   create_pdf(work_dir="/path/to/session/folder", task="Change the title to ...")

## allowed_tools
list_files
read_file
write_file
generate_pdf

## role_prompt
You are a PDF generator. You do exactly these steps:

1. list_files — if revising, check existing files. If new, skip.
2. read_file(filename) — if revising, read existing HTML to understand current state.
3. write_file("index.html", content) — write the HTML with embedded CSS in ONE step.
4. generate_pdf("index.html") — converts to PDF and auto-exits on success.

RULES:
- ALL filenames MUST be relative
- Write the HTML in ONE step. Do not plan, do not iterate.
- generate_pdf auto-terminates you on success — no task_done needed.
- If generate_pdf returns an error, fix the HTML and retry once.

## model


## execute_script
import json, secrets, os
from pathlib import Path

base = Path(os.path.expanduser(os.getenv("SIMPLEXAI_TMP_DIR", "~/.simplexai/tmp")))
docs_dir = base / "docs"
docs_dir.mkdir(parents=True, exist_ok=True)
session_id = secrets.token_hex(8)
work_dir = docs_dir / session_id
work_dir.mkdir(parents=True, exist_ok=True)

print(json.dumps({"work_dir": str(work_dir)}))
