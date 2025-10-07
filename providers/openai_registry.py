"""Registry loader for OpenAI model capabilities."""

from __future__ import annotations

from .model_registry_base import CapabilityModelRegistry
from .shared import ProviderType


class OpenAIModelRegistry(CapabilityModelRegistry):
    """Capability registry backed by `conf/openai_models.json`."""

    def __init__(self, config_path: str | None = None) -> None:
        super().__init__(
            env_var_name="OPENAI_MODELS_CONFIG_PATH",
            default_filename="openai_models.json",
            provider=ProviderType.OPENAI,
            friendly_prefix="OpenAI ({model})",
            config_path=config_path,
        )
