# Fix: main agent must pass detailed layout specs when delegating to create_doc

## Subtasks
- Fix 4: agent_description — instructiuni clare ce trebuie pasat
- Fix 5: state.py regula #5 extinsa
- Fix 6: create_doc role_prompt — nu re-analiza
- Commit, push, archive

## Summary
The create_doc agent was wasting tool calls on redundant PDF analysis because the main agent didn't provide enough detail in the task description. Fixed by:

### Changes
1. **src/agents/create_doc.md:4-14** (agent_description): Replaced vague "Provide a detailed description" with explicit checklist of what the main agent MUST include: layout structure, hex colors, fonts (name/size/weight per element), full text verbatim (or file path), visual elements. Added: "It does NOT analyze reference files."

2. **src/ui/state.py:233-236** (strategic guideline #5): Expanded from generic "delegate" instruction to explicit: "For create_doc: first analyze reference documents yourself, then call the agent with ALL layout specs. The sub-agent generates directly from your description — it does NOT re-analyze."

3. **src/agents/create_doc.md:21** (role_prompt): Added at end: "The main agent's task description already contains ALL layout specifications and full text content — generate directly from it without re-analyzing any reference files."

### Key decisions
- Main agent (powerful LLM) does ONE thorough analysis → passes all specs to create_doc
- create_doc just generates HTML+CSS+weasyprint from the provided description
- No redundant analysis at any level
- Main agent can either embed text verbatim or provide a file path for create_doc to read
