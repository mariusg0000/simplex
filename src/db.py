"""
src/db.py · Database Layer · Handles SQLite persistence for chat sessions.
"""

import shutil
import sqlite3
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

DB_DIR = Path.home() / ".simplexai" / "db"
DB_PATH = str(DB_DIR / "chats.db")

def init_db():
    """Initializes the database schema if it doesn't exist."""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                title TEXT,
                messages TEXT,
                updated_at DATETIME
            )
        """)
        conn.commit()

class ChatDatabase:
    """
    WHAT:    Manages chat history persistence.
    WHY:     Allows users to resume past conversations.
    HOW:     Stores messages as JSON in SQLite, excluding system prompts for dynamic injection.
    """
    def __init__(self):
        init_db()

    def save_session(self, session_id: str, title: str, messages: List[Dict[str, Any]]):
        """
        Saves or updates a chat session.
        Filters out system messages to allow for dynamic prompt updates.
        Strips reasoning_content from all messages before saving.
        """
        # Filter out system messages
        chat_history = [m for m in messages if m.get("role") != "system"]

        if not chat_history:
            return

        # Strip reasoning_content to save space (shown only in Activity Log, never persisted)
        for m in chat_history:
            m.pop("reasoning_content", None)

        json_messages = json.dumps(chat_history)
        updated_at = datetime.now().isoformat()

        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""
                INSERT INTO sessions (id, title, messages, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title = excluded.title,
                    messages = excluded.messages,
                    updated_at = excluded.updated_at
            """, (session_id, title, json_messages, updated_at))
            conn.commit()

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a specific session by ID."""
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
            row = cur.fetchone()
            if row:
                return {
                    "id": row["id"],
                    "title": row["title"],
                    "messages": json.loads(row["messages"]),
                    "updated_at": row["updated_at"]
                }
        return None

    def list_sessions(self) -> List[Dict[str, Any]]:
        """Lists all sessions sorted by last update (newest first)."""
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute("SELECT id, title, updated_at FROM sessions ORDER BY updated_at DESC")
            return [dict(row) for row in cur.fetchall()]

    def delete_session(self, session_id: str):
        """Deletes a session from the database and removes its filesystem folder."""
        from src.config import settings
        session_path = Path(settings.sessions_dir).expanduser() / session_id
        if session_path.exists():
            shutil.rmtree(session_path, ignore_errors=True)
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            conn.commit()

    def update_title(self, session_id: str, new_title: str):
        """Updates the title of a specific session."""
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("UPDATE sessions SET title = ? WHERE id = ?", (new_title, session_id))
            conn.commit()

# Global database instance
db = ChatDatabase()
