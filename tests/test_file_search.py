"""
tests/test_file_search.py · Unit tests for file search · Verifies logic and tracking.
"""

import json
from pathlib import Path
from src.engine.file_search import SearchTracker


def test_tracker_record_and_rank(tmp_path):
    """Verifies that the tracker records hits and ranks by keyword match + hit count."""
    test_tracking = tmp_path / "test_tracking.json"
    tracker = SearchTracker(str(test_tracking))

    tracker.record_hit("/tmp/test/work", ["invoice", "finance"])
    tracker.record_hit("/tmp/test/work", ["invoice", "2024"])
    tracker.record_hit("/tmp/test/docs", ["report", "annual"])

    assert len(tracker.data) == 2
    assert tracker.data[0]["hit_count"] == 2

    ranked = tracker.get_ranked_locations(["invoice"])
    assert len(ranked) >= 1
    assert "/tmp/test/work" in ranked


def test_tracker_empty(tmp_path):
    """Verifies empty tracker behavior."""
    test_tracking = tmp_path / "empty_track.json"
    tracker = SearchTracker(str(test_tracking))
    assert tracker.data == []
    assert tracker.get_ranked_locations(["nothing"]) == []
