"""Registry loader for X.AI (GROK) model capabilities."""

from __future__ import annotations

from .model_registry_base import CapabilityModelRegistry
from .shared import ProviderType


class XAIModelRegistry(CapabilityModelRegistry):
    """Capability registry backed by `conf/xai_models.json`."""

    def __init__(self, config_path: str | None = None) -> None:
        super().__init__(
            env_var_name="XAI_MODELS_CONFIG_PATH",
            default_filename="xai_models.json",
            provider=ProviderType.XAI,
            friendly_prefix="X.AI ({model})",
            config_path=config_path,
        )
