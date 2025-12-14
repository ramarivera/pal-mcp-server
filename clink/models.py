"""Pydantic models for clink configuration and runtime structures."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, PositiveInt, field_validator


class OutputCaptureConfig(BaseModel):
    """Optional configuration for CLIs that write output to disk."""

    flag_template: str = Field(..., description="Template used to inject the output path, e.g. '--output {path}'.")
    cleanup: bool = Field(
        default=True,
        description="Whether the temporary file should be removed after reading.",
    )


class CLIRoleConfig(BaseModel):
    """Role-specific configuration loaded from JSON manifests."""

    prompt_path: str | None = Field(
        default=None,
        description="Path to the prompt file that seeds this role.",
    )
    role_args: list[str] = Field(default_factory=list)
    description: str | None = Field(default=None)

    @field_validator("role_args", mode="before")
    @classmethod
    def _ensure_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        if isinstance(value, str):
            return [value]
        raise TypeError("role_args must be a list of strings or a single string")


class CLIClientConfig(BaseModel):
    """Raw CLI client configuration before internal defaults are applied.

    For custom CLIs (not in INTERNAL_DEFAULTS), the following fields are required:
      - name: Unique identifier for the CLI
      - command: The executable command to run
      - parser: Parser spec (e.g., 'builtin:gemini_json' or 'path/to/parser.py:MyParser')

    Optional fields for custom CLIs:
      - internal_args: Args added by the system (like --output json)
      - default_role_prompt: Path to default prompt file
      - runner: Agent spec (defaults to BaseCLIAgent if not specified)
    """

    name: str
    command: str | None = None
    working_dir: str | None = None
    additional_args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: PositiveInt | None = Field(default=None)
    roles: dict[str, CLIRoleConfig] = Field(default_factory=dict)
    output_to_file: OutputCaptureConfig | None = None

    # New fields for custom CLI support (config-only, no code changes needed)
    parser: str | None = Field(
        default=None,
        description="Parser spec: 'builtin:<name>' or 'path/to/module.py:ClassName'",
    )
    internal_args: list[str] = Field(
        default_factory=list,
        description="Internal args appended by system (e.g., --output json)",
    )
    default_role_prompt: str | None = Field(
        default=None,
        description="Default prompt path for roles without explicit prompt_path",
    )
    runner: str | None = Field(
        default=None,
        description="Agent spec: 'builtin:<name>', 'path:ClassName', or null for BaseCLIAgent",
    )

    @field_validator("additional_args", mode="before")
    @classmethod
    def _ensure_args_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        if isinstance(value, str):
            return [value]
        raise TypeError("additional_args must be a list of strings or a single string")

    @field_validator("internal_args", mode="before")
    @classmethod
    def _ensure_internal_args_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        if isinstance(value, str):
            return [value]
        raise TypeError("internal_args must be a list of strings or a single string")


class ResolvedCLIRole(BaseModel):
    """Runtime representation of a CLI role with resolved prompt path."""

    name: str
    prompt_path: Path
    role_args: list[str] = Field(default_factory=list)
    description: str | None = None


class ResolvedCLIClient(BaseModel):
    """Runtime configuration after merging defaults and validating paths.

    The `parser` and `runner` fields store spec strings that can be resolved
    at runtime using the loader module. This allows custom parsers/agents
    to be loaded from user-provided Python files.
    """

    model_config = {"arbitrary_types_allowed": True}

    name: str
    executable: list[str]
    working_dir: Path | None
    internal_args: list[str] = Field(default_factory=list)
    config_args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: int
    parser: str  # Parser spec string (builtin or path)
    runner: str | None = None  # Agent spec string (builtin, path, or None for BaseCLIAgent)
    roles: dict[str, ResolvedCLIRole]
    output_to_file: OutputCaptureConfig | None = None

    # Internal field for resolving relative paths in custom parser/agent specs
    config_source_path: Path | None = Field(
        default=None,
        description="Path to the config file that defined this client (for relative path resolution)",
    )

    def list_roles(self) -> list[str]:
        return list(self.roles.keys())

    def get_role(self, role_name: str | None) -> ResolvedCLIRole:
        key = role_name or "default"
        if key not in self.roles:
            available = ", ".join(sorted(self.roles.keys()))
            raise KeyError(f"Role '{role_name}' not configured for CLI '{self.name}'. Available roles: {available}")
        return self.roles[key]

    @property
    def config_base_dir(self) -> Path | None:
        """Get the base directory for resolving relative paths in parser/agent specs."""
        if self.config_source_path:
            return self.config_source_path.parent
        return None
