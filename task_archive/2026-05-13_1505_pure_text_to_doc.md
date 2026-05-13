# create_doc becomes pure text-to-document converter

## Changes
- Agent receives only LAYOUT description + TEXT inline. No file paths. No fitz.
- Workflow: write HTML → weasyprint → done (max 3 bash calls)
- Prompt: 615 chars, 15 lines
- state.py rule #5 updated

## Rationale
Fitz and file reading removed entirely. Agent is a pure text-to-document pipeline.
Main agent must provide all layout specs and text inline.
