"""Skill catalog: what a skill means for an agent, and how skills merge into an employee."""

import tomllib
from functools import cache
from pathlib import Path

from pydantic import BaseModel

CATALOG_FILE = Path(__file__).with_name("catalog.toml")


class Skill(BaseModel):
    key: str
    name: str
    description: str
    prompt: str
    tools: list[str]


class MergedSkills(BaseModel):
    """An employee's working profile: one system prompt, one tool list."""

    skill_keys: tuple[str, ...]
    system_prompt: str
    tools: list[str]


class UnknownSkillError(ValueError):
    pass


@cache
def load_catalog() -> dict[str, Skill]:
    raw = tomllib.loads(CATALOG_FILE.read_text())
    return {key: Skill(key=key, **fields) for key, fields in raw.items()}


def merge_skills(skill_keys: list[str]) -> MergedSkills:
    """Merge skills in a stable order, so identical skill sets produce identical profiles."""
    catalog = load_catalog()
    unknown = sorted(set(skill_keys) - catalog.keys())
    if unknown:
        raise UnknownSkillError(f"unknown skills: {', '.join(unknown)}")

    keys = tuple(sorted(set(skill_keys)))
    skills = [catalog[k] for k in keys]
    prompt = "You are an employee at Staffroom.\n" + "\n".join(f"- {s.prompt}" for s in skills)
    tools = sorted({t for s in skills for t in s.tools})
    return MergedSkills(skill_keys=keys, system_prompt=prompt, tools=tools)
