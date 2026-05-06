"""
tests/test_file_search.py · Unit tests for intelligent file search · Verifies logic and tracking.
"""

import os
import json
from pathlib import Path
from src.engine.file_search import intelligent_file_search, SearchTracker, TRACKING_FILE

def test_file_search_logic(tmp_path):
    """Verifies that the search finds a file and records a hit."""
    # Create a dummy structure
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    test_file = work_dir / "invoice_test_123.pdf"
    test_file.write_text("dummy")
    
    # Use a custom tracking file for testing
    test_tracking = tmp_path / "test_tracking.json"
    tracker = SearchTracker(str(test_tracking))
    
    # Run search
    # We mock the global tracker for this test to avoid polluting real data
    import src.engine.file_search
    original_tracker = src.engine.file_search.tracker
    src.engine.file_search.tracker = tracker
    
    try:
        result = intelligent_file_search("invoice_test_*.pdf", ["finance", "test"], suggested_dir=str(work_dir))
        assert "invoice_test_123.pdf" in result
        
        # Verify tracking
        tracker = SearchTracker(str(test_tracking)) # Reload
        assert len(tracker.data) == 1
        assert tracker.data[0]["hit_count"] == 1
        assert "finance" in tracker.data[0]["keywords"]
    finally:
        src.engine.file_search.tracker = original_tracker

def test_upward_search(tmp_path):
    """Verifies that the search can find a file in a parent directory."""
    parent = tmp_path / "parent"
    parent.mkdir()
    child = parent / "child"
    child.mkdir()
    
    target_file = parent / "target_up.txt"
    target_file.write_text("found me")
    
    # Mock tracker to avoid side effects
    import src.engine.file_search
    original_tracker = src.engine.file_search.tracker
    src.engine.file_search.tracker = SearchTracker(str(tmp_path / "dummy_track.json"))
    
    try:
        # Search starting from child, file is in parent
        result = intelligent_file_search("target_up.txt", ["test"], suggested_dir=str(child))
        assert "target_up.txt" in result
    finally:
        src.engine.file_search.tracker = original_tracker
