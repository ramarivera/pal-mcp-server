"""Registry for models exposed via custom (local) OpenAI-compatible endpoints."""

from __future__ import annotations

from .model_registry_base import CAPABILITY_FIELD_NAMES, CapabilityModelRegistry
from .shared import ModelCapabilities, ProviderType


class CustomEndpointModelRegistry(CapabilityModelRegistry):
    def __init__(self, config_path: str | None = None) -> None:
        super().__init__(
            env_var_name="CUSTOM_MODELS_CONFIG_PATH",
            default_filename="custom_models.json",
            provider=ProviderType.CUSTOM,
            friendly_prefix="Custom ({model})",
            config_path=config_path,
        )
        self.reload()

    def _finalise_entry(self, entry: dict) -> tuple[ModelCapabilities, dict]:
        entry["provider"] = ProviderType.CUSTOM
        entry.setdefault("friendly_name", f"Custom ({entry['model_name']})")
        filtered = {k: v for k, v in entry.items() if k in CAPABILITY_FIELD_NAMES}
        filtered.setdefault("provider", ProviderType.CUSTOM)
        capability = ModelCapabilities(**filtered)
        return capability, {}
