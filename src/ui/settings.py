"""
src/ui/settings.py · Settings dialog · Working directories and UI preferences.
"""

from nicegui import ui
from src.ui import state
from src.storage import storage
from src.ui.state import build_install_command, find_tool, load_cli_prompts


def create_settings_dialog(on_style_change=None):
    """Creates and returns a settings dialog element."""
    with ui.dialog() as dialog, ui.card().classes('w-96 p-4'):
        ui.label('Settings').classes('text-xl font-bold mb-2')

        def change_font_size(e):
            storage.update_preference("font_size", int(e.value))
            if on_style_change:
                on_style_change()

        def change_line_spacing(e):
            storage.update_preference("line_spacing", int(e.value))
            if on_style_change:
                on_style_change()

        with ui.row().classes("w-full gap-2 items-center mb-2"):
            ui.label("Font size").classes("text-sm").style("width: 100px")
            ui.select({1: "1 (tiny)", 2: "2 (small)", 3: "3 (normal)", 4: "4 (large)", 5: "5 (xl)"},
                      value=storage.prefs.font_size, on_change=change_font_size).props("outlined dense").classes("flex-grow")

        with ui.row().classes("w-full gap-2 items-center mb-4"):
            ui.label("Line spacing").classes("text-sm").style("width: 100px")
            ui.select({1: "1 (compact)", 2: "2 (normal)", 3: "3 (spacious)"},
                      value=storage.prefs.line_spacing, on_change=change_line_spacing).props("outlined dense").classes("flex-grow")

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

        ui.separator().classes('my-3')
        ui.label('Installed Tools').classes('text-sm font-semibold text-gray-500 mb-1')
        for cmd in load_cli_prompts():
            installed = find_tool(cmd) is not None
            with ui.row().classes('w-full items-center gap-2 py-0.5'):
                color = 'black' if installed else 'red-800'
                ui.label(cmd).classes(f'text-sm font-bold text-{color}')
                status = 'installed' if installed else 'not installed (please install)'
                ui.label(status).classes('text-xs ml-1')

        install_cmd = build_install_command()
        if install_cmd:
            ui.separator().classes('my-3')
            ui.label('Install missing tools').classes('text-sm font-semibold text-gray-500 mb-1')
            ui.textarea(value=install_cmd).props('readonly outlined dense').classes('w-full')

        ui.button('Close', on_click=dialog.close).classes('w-full mt-4')

    return dialog
