"""
src/ui/settings.py · Settings dialog · Working directories and UI preferences.
"""

from nicegui import ui
from src.ui import state
from src.ui.chat_view import refresh_chat_display
from src.storage import storage


def create_settings_dialog():
    """Creates and returns a settings dialog element."""
    with ui.dialog() as dialog, ui.card().classes('w-96 p-4'):
        ui.label('Settings').classes('text-xl font-bold mb-2')

        async def toggle_reasoning(e):
            storage.update_preference("show_reasoning", e.value)
            await refresh_chat_display()
        state.show_reasoning_checkbox = ui.checkbox("Show Reasoning", value=storage.prefs.show_reasoning, on_change=toggle_reasoning).classes("mb-4")

        ui.label('Working Directories').classes('text-sm font-semibold text-gray-500 mb-1')
        folders_container = ui.column().classes('w-full gap-1 mb-4')

        def refresh_folders():
            folders_container.clear()
            for path in storage.prefs.working_directories:
                with folders_container, ui.row().classes('w-full items-center justify-between bg-gray-100 p-1 rounded px-2'):
                    ui.label(path).classes('text-xs truncate flex-grow')
                    ui.button(icon='delete', on_click=lambda p=path: remove_folder(p)).props('flat round dense color=red size=xs')

        def remove_folder(path):
            storage.prefs.working_directories.remove(path)
            storage.save()
            refresh_folders()

        def add_folder():
            path = new_folder_input.value.strip()
            if path:
                storage.prefs.working_directories.append(path)
                storage.save()
                new_folder_input.value = ''
                refresh_folders()

        refresh_folders()

        with ui.row().classes('w-full gap-2 items-center'):
            new_folder_input = ui.input(placeholder='Path...').classes('flex-grow').props('outlined dense')
            ui.button(icon='add', on_click=add_folder).props('flat round color=primary')

        ui.button('Close', on_click=dialog.close).classes('w-full mt-4')

    return dialog
