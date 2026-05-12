# Creating Custom Skills for Simplex AI

Skills are instruction modules that guide the LLM when handling specialized tasks.
When the LLM decides to use a skill, the skill's prompt is injected into the
conversation, providing expert guidance.

## How to Create a Skill

1. Create a `.md` file in `~/.simplexai/skills/`
2. Use the following sections:

```markdown
## enabled
enabled

## skill_description
A clear description of what this skill does. This is shown to the LLM so
it knows when to invoke this skill.

## skill_prompt
The detailed instructions, methodology, and guidelines the LLM should
follow when this skill is activated. Be specific and thorough.
```

## Required Sections

- `## enabled` — set to "enabled" to activate
- `## skill_description` — description for the LLM (used in function schema)
- `## skill_prompt` — the instruction content injected when skill is called

## Example

See the built-in `code_review` skill in `src/skills/code_review.md` for a
complete example.

## Notes

- Skills are loaded at startup. Restart the app to pick up new or modified skills.
- Custom skills override built-in ones with the same filename.
- The LLM decides when to invoke a skill based on the `skill_description`.
