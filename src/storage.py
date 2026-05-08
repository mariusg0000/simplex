"""
src/storage.py · User preferences storage · Manages persistent UI settings in a JSON file.
"""

import json
from pathlib import Path
from typing import List
from pydantic import BaseModel, Field


class UserPreferences(BaseModel):
    """
    WHAT:    Model for persistent user UI preferences.
    WHY:     Provides type safety and easy serialization for local settings.
    HOW:     Stored as a JSON file in the project root.
    """
    show_reasoning: bool = Field(default=False)
    dark_mode: bool = Field(default=False)
    working_directories: List[str] = Field(default_factory=list)
    font_size: int = Field(default=4)
    line_spacing: int = Field(default=2)


class StorageManager:
    """
    WHAT:    Handles reading and writing UserPreferences to disk.
    WHY:     Decouples UI logic from file I/O.
    HOW:     Uses a fixed file path 'user_settings.json'.
    """
    def __init__(self, filename: str = "user_settings.json"):
        self.file_path = Path.home() / ".simplexai" / filename
        self.prefs = self.load()

    def load(self) -> UserPreferences:
        """Loads preferences from JSON or returns defaults if file missing/invalid."""
        if not self.file_path.exists():
            return UserPreferences()
        
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return UserPreferences(**data)
        except (json.JSONDecodeError, KeyError, Exception):
            return UserPreferences()

    def save(self) -> None:
        """Writes current preferences to disk."""
        with open(self.file_path, "w", encoding="utf-8") as f:
            f.write(self.prefs.model_dump_json(indent=2))

    def update_preference(self, key: str, value: any) -> None:
        """Updates a specific preference and saves immediately."""
        if hasattr(self.prefs, key):
            setattr(self.prefs, key, value)
            self.save()


# Global storage instance
storage = StorageManager()
