"""
src/ui/chat_view.py · Chat logic · Message handling, streaming response display.
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path
from nicegui import ui
from src.ui import state
from src.ui.sidebar import refresh_sidebar
from src.db import db
from src.config import settings
from src.engine.chat import stream_chat
from src.engine.tools import registry
from src.engine.agents import activity_callback, agent_stream_callback
from src.engine.context import compress_messages


def _debug(msg: str):
    line = f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [CHAT_VIEW_DEBUG] {msg}"
    print(line, file=sys.stderr, flush=True)
    try:
        with open("/tmp/simplex_debug.log", "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


async def start_new_chat():
    """Resets the UI and state for a fresh conversation."""
    if state.active_task and not state.active_task.done():
        state.active_task.cancel()

    state.current_session_id = str(__import__("uuid").uuid4())
    session_path = Path(settings.sessions_dir).expanduser() / state.current_session_id
    session_path.mkdir(parents=True, exist_ok=True)
    state.session_folder = str(session_path)
    state.chat_title = "New Chat"
    state.init_messages()
    state.chat_content.clear()
    if state.usage_label:
        state.usage_label.set_text("Context: 0k - 0.0% | Cost: $0.000")
    refresh_sidebar()


async def refresh_chat_display():
    """Re-renders all messages based on current state and preferences."""
    state.chat_content.clear()
    with state.chat_content:
        dialogue = state.messages[1:] if state.messages and state.messages[0]["role"] == "system" else state.messages

        last_assistant_tool_calls: list[dict] | None = None
        for msg in dialogue:
            if msg["role"] == "user":
                with ui.element("div").classes("terminal-user-block"):
                    ui.label("▸ You:").classes("terminal-user-prefix")
                    ui.markdown(msg["content"]).classes("terminal-content")

            elif msg["role"] == "assistant":
                last_assistant_tool_calls = msg.get("tool_calls")
                content = msg.get("content")

                if content:
                    ui.markdown(content).classes("terminal-content")

            elif msg["role"] == "tool":
                cmd_snippet = ""
                if last_assistant_tool_calls:
                    for tc in last_assistant_tool_calls:
                        if tc.get("function", {}).get("name") == "bash":
                            try:
                                import json
                                args = json.loads(tc["function"].get("arguments", "{}"))
                                cmd = args.get("command", "")
                                cmd_snippet = cmd[:50] + ("..." if len(cmd) > 50 else "")
                            except (json.JSONDecodeError, KeyError, TypeError):
                                pass
                label = f"▸ tool: {msg.get('name', 'unknown')}"
                if cmd_snippet:
                    label += f" — {cmd_snippet}"
                ui.label(label).classes("terminal-tool")

    await asyncio.sleep(0.1)
    state.scroll_area.scroll_to(percent=1.0, duration=0.2)


async def load_chat(session_id: str):
    """Loads a previous session from the database."""
    if state.active_task and not state.active_task.done():
        state.active_task.cancel()

    session = db.get_session(session_id)
    if not session:
        return

    state.current_session_id = session_id
    session_path = Path(settings.sessions_dir).expanduser() / session_id
    session_path.mkdir(parents=True, exist_ok=True)
    state.session_folder = str(session_path)
    state.chat_title = session["title"]
    state.messages = [state.get_system_prompt()] + session["messages"]
    await refresh_chat_display()


async def handle_send():
    """Handles user input and starts LLM processing."""
    user_input = state.message_input.value
    if not user_input.strip():
        return

    if state.active_task and not state.active_task.done():
        state.active_task.cancel()
        try:
            await state.active_task
        except asyncio.CancelledError:
            pass

    if not state.current_session_id:
        state.current_session_id = str(__import__("uuid").uuid4())
        session_path = Path(settings.sessions_dir).expanduser() / state.current_session_id
        session_path.mkdir(parents=True, exist_ok=True)
        state.session_folder = str(session_path)

    if state.chat_title == "New Chat":
        state.chat_title = user_input[:40] + ("..." if len(user_input) > 40 else "")

    state.message_input.value = ""
    with state.chat_content:
        with ui.element("div").classes("terminal-user-block"):
            ui.label("▸ You:").classes("terminal-user-prefix")
            ui.markdown(user_input).classes("terminal-content")

    state.messages.append({"role": "user", "content": user_input})
    db.save_session(state.current_session_id, state.chat_title, state.messages)
    refresh_sidebar()

    with state.chat_content:
        thinking_container = ui.row().classes("items-center gap-2 text-gray-400 italic")
        with thinking_container:
            ui.spinner(size="sm")
            ui.label("Thinking...")

    state.scroll_area.scroll_to(percent=1.0, duration=0.2)
    _debug(f"Created _process_response task. messages count before stream: {len(state.messages)}")
    step_cb, stream_cb = state.make_sub_agent_callback()
    state.active_task = asyncio.create_task(_process_response(
        thinking_indicator=thinking_container,
        sub_agent_callback=step_cb,
        sub_agent_stream_callback=stream_cb,
    ))


_confirm_dialog = None
_confirm_title = None
_confirm_explanation = None
_confirm_danger = None
_confirm_command = None
_confirm_future = None


def setup_confirmation_dialog():
    """Pre-creates the confirmation dialog in the correct NiceGUI context.
    Must be called from init_ui() during page construction."""
    global _confirm_dialog, _confirm_title, _confirm_explanation
    global _confirm_danger, _confirm_command

    def _confirm():
        if _confirm_future and not _confirm_future.done():
            _confirm_future.set_result(True)
        _confirm_dialog.close()

    def _deny():
        if _confirm_future and not _confirm_future.done():
            _confirm_future.set_result(False)
        _confirm_dialog.close()

    with ui.dialog() as _confirm_dialog, ui.card().classes("w-96 p-4"):
        _confirm_title = ui.label("⚠️ Confirmare comandă").classes("text-lg font-bold mb-2")
        _confirm_explanation = ui.label("").classes("text-sm mb-2")
        _confirm_danger = ui.label("").classes("text-xs text-red-600 mb-2")
        _confirm_command = ui.label("").classes(
            "text-[10px] text-gray-400 font-mono bg-gray-100 p-2 rounded mb-4 break-all"
        )

        with ui.row().classes("w-full gap-2 justify-end"):
            ui.button("Nu", on_click=_deny)
            ui.button("✅ Da", on_click=_confirm).props("autofocus color=primary")


async def _show_confirmation_dialog(command: str, explanation: str, danger: str) -> bool:
    """Updates the pre-created dialog content, opens it, and returns user choice."""
    global _confirm_future
    loop = asyncio.get_event_loop()
    _confirm_future = loop.create_future()

    _confirm_explanation.set_text(explanation)

    if danger:
        _confirm_danger.set_text(f"Motiv: {danger}")
        _confirm_danger.set_visibility(True)
    else:
        _confirm_danger.set_visibility(False)

    _confirm_command.set_text(f"Comanda: {command[:200]}")
    _confirm_dialog.open()
    return await _confirm_future


async def _process_response(thinking_indicator: ui.element, sub_agent_callback=None, sub_agent_stream_callback=None):
    """Streams the LLM response and saves to database at the end."""
    _debug("=== _process_response STARTED ===")
    if sub_agent_callback:
        activity_callback.set(sub_agent_callback)
    if sub_agent_stream_callback:
        agent_stream_callback.set(sub_agent_stream_callback)
    state.status_label.set_text("Connecting...")
    try:
        total_response = ""
        total_reasoning = ""

        response_container = None
        _reasoning_active = False

        async for chunk in stream_chat(state.messages):
            if chunk["type"] == "status":
                state.status_label.set_text(chunk["content"])

            elif chunk["type"] == "usage":
                ctx = chunk.get("context_tokens", 0) / 1000
                pct = chunk.get("context_pct", 0.0)
                cost = chunk.get("cost", 0.0)
                state.usage_label.set_text(f"Context: {ctx:.1f}k - {pct:.1f}% | Cost: ${cost:.4f}")

            elif chunk["type"] == "reasoning":
                if thinking_indicator:
                    try: thinking_indicator.delete()
                    except: pass
                    thinking_indicator = None
                total_reasoning += chunk["content"]
                if _reasoning_active:
                    state.log_activity(chunk["content"])
                else:
                    state.log_activity(f"[main] {chunk['content']}")
                    _reasoning_active = True

            elif chunk["type"] == "tool":
                _reasoning_active = False
                response_container = None
                if thinking_indicator:
                    try: thinking_indicator.delete()
                    except: pass
                    thinking_indicator = None
                state.log_activity(f"[main] ▸ tool: {chunk['content']}")

            elif chunk["type"] == "content":
                if thinking_indicator:
                    try: thinking_indicator.delete()
                    except: pass
                    thinking_indicator = None

                if response_container is None:
                    with state.chat_content:
                        response_container = ui.markdown("").classes("terminal-content")

                total_response += chunk["content"]
                state.status_label.set_text(f"Receiving response: {len(total_response)} chars")
                response_container.set_content((response_container.content or "") + chunk["content"])
                state.scroll_area.scroll_to(percent=1.0, duration=0)

        if thinking_indicator:
            try: thinking_indicator.delete()
            except: pass

        state.close_activity_log()
        state.status_label.set_text("Saving to DB...")
        state.messages.append({
            "role": "assistant",
            "content": total_response or None,
            "reasoning_content": total_reasoning or None
        })

        # Context compression: if context exceeds max_context, compress old messages
        compressed = await compress_messages(state.messages)
        if compressed is not state.messages:
            state.messages = compressed
            _debug(f"Context compressed — messages_count reduced to {len(state.messages)}")

        _debug(f"Saving to DB — session_id={state.current_session_id}, messages_count={len(state.messages)}, title={state.chat_title}")
        db.save_session(state.current_session_id, state.chat_title, state.messages)
        _debug("DB save complete")
        state.status_label.set_text("Done ✓")
        refresh_sidebar()
        state.status_label.set_text("Ready")

    except asyncio.CancelledError:
        _debug("=== _process_response CANCELLED ===")
        # Save partial response before raising
        if total_response or total_reasoning:
            state.messages.append({
                "role": "assistant",
                "content": total_response or None,
                "reasoning_content": total_reasoning or None
            })
            compressed = await compress_messages(state.messages)
            if compressed is not state.messages:
                state.messages = compressed
            _debug(f"Saving partial response on cancel ({len(total_response)} content, {len(total_reasoning)} reasoning chars)")
            db.save_session(state.current_session_id, state.chat_title, state.messages)
            refresh_sidebar()
        state.status_label.set_text("Cancelled")
        if response_container:
            response_container.set_content((response_container.content or "") + " _(interrupted)_")
        raise
    finally:
        activity_callback.set(None)
        agent_stream_callback.set(None)
