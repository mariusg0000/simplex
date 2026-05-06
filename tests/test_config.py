"""
tests/test_config.py · Unit tests for configuration · Verifies Pydantic settings loading.
"""

from src.config import Settings

def test_settings_load():
    """
    WHAT:    Tests if settings are loaded from .env or defaults.
    WHY:     Ensures the configuration layer is working before the app starts.
    HOW:     Instantiates Settings and checks for presence of key fields.
    """
    settings = Settings()
    assert settings.model is not None
    assert isinstance(settings.temperature, float)
    assert settings.system_prompt.startswith("You are")
