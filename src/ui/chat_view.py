"""
src/ui/chat_view.py · Chat logic · Message handling, streaming response display.
"""

import asyncio
from nicegui import ui
from src.ui import state
from src.ui.sidebar import refresh_sidebar
from src.db import db
from src.storage import storage
from src.engine.chat import stream_chat
from src.engine.tools import registry


async def start_new_chat():
    """Resets the UI and state for a fresh conversation."""
    if state.active_task and not state.active_task.done():
        state.active_task.cancel()

    state.current_session_id = str(__import__("uuid").uuid4())
    state.chat_title = "New Chat"
    state.init_messages()
    state.chat_content.clear()
    refresh_sidebar()


async def refresh_chat_display():
    """Re-renders all messages based on current state and preferences."""
    state.chat_content.clear()
    with state.chat_content:
        dialogue = state.messages[1:] if state.messages and state.messages[0]["role"] == "system" else state.messages

        last_assistant_tool_calls: list[dict] | None = None
        for msg in dialogue:
            if msg["role"] == "user":
                ui.chat_message(msg["content"], name="You", sent=True, avatar="https://api.dicebear.com/7.x/avataaars/svg?seed=User")

            elif msg["role"] == "assistant":
                last_assistant_tool_calls = msg.get("tool_calls")
                reasoning = msg.get("reasoning_content")
                content = msg.get("content")
                show_reasoning = storage.prefs.show_reasoning

                # Content bubble — only when the model emitted actual content text.
                # We NEVER promote reasoning to content here; reasoning has its own visual block.
                if content:
                    with ui.chat_message(name="Simplex AI", sent=False, avatar="https://api.dicebear.com/7.x/bottts/svg?seed=Simplex"):
                        ui.markdown(content)

                # When show_reasoning is OFF, we NEVER display reasoning text anywhere.

                # Reasoning card — separate visual block, only shown when the user enables it.
                # Always appears AFTER the content bubble with a separator in between.
                if reasoning and show_reasoning:
                    if content:
                        ui.separator().classes("my-1 opacity-30")
                    with ui.card().classes("w-full bg-indigo-50 px-3 py-1 shadow-none border-l-4 border-primary gap-0"):
                        ui.label("Reasoning Process:").classes("text-[10px] font-bold text-primary m-0 p-0 uppercase")
                        with ui.scroll_area().classes("h-20 w-full m-0 p-0"):
                            ui.markdown(reasoning).classes("text-sm text-slate-600 italic selectable-text")

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
                label = f"Used tool: {msg.get('name', 'unknown')}"
                if cmd_snippet:
                    label += f" — {cmd_snippet}"
                ui.label(label).classes("text-[10px] text-gray-400 italic")

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

    if state.chat_title == "New Chat":
        state.chat_title = user_input[:40] + ("..." if len(user_input) > 40 else "")
        refresh_sidebar()

    state.message_input.value = ""
    with state.chat_content:
        ui.chat_message(user_input, name="You", sent=True, avatar="https://api.dicebear.com/7.x/avataaars/svg?seed=User")

    state.messages.append({"role": "user", "content": user_input})

    with state.chat_content:
        thinking_container = ui.row().classes("items-center gap-2 text-gray-400 italic")
        with thinking_container:
            ui.spinner(size="sm")
            ui.label("Thinking...")

    state.scroll_area.scroll_to(percent=1.0, duration=0.2)
    state.active_task = asyncio.create_task(_process_response(thinking_indicator=thinking_container))


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


async def _process_response(thinking_indicator: ui.element):
    """Streams the LLM response and saves to database at the end."""
    try:
        total_response = ""
        total_reasoning = ""

        response_container = None
        reasoning_container = None
        reasoning_scroll = None
        tool_indicator = None

        all_reasoning_cards = []

        async for chunk in stream_chat(state.messages):
            if chunk["type"] == "reasoning":
                if thinking_indicator:
                    try: thinking_indicator.delete()
                    except: pass
                    thinking_indicator = None

                if reasoning_container is None:
                    with state.chat_content:
                        reasoning_card = ui.card().classes("w-full bg-indigo-50 px-3 py-1 shadow-none border-l-4 border-primary gap-0")
                        all_reasoning_cards.append(reasoning_card)
                        with reasoning_card:
                            ui.label("Reasoning Process:").classes("text-[10px] font-bold text-primary m-0 p-0 uppercase")
                            reasoning_scroll = ui.scroll_area().classes("h-20 w-full m-0 p-0")
                            with reasoning_scroll:
                                reasoning_container = ui.markdown("").classes("text-sm text-slate-600 italic selectable-text")

                total_reasoning += chunk["content"]
                reasoning_container.set_content((reasoning_container.content or "") + chunk["content"])
                if reasoning_scroll:
                    reasoning_scroll.scroll_to(percent=1.0, duration=0)
                state.scroll_area.scroll_to(percent=1.0, duration=0.1)

            elif chunk["type"] == "tool":
                response_container = None
                reasoning_container = None
                reasoning_scroll = None

                if thinking_indicator:
                    try: thinking_indicator.delete()
                    except: pass
                    thinking_indicator = None
                if tool_indicator:
                    try: tool_indicator.delete()
                    except: pass

                with state.chat_content:
                    tool_indicator = ui.row().classes("items-center gap-2 text-amber-600 italic text-sm bg-amber-50 p-1 rounded px-2 border border-amber-200")
                    with tool_indicator:
                        ui.icon("settings", size="xs")
                        ui.label(chunk["content"])
                state.scroll_area.scroll_to(percent=1.0, duration=0.1)

            elif chunk["type"] == "content":
                if thinking_indicator:
                    try: thinking_indicator.delete()
                    except: pass
                    thinking_indicator = None

                if response_container is None:
                    with state.chat_content:
                        with ui.chat_message(name="Simplex AI", sent=False, avatar="https://api.dicebear.com/7.x/bottts/svg?seed=Simplex"):
                            response_container = ui.markdown("")

                total_response += chunk["content"]
                response_container.set_content((response_container.content or "") + chunk["content"])
                state.scroll_area.scroll_to(percent=1.0, duration=0)

        if thinking_indicator:
            try: thinking_indicator.delete()
            except: pass

        if not storage.prefs.show_reasoning:
            for card in all_reasoning_cards:
                try: card.delete()
                except: pass

        # When show_reasoning is OFF, reasoning cards were deleted above.
        # Never promote reasoning to content — the model's response is authoritative.

        # Preserve model's raw output: NEVER promote reasoning -> content.
        # The two fields are semantically distinct. Content = final response,
        # reasoning_content = internal monologue. Display logic handles fallbacks.
        state.messages.append({
            "role": "assistant",
            "content": total_response or None,
            "reasoning_content": total_reasoning or None
        })
        db.save_session(state.current_session_id, state.chat_title, state.messages)
        refresh_sidebar()

    except asyncio.CancelledError:
        if response_container:
            response_container.set_content((response_container.content or "") + " _(interrupted)_")
        raise
