"""
src/config.py · Configuration management using Pydantic Settings · Fills settings from .env file.
"""

from typing import Optional
from pydantic import Field, AliasChoices
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    WHAT:    Configuration settings for Simplex AI.
    WHY:     Centralizes all environment variables and provides type safety.
    HOW:     Uses pydantic-settings to parse .env file with aliases for mixed prefixes.
    """
    model: str = Field(default="openai/deepseek-v4-flash", validation_alias=AliasChoices("simplex_model", "model"))
    openai_api_key: Optional[str] = Field(default=None, validation_alias=AliasChoices("simplex_openai_api_key", "openai_api_key"))
    openai_api_base: Optional[str] = Field(default=None, validation_alias=AliasChoices("simplex_openai_api_base", "openai_api_base"))
    
    temperature: float = Field(default=0.7, validation_alias=AliasChoices("simplex_temperature", "temperature"))
    max_tokens: int = Field(default=4096, validation_alias=AliasChoices("simplex_max_tokens", "max_tokens"))
    system_prompt: str = Field(
        default="You are Simplex AI, a helpful office assistant.",
        validation_alias=AliasChoices("simplex_system_prompt", "system_prompt")
    )
    
    native_mode: bool = Field(default=True, validation_alias=AliasChoices("simplex_native_mode", "native_mode"))

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
