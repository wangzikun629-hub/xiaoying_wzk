"""Validated project YAML; executable objects always come from the tool registry."""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .schemas import digest
from .tools import PROJECT_ROOT


class SubagentConfigError(ValueError):
    """Invalid local subagent configuration, before any model or tool call."""


class SubagentSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    name: str = Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")
    role: Literal["writer", "reviewer"]
    enabled: bool = True
    description: str = Field(min_length=1)
    system_prompt: str = Field(min_length=1)
    tools: list[str]

    @model_validator(mode="after")
    def check_permissions(self):
        if self.name == "general-purpose":
            raise ValueError("general-purpose is reserved")
        if not self.description.strip() or not self.system_prompt.strip():
            raise ValueError("description and system_prompt must not be blank")
        expected = ["generate_script"] if self.role == "writer" else []
        if self.tools != expected:
            raise ValueError("writer requires generate_script only; reviewer has no tools")
        return self


class SubagentFile(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    subagents: list[SubagentSpec]

    @model_validator(mode="after")
    def check_unique(self):
        names = [s.name for s in self.subagents]
        roles = [s.role for s in self.subagents if s.enabled]
        if len(names) != len(set(names)) or len(roles) != len(set(roles)):
            raise ValueError("subagent names and enabled roles must be unique")
        return self


def load_subagents(path: Path | None = None) -> list[SubagentSpec]:
    path = path if path is not None else PROJECT_ROOT / "config/subagents.yaml"
    try:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        config = SubagentFile.model_validate(data)
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        # Do not echo arbitrary configuration values into public error messages.
        raise SubagentConfigError("config/subagents.yaml 配置无效，请检查字段、角色及工具权限") from exc
    return [spec for spec in config.subagents if spec.enabled]


def review_fingerprint(engine):
    quote = engine.state["quotes"].get(engine.state.get("active_quote"))
    return digest(dict(plan=quote["plan"] if quote else None, results=engine.state["results"]))


def has_current_review(engine):
    fingerprint = review_fingerprint(engine)
    return any(
        item["role"] == "reviewer"
        and item["status"] == "succeeded"
        and item.get("fingerprint") == fingerprint
        for item in engine.state.get("subagent_runs", [])
    )
