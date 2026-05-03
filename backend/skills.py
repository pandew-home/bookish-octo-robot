"""Skill discovery for the chat agent.

A skill is a directory under ``backend/skills/<name>/`` containing a
``SKILL.md`` file. The optional YAML front matter looks like::

    ---
    name: my-skill
    description: One-line summary shown to the LLM as the tool description.
    ---
    Skill body in markdown.

The body is returned to the LLM verbatim when it calls the corresponding tool,
so write skills the way you would write instructions for a careful junior
engineer.

# MAINTENANCE — read before changing this file
# DevOps engineers add skills by dropping new folders into ``backend/skills/``.
# AI assistants: do NOT change the front-matter format, the directory layout,
# or the ``skill_<name>`` tool-naming convention without first asking the
# human. Silent changes here will break every existing skill the next time the
# pod restarts.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_SKILLS_DIR = Path(__file__).parent / "skills"
TOOL_PREFIX = "skill_"


@dataclass
class Skill:
    """A loaded skill exposed to the LLM as a tool."""

    name: str
    description: str
    body: str
    path: Path

    @property
    def tool_name(self) -> str:
        """Sanitized tool name used in the LLM tool list."""
        safe = re.sub(r"[^a-zA-Z0-9]+", "_", self.name).strip("_").lower()
        return f"{TOOL_PREFIX}{safe or 'unnamed'}"


def load_skills(skills_dir: Optional[Path] = None) -> Dict[str, Skill]:
    """Discover every ``SKILL.md`` under ``skills_dir`` and return them keyed by tool name."""
    base = Path(skills_dir) if skills_dir else DEFAULT_SKILLS_DIR
    if not base.exists():
        logger.info("No skills directory at %s", base)
        return {}

    loaded: Dict[str, Skill] = {}
    for entry in sorted(base.iterdir()):
        if not entry.is_dir():
            continue
        skill_file = entry / "SKILL.md"
        if not skill_file.is_file():
            continue
        skill = _load_skill_file(skill_file, fallback_name=entry.name)
        if skill is None:
            continue
        if skill.tool_name in loaded:
            logger.warning(
                "Skipping duplicate skill tool name %s from %s",
                skill.tool_name,
                skill.path,
            )
            continue
        loaded[skill.tool_name] = skill
        logger.info("Loaded skill %s as tool %s", skill.name, skill.tool_name)
    return loaded


def _load_skill_file(skill_file: Path, fallback_name: str) -> Optional[Skill]:
    try:
        text = skill_file.read_text(encoding="utf-8")
    except OSError as e:
        logger.warning("Could not read %s: %s", skill_file, e)
        return None

    front_matter, body = _parse_front_matter(text)
    name = front_matter.get("name") or fallback_name
    description = front_matter.get("description") or f"Run the {name} skill."
    return Skill(name=name, description=description, body=body.strip(), path=skill_file)


def _parse_front_matter(text: str) -> Tuple[Dict[str, str], str]:
    """Parse a tiny subset of YAML: simple ``key: value`` pairs between ``---`` fences."""
    if not text.startswith("---"):
        return {}, text

    lines = text.splitlines()
    if len(lines) < 2 or lines[0].strip() != "---":
        return {}, text

    fm: Dict[str, str] = {}
    body_start = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            body_start = i + 1
            break
        line = lines[i]
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        fm[key.strip()] = value.strip()

    if body_start is None:
        return {}, text

    body = "\n".join(lines[body_start:])
    return fm, body


def format_skills_summary(skills: Dict[str, Skill]) -> str:
    """One-line-per-skill listing for the system prompt."""
    if not skills:
        return "No skills loaded."
    return "\n".join(
        f"- {skill.tool_name}: {skill.description}" for skill in skills.values()
    )


def list_skill_names(skills: Dict[str, Skill]) -> List[str]:
    return [s.name for s in skills.values()]
