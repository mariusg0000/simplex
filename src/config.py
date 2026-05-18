"""
src/config.py · Configuration management using Pydantic Settings · Fills settings from .env file.
"""

import logging
from pathlib import Path
from typing import Optional, Dict
from pydantic import Field, AliasChoices, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import dotenv_values

_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    """
    WHAT:    Configuration settings for Simplex AI.
    WHY:     Centralizes all environment variables and provides type safety.
    HOW:     Uses pydantic-settings to parse .env file with aliases for mixed prefixes.
             Providers are defined in .env as SIMPLEX_PROVIDER_<NAME>_{ALIAS,API_KEY,API_BASE}
             and resolved at runtime via resolve_model().
    """
    # Model selection — use alias/provider format (e.g. "opencode-go/deepseek-v4-flash")
    chat_model: str = Field(
        default="opencode-go/deepseek-v4-flash",
        validation_alias=AliasChoices("simplex_chat_model", "simplex_model", "model")
    )
    vision_model: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("simplex_vision_model")
    )
    vision_max_dimension: int = Field(
        default=2000,
        validation_alias=AliasChoices("simplex_vision_max_dimension", "vision_max_dimension")
    )

    # Legacy single-provider fallback (used when no provider aliases match)
    openai_api_key: Optional[str] = Field(default=None, validation_alias=AliasChoices("simplex_openai_api_key", "openai_api_key"))
    openai_api_base: Optional[str] = Field(default=None, validation_alias=AliasChoices("simplex_openai_api_base", "openai_api_base"))

    tmp_dir: str = Field(
        default="~/.simplexai/tmp",
        validation_alias=AliasChoices("simplex_tmp_dir", "tmp_dir")
    )

    sessions_dir: str = Field(
        default="~/.simplexai/sessions",
        validation_alias=AliasChoices("simplex_sessions_dir", "sessions_dir")
    )

    temperature: float = Field(default=0.7, validation_alias=AliasChoices("simplex_temperature", "temperature"))
    max_tokens: int = Field(default=4096, validation_alias=AliasChoices("simplex_max_tokens", "max_tokens"))

    max_context: int = Field(default=80000, validation_alias=AliasChoices("simplex_max_context", "max_context"))
    min_context: int = Field(default=4000, validation_alias=AliasChoices("simplex_min_context", "min_context"))

    system_prompt: str = Field(
        default="You are Simplex AI, a helpful office assistant.",
        validation_alias=AliasChoices("simplex_system_prompt", "system_prompt")
    )

    native_mode: bool = Field(default=True, validation_alias=AliasChoices("simplex_native_mode", "native_mode"))
    log_level: str = Field(default="INFO", validation_alias=AliasChoices("simplex_log_level", "log_level"))

    # Internal: provider registry populated from .env
    providers: Dict[str, Dict[str, str]] = Field(default_factory=dict, exclude=True)

    model_config = SettingsConfigDict(
        env_file=str(_ENV_PATH),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @model_validator(mode="after")
    def _load_providers(self) -> "Settings":
        env = dotenv_values(str(_ENV_PATH))
        providers: Dict[str, Dict[str, str]] = {}
        for key, value in env.items():
            if not key or not value:
                continue
            if key.startswith("SIMPLEX_PROVIDER_") and key.endswith("_ALIAS"):
                stem = key[len("SIMPLEX_PROVIDER_"):-len("_ALIAS")]
                api_key = env.get(f"SIMPLEX_PROVIDER_{stem}_API_KEY", "")
                api_base = env.get(f"SIMPLEX_PROVIDER_{stem}_API_BASE", "")
                if api_key:
                    providers[value] = {"api_key": api_key, "api_base": api_base}
        self.providers = providers
        return self

    @property
    def model(self) -> str:
        """Backward-compat alias for chat_model."""
        return self.chat_model

    def resolve_model(self, model_str: Optional[str] = None) -> tuple:
        """
        WHAT:    Resolves an 'alias/model' string to (litellm_model, api_key, api_base).
        WHY:     Enables multi-provider support — each provider has its own api_key/base
                 defined in .env. The alias prefix selects which provider to use.
        HOW:     Splits on '/' — first part is the provider alias, rest is the model name.
                 If alias matches a known provider, prepends 'openai/' for LiteLLM routing.
                 Falls back to legacy 'openai_api_key' / 'openai_api_base' when no alias matches.
        PARAMS:  model_str: Optional[str] — model in 'alias/name' format (default: chat_model)
        RETURNS: tuple[str, str, str] — (litellm_model, api_key, api_base)
        """
        model_str = model_str or self.chat_model
        if "/" in model_str:
            alias, rest = model_str.split("/", 1)
            if alias in self.providers:
                p = self.providers[alias]
                return (f"openai/{rest}", p["api_key"], p["api_base"])
        return (model_str, self.openai_api_key, self.openai_api_base)


settings = Settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("simplex")
