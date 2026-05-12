"""
src/engine/skills.py · Skill System · SkillRegistry for .md skill modules.
"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set

log = logging.getLogger("simplex.engine.skills")

SKILLS_BUILTIN_DIR = Path(__file__).resolve().parent.parent / "skills"
SKILLS_CUSTOM_DIR = Path.home() / ".simplexai" / "skills"


@dataclass
class SkillDef:
    name: str
    enabled: bool
    description: str
    skill_prompt: str


def _parse_skill_md(content: str) -> dict:
    sections = {}
    pattern = r'^##\s+(\S+)\s*$'
    lines = content.split('\n')
    current_section = None
    current_lines = []

    for line in lines:
        m = re.match(pattern, line.strip())
        if m:
            if current_section:
                sections[current_section] = '\n'.join(current_lines).strip()
            current_section = m.group(1).lower()
            current_lines = []
        else:
            current_lines.append(line)

    if current_section:
        sections[current_section] = '\n'.join(current_lines).strip()

    return sections


class SkillRegistry:
    """
    Registry for LLM-accessible skills.
    Discovers skill modules from src/skills/ and ~/.simplexai/skills/ automatically.
    Skills are .md files with ## section headers.
    """

    def __init__(self):
        self._skills: Dict[str, SkillDef] = {}
        self._disabled: Set[str] = set()
        self._discover(SKILLS_BUILTIN_DIR, "built-in")
        self._discover(SKILLS_CUSTOM_DIR, "custom")

    def _discover(self, directory: Path, source_label: str):
        if not directory.exists():
            return
        for filepath in sorted(directory.iterdir()):
            if filepath.suffix != ".md" or filepath.name.lower() == "readme.md":
                continue
            try:
                content = filepath.read_text(encoding="utf-8")
                sections = _parse_skill_md(content)

                required = {"enabled", "skill_description", "skill_prompt"}
                missing = required - set(sections.keys())
                if missing:
                    log.warning(
                        f"Skill {filepath.name} missing sections: {missing} — skipped"
                    )
                    continue

                name = filepath.stem
                enabled = sections["enabled"].strip().lower() == "enabled"
                description = sections["skill_description"].strip()
                skill_prompt = sections["skill_prompt"].strip()

                skill_def = SkillDef(
                    name=name,
                    enabled=enabled,
                    description=description,
                    skill_prompt=skill_prompt,
                )

                self._skills[name] = skill_def
                log.info("Loaded skill '%s' from %s", name, source_label)
            except Exception as e:
                log.error(f"Failed to load skill {filepath.name}: {e}")

    def get_schemas(self) -> List[Dict]:
        schemas = []
        for name, skill in self._skills.items():
            if skill.enabled and name not in self._disabled:
                schemas.append({
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": skill.description,
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "task": {
                                    "type": "string",
                                    "description": f"Task for the {name} skill. Describe what you need in detail."
                                }
                            },
                            "required": ["task"],
                        },
                    },
                })
        return schemas

    async def call(self, name: str, arguments: dict) -> str:
        skill = self._skills.get(name)
        if not skill:
            return f"Error: Skill '{name}' not found."
        if not skill.enabled:
            return f"Error: Skill '{name}' is disabled."

        log.info("→ skill call: %s", name)
        return skill.skill_prompt

    def disable(self, name: str):
        self._disabled.add(name)

    def enable(self, name: str):
        self._disabled.discard(name)

    def is_disabled(self, name: str) -> bool:
        return name in self._disabled

    def __contains__(self, name: str) -> bool:
        return name in self._skills


skill_registry = SkillRegistry()
