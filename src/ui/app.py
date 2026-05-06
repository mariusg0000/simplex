"""
src/ui/app.py · Main UI layout · Top bar, sidebar, chat area, input bar.
"""

from nicegui import ui
from src.ui import state
from src.ui.sidebar import refresh_sidebar
from src.ui.settings import create_settings_dialog


def init_ui():
    """Sets up the full UI layout and initializes global state."""
    state.init_messages()

    ui.add_head_html("""
        <style>
            html, body { margin: 0; padding: 0; height: 100vh; overflow: hidden; }
            .nicegui-content { padding: 0 !important; margin: 0 !important; }
            .q-message-text, .q-markdown { user-select: text !important; }
            .selectable-text { user-select: text !important; cursor: text; }
        </style>
    """)
    ui.query('body').classes('p-0 m-0 overflow-hidden')
    ui.query('.nicegui-content').classes('p-0 m-0')

    with ui.left_drawer(value=True).classes("bg-slate-100 p-2") as drawer:
        state.drawer = drawer
        state.sidebar_content = ui.column().classes("w-full gap-0")
        refresh_sidebar()

    settings_dialog = create_settings_dialog()

    with ui.column().classes("w-full h-screen no-wrap gap-0 p-0 m-0"):
        with ui.row().classes("w-full px-4 bg-primary text-white items-center").style("height: 50px;"):
            ui.button(icon="menu", on_click=lambda: state.drawer.toggle()).props("flat color=white dense")
            ui.label("Simplex AI").classes("font-bold text-lg")
            ui.space()
            ui.button(icon="settings", on_click=settings_dialog.open).props("flat color=white dense")

        state.scroll_area = ui.scroll_area().classes("w-full bg-white").style("height: calc(100vh - 130px);")
        with state.scroll_area:
            state.chat_content = ui.column().classes("w-full p-4 gap-4")

        with ui.row().classes("w-full px-4 bg-slate-50 items-center border-t shadow-inner").style("height: 80px;"):
            from src.ui.chat_view import handle_send
            state.message_input = ui.input(placeholder="Message...").classes("flex-grow").props("outlined bg-color=white")
            state.message_input.on("keydown.enter", handle_send)
            ui.button(icon="send", on_click=handle_send).props("round flat color=primary size=lg")
