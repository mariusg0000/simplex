"""
tests/test_storage.py · Unit tests for storage manager · Verifies JSON saving/loading.
"""

import os
from src.storage import StorageManager, UserPreferences

def test_storage_save_load():
    """
    WHAT:    Tests if preferences are correctly saved and loaded from JSON.
    WHY:     Ensures user settings are persistent.
    HOW:     Creates a temporary storage file, updates a value, and reloads it.
    """
    test_file = "test_settings.json"
    if os.path.exists(test_file):
        os.remove(test_file)
        
    manager = StorageManager(test_file)
    manager.update_preference("show_reasoning", True)
    
    # New manager instance to force reload from disk
    new_manager = StorageManager(test_file)
    assert new_manager.prefs.show_reasoning is True
    
    # Cleanup
    if os.path.exists(test_file):
        os.remove(test_file)
