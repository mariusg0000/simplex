# Remediation Plan — 2026-05-06

## 1. Security: Add `.env` to `.gitignore`
- `.env` contains API keys and is committed to git
- Add `.env` to `.gitignore`

## 2. Replace print debug with logging
- Add `SIMPLEX_LOG_LEVEL` to `config.py`
- Replace all `print("[DEBUG] ...")` with `logging.debug(...)` in:
  - `src/engine/chat.py` (4 occurrences)
  - `src/engine/file_search.py` (5 occurrences)
  - `src/engine/file_management.py` (1 occurrence)

## 3. Update `specs.md`
- Replace Flet references with NiceGUI
- Document current architecture: `src/engine/`, `src/db.py`, `src/storage.py`
- List implemented features

## 4. Modularize `main.py` → `src/ui/`
- `src/ui/chat_view.py` — chat logic (start_new_chat, refresh_chat_display, load_chat, handle_send, process_response)
- `src/ui/sidebar.py` — sidebar logic (refresh_sidebar, edit/archive/delete)
- `src/ui/settings.py` — settings dialog
- `src/ui/app.py` — init_ui() + layout
- `src/engine/builtin_tools.py` — get_current_time, calculator
- `src/ui/__init__.py` — expose public components
- `main.py` → thin entry point (~15 lines)

## 5. Add tests
- `tests/test_file_management.py` — CRUD + backup rotation
- `tests/test_doc_reader.py` — all formats, edge cases
- `tests/test_db.py` — SQLite session CRUD
- `tests/test_builtin_tools.py` — get_current_time, calculator

## 6. Verify
- Run existing tests
- Lint check

---

## Execution Summary (completed)

| # | Task | Status | Detalii |
|---|------|--------|---------|
| 1 | **Securitate** | ✅ | `.env` adăugat în `.gitignore` |
| 2 | **Logging** | ✅ | `print("[DEBUG]")` → `logging.debug()` în chat.py, file_search.py, file_management.py. Nivel configurable via `SIMPLEX_LOG_LEVEL` |
| 3 | **specs.md** | ✅ | Rescris să reflecte NiceGUI, structura curentă, feature-uri implementate |
| 4 | **Modularizare** | ✅ | `main.py` (378 linii → 14 linii). UI-ul împărțit în 5 fișiere: `state.py`, `chat_view.py`, `sidebar.py`, `settings.py`, `app.py`. Tool-urile inline mutate în `builtin_tools.py` |
| 5 | **Teste** | ✅ | 4 fișiere test → 9 fișiere test. 7 teste → 34 teste (toate trec) |
| 6 | **Verificare** | ✅ | Toate 17 fișiere source compilează fără erori, 34/34 teste trec |

### Structura nouă `src/ui/`
```
src/ui/
├── __init__.py
├── state.py        # Shared state (globals, get_system_prompt, init_messages)
├── chat_view.py    # Chat logic (send, stream, display)
├── sidebar.py      # Session list, rename, archive, delete
├── settings.py     # Settings dialog (dirs, preferences)
└── app.py          # Layout + init_ui()
```
