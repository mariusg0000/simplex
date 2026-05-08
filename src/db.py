"""
src/db.py · Database Layer · Handles SQLite persistence for chat sessions.
"""

import sqlite3
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

DB_PATH = str(Path.home() / ".simplexai" / "chats.db")

def init_db():
    """Initializes the database schema if it doesn't exist."""
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
        """
        # Filter out system messages
        chat_history = [m for m in messages if m.get("role") != "system"]
        
        if not chat_history:
            return

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
        """Deletes a session from the database."""
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
