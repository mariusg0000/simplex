# Simplex AI - Project Specifications (V1)

## 1. General Vision
Simplex AI is an assistant-type AI agent, optimized for office work environments (corporate/administrative). Although its "brain" is completely separate, it is distributed with a simple and friendly graphical interface, hiding technical complexity from the end user.

## 2. Core Architecture
*   **Paradigm:** Developed from scratch, total control over the agent loop.
*   **LLM Backend:** Agnostic, using the `litellm` library with `acompletion(stream=True)` for async streaming. Allows easy switching between models (OpenAI, Anthropic, Gemini, Ollama for local execution).
*   **Async-Native:** The entire stack is async — NiceGUI runs on an async event loop, LLM calls are non-blocking, and streaming responses update the UI chunk-by-chunk in-place.
*   **Configuration:** `pydantic-settings` via `.env` file (model, API keys, temperature, max_tokens, system prompt, log level).
*   **Logging:** Structured logging via Python `logging` module with configurable level (`SIMPLEX_LOG_LEVEL`).
*   **Python Ecosystem:** 
    *   Language: Python 3.11+
    *   Package Manager: `uv` (for speed and efficient environment management).

## 3. Project Structure

```
Simplex/
├── main.py                 # Thin entry point: init_ui() + ui.run()
├── src/
│   ├── config.py           # Pydantic-settings from .env + logging setup
│   ├── db.py               # SQLite persistence for chat sessions
│   ├── storage.py          # JSON user preferences (working dirs, UI toggles)
│   ├── engine/
│   │   ├── chat.py         # LLM streaming loop + multi-turn tool execution
│   │   ├── tools.py        # Tool registry with decorator pattern
│   │   ├── agents.py       # Sub-agent base class + RerankerAgent
│   │   ├── file_search.py  # Focused file search with Reranker sub-agent
│   │   ├── doc_reader.py   # Document reader (PDF, DOCX, XLSX, TXT, MD)
│   │   └── file_management.py  # CRUD file ops + rolling backups (~/.backups/)
│   ├── ui/                 # UI components (modularized from main.py)
│   └── utils/              # Utility functions
└── tests/                  # Pytest test suite
```

## 4. Extensibility System
*   **Sub-agents:** Delegation system to specialized agents with their own prompts and tools.
    *   *Architecture:* Isolated LLM calls with specific system prompts for internal tasks (e.g., reranking, analysis).
    *   *Integration:* Used within native tools to process high-volume data before returning to the main agent.
    *   *Implemented:* `RerankerAgent` — ranks file search results by relevance.
*   **Tools (Native tools):** Python functions decorated with `@tool` to be exposed to the LLM.
    *   *Auto schema generation:* Parameters parsed via `inspect.signature` + type hints.
    *   *Implemented tools:* `file_search`, `list_directory`, `read_document_content`, `read_file`, `write_file`, `append_to_file`, `patch_file`, `delete_file`, `get_current_time`, `calculator`.
*   **MCP Integration (Model Context Protocol):** [PLANNED] Integrated client to connect to MCP servers for standardized access to file system, databases, external applications.

## 5. User Interface (UI)
*   **Framework:** `NiceGUI` (High-level UI components based on Vue and Quasar, written entirely in Python).
*   **Architecture:**
    *   Entry: `ui.run()` — NiceGUI auto-detects and runs the async event loop.
    *   Native desktop mode via NiceGUI's native wrapper (WebView/Qt).
    *   UI components: Modularized into `src/ui/` (chat_view, sidebar, settings, app).
*   **Streaming:** Assistant messages stream token-by-token into a `ui.markdown` widget. Each chunk from `litellm.acompletion(stream=True)` appends to the bubble content and triggers a UI update.
*   **Experience:** Chat style (bubble messages), clean, intuitive for non-technical users. User bubbles right-aligned, assistant left-aligned.
*   **Reasoning visibility:** Optional toggle to show AI "thinking" process before the final answer.
*   **NiceGUI Advantages:** 
    *   Native Tailwind CSS support for easy and modern styling.
    *   Standard Web technologies (HTML/JS/CSS) under the hood, but 100% Python development.
    *   Extremely flexible layout system.

## 6. Key Features (Implemented)

### File System & Search
*   **Focused File Search:** Strictly searches within user-defined working directories.
*   **Smart Reranking:** `RerankerAgent` identifies the most relevant files based on chat context and modification time.
*   **Directory Listing:** Browse folder contents with security checks (restricted to working directories).
*   **Search Tracker:** Learning database that remembers which folders contain relevant files.

### Document Reader
*   **Multi-Format Support:** Text extraction from `.pdf`, `.docx`, `.xlsx`/`.xls`, and plain text (`.txt`, `.md`, `.py`, `.json`, `.yaml`/`.yml`).
*   **Safety limit:** 10,000 characters max to avoid context overflow.

### File Management
*   **CRUD Operations:** read, write, append, patch (surgical text replacement), delete.
*   **Rolling Backups:** Automatic before every write/patch/delete. Stored in `~/.backups/` with 3 rotating versions (`.v1` newest, `.v3` oldest).
*   **Security:** All file operations restricted to configured working directories.

### Chat Persistence
*   **SQLite Storage:** Sessions saved to `chats.db` with title, messages (JSON), and timestamp.
*   **Sidebar Management:** Browse, load, rename, archive, and delete past conversations.
*   **Dynamic System Prompt:** System prompt injected at load time, not stored — allows prompt evolution.

### User Preferences
*   **Persistent Settings:** Working directories, show reasoning toggle saved to `user_settings.json`.
*   **Type-safe:** Backed by Pydantic `UserPreferences` model.

## 7. Planned Features (Roadmap)
- [ ] Phase 5: Security & Packaging
  - [ ] Add support for local models (Ollama)
  - [ ] Build process for .exe/binary
  - [ ] Implement MCP Client for standardized tool access
  - [ ] Implement 'Data Analysis' tool (Pandas for XLSX/CSV)
- [ ] Phase 3 Extension: MCP integration
- [ ] Data Analysis: Advanced Pandas sub-agent for complex Excel queries
- [ ] Email Integration: Outlook/Gmail drafter tools
- [ ] Confidential Mode: One-click toggle for local-only execution via Ollama

## 8. Security & Privacy
*   **Working Directory Sandbox:** All file operations and searches are restricted to user-configured directories.
*   **Backup System:** Rolling backups provide safety net for any destructive operations.
*   **Confidential Mode:** [PLANNED] Local execution via Ollama for sensitive documents.
*   **Data Redaction:** [PLANNED] Intermediary tool for anonymizing names/contact details before external API calls.
