"""
tests/test_db.py · Unit tests for chat database · Verifies CRUD operations.
"""

import json
import pytest
from src.db import ChatDatabase, init_db


@pytest.fixture
def db(tmp_path, monkeypatch):
    """Creates a test database using a temporary file."""
    db_path = tmp_path / "test_chats.db"
    monkeypatch.setattr("src.db.DB_PATH", str(db_path))
    init_db()
    return ChatDatabase()


def test_save_and_get_session(db):
    """Happy path: save a session and retrieve it."""
    session_id = "test-123"
    title = "Test Chat"
    messages = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi there"}
    ]

    db.save_session(session_id, title, messages)
    session = db.get_session(session_id)

    assert session is not None
    assert session["title"] == title
    assert session["id"] == session_id

    # System messages should be filtered out
    stored_msgs = session["messages"]
    roles = [m["role"] for m in stored_msgs]
    assert "system" not in roles


def test_save_filters_system_messages(db):
    """System messages are not persisted."""
    session_id = "test-sys"
    messages = [
        {"role": "system", "content": "You are a bot"},
        {"role": "user", "content": "hello"}
    ]

    db.save_session(session_id, "Test", messages)
    session = db.get_session(session_id)

    stored = session["messages"]
    assert len(stored) == 1
    assert stored[0]["role"] == "user"


def test_list_sessions(db):
    """List returns sessions sorted by update time."""
    db.save_session("a", "First", [{"role": "user", "content": "a"}])
    db.save_session("b", "Second", [{"role": "user", "content": "b"}])

    sessions = db.list_sessions()
    assert len(sessions) == 2
    # Most recently updated should be first
    assert sessions[0]["id"] == "b"


def test_delete_session(db):
    """Delete removes the session."""
    db.save_session("del-me", "Delete", [{"role": "user", "content": "x"}])
    db.delete_session("del-me")
    assert db.get_session("del-me") is None


def test_update_title(db):
    """Update title changes the session title."""
    db.save_session("t1", "Old Title", [{"role": "user", "content": "x"}])
    db.update_title("t1", "New Title")

    session = db.get_session("t1")
    assert session["title"] == "New Title"


def test_get_nonexistent(db):
    """Non-existent session returns None."""
    assert db.get_session("does-not-exist") is None
