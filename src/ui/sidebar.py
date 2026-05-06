"""
src/ui/sidebar.py · Sidebar UI · Chat session list, rename, archive, delete.
"""

from nicegui import ui
from src.ui import state
from src.db import db


def refresh_sidebar():
    """Updates the list of chat sessions in the drawer with compact items and action buttons."""
    state.sidebar_content.clear()
    sessions = db.list_sessions()
    with state.sidebar_content:
        from src.ui.chat_view import start_new_chat
        ui.button("New Chat", icon="add", on_click=start_new_chat).classes("w-full mb-2").props("outline color=primary dense")

        if not sessions:
            ui.label("Empty").classes("text-gray-400 italic text-xs text-center w-full mt-4")
            return

        for s in sessions:
            from src.ui.chat_view import load_chat
            row = ui.row().classes("w-full items-center no-wrap group hover:bg-slate-200 rounded px-1 h-8 m-0 cursor-pointer")
            with row:
                row.on('click', lambda sid=s["id"]: load_chat(sid))
                ui.label(s["title"]).classes("truncate text-left text-[13px] text-slate-700 flex-grow py-1")
                with ui.row().classes("opacity-0 group-hover:opacity-100 items-center gap-0 shrink-0").on('click', lambda e: e.stop_propagation()):
                    ui.button(icon="edit", on_click=lambda sid=s["id"], t=s["title"]: open_edit_dialog(sid, t)).props("flat round dense size=xs color=slate-400").classes("hover:text-primary")
                    ui.button(icon="archive", on_click=lambda sid=s["id"]: archive_chat(sid)).props("flat round dense size=xs color=slate-400").classes("hover:text-amber-600")
                    ui.button(icon="delete", on_click=lambda sid=s["id"]: delete_chat(sid)).props("flat round dense size=xs color=slate-400").classes("hover:text-red-600")


async def open_edit_dialog(session_id: str, current_title: str):
    """Opens a dialog to rename a chat session."""
    with ui.dialog() as dialog, ui.card().classes('w-80 p-4'):
        ui.label('Rename Chat').classes('font-bold mb-2')
        new_title_input = ui.input(value=current_title).classes('w-full mb-4').props('outlined dense auto-focus')
        with ui.row().classes('w-full justify-end gap-2'):
            ui.button('Cancel', on_click=dialog.close).props('flat')
            def save_title():
                if new_title_input.value.strip():
                    db.update_title(session_id, new_title_input.value.strip())
                    refresh_sidebar()
                    dialog.close()
            ui.button('Save', on_click=save_title).props('flat color=primary')
    dialog.open()


async def archive_chat(session_id: str):
    """Archives a chat by adding a box icon prefix."""
    session = db.get_session(session_id)
    if session:
        new_title = f"\U0001f4e6 {session['title']}"
        db.update_title(session_id, new_title)
        refresh_sidebar()


async def delete_chat(session_id: str):
    """Deletes a chat and refreshes the list."""
    from src.ui.chat_view import start_new_chat
    db.delete_session(session_id)
    if state.current_session_id == session_id:
        await start_new_chat()
    else:
        refresh_sidebar()
