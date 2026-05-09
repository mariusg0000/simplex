"""
src/ui/app.py · Main UI layout · Top bar, sidebar, chat area, input bar.
"""

from nicegui import ui
from src.ui import state
from src.ui.sidebar import refresh_sidebar
from src.ui.settings import create_settings_dialog
from src.storage import storage


_FONT_SIZES = {
    1: ("0.75rem", "0.625rem", "0.625rem", "0.5rem"),
    2: ("0.8125rem", "0.6875rem", "0.6875rem", "0.5625rem"),
    3: ("0.875rem", "0.75rem", "0.75rem", "0.583rem"),
    4: ("0.9375rem", "0.75rem", "0.75rem", "0.625rem"),
    5: ("1.0625rem", "0.875rem", "0.875rem", "0.708rem"),
}
_LINE_SPACINGS = {1: "1.3", 2: "1.6", 3: "1.9"}


def _terminal_css_values():
    """Returns (content, prefix, reasoning, tool, line_height) for current prefs."""
    c, p, r, t = _FONT_SIZES.get(storage.prefs.font_size, _FONT_SIZES[4])
    ls = _LINE_SPACINGS.get(storage.prefs.line_spacing, _LINE_SPACINGS[2])
    return c, p, r, t, ls


def apply_terminal_styles():
    c, p, r, t, ls = _terminal_css_values()
    ui.run_javascript(f"""
        document.documentElement.style.setProperty('--terminal-content-size', '{c}');
        document.documentElement.style.setProperty('--terminal-prefix-size', '{p}');
        document.documentElement.style.setProperty('--terminal-reasoning-size', '{r}');
        document.documentElement.style.setProperty('--terminal-tool-size', '{t}');
        document.documentElement.style.setProperty('--terminal-line-height', '{ls}');
    """)


def init_ui():
    """Sets up the full UI layout and initializes global state."""
    state.init_messages()

    from src.ui.chat_view import setup_confirmation_dialog
    from src.engine.tools import registry
    from src.ui.chat_view import _show_confirmation_dialog
    setup_confirmation_dialog()
    registry.on_confirmation_required = _show_confirmation_dialog

    c, p, r, t, ls = _terminal_css_values()
    ui.add_head_html(f"""
        <style>
            html, body {{ margin: 0; padding: 0; height: 100vh; overflow: hidden; }}
            .nicegui-content {{ padding: 0 !important; margin: 0 !important; }}
            .selectable-text {{ user-select: text !important; cursor: text; }}

            /* Terminal chat styles — sizes controlled via CSS variables */
            .terminal-user-block {{
                background: #eef2ff !important;
                border-left: 2px solid #93c5fd !important;
                padding: 0.375rem 0.75rem !important;
                border-radius: 0 4px 4px 0 !important;
                margin-bottom: 0.25rem !important;
            }}
            .terminal-user-prefix {{
                font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', 'Menlo', 'DejaVu Sans Mono', monospace !important;
                font-size: var(--terminal-prefix-size, 0.75rem) !important;
                font-weight: 700 !important;
                color: #2563eb !important;
                margin-bottom: 0.125rem !important;
                line-height: var(--terminal-line-height, 1.6) !important;
            }}
            .terminal-content, .terminal-content .nicegui-markdown {{
                font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', 'Menlo', 'DejaVu Sans Mono', monospace !important;
                font-size: var(--terminal-content-size, 0.9375rem) !important;
                color: #1a1a1a !important;
                line-height: var(--terminal-line-height, 1.6) !important;
                user-select: text !important;
            }}
            .terminal-reasoning, .terminal-reasoning .nicegui-markdown {{
                font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', 'Menlo', 'DejaVu Sans Mono', monospace !important;
                font-size: var(--terminal-reasoning-size, 0.75rem) !important;
                color: #9ca3af !important;
                font-style: italic !important;
                line-height: var(--terminal-line-height, 1.6) !important;
            }}
            .terminal-tool {{
                font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', 'Menlo', 'DejaVu Sans Mono', monospace !important;
                font-size: var(--terminal-tool-size, 0.625rem) !important;
                color: #d1d5db !important;
                font-style: italic !important;
                line-height: var(--terminal-line-height, 1.6) !important;
            }}
            .terminal-content .nicegui-markdown * {{
                line-height: inherit !important;
            }}
            .terminal-content .nicegui-markdown p {{
                margin: 0 0 0.25rem 0 !important;
                min-height: 0 !important;
            }}
            .terminal-content .nicegui-markdown p:last-child {{
                margin-bottom: 0 !important;
            }}
            .terminal-content .nicegui-markdown code {{
                font-family: inherit !important;
                font-size: inherit !important;
                background: transparent !important;
                color: inherit !important;
                padding: 0 !important;
                border: none !important;
            }}
            .terminal-content .nicegui-markdown pre {{
                background: transparent !important;
                border: none !important;
                padding: 0 !important;
                margin: 0 0 0.25rem 0 !important;
                border-radius: 0 !important;
            }}
            .terminal-content .nicegui-markdown pre code {{
                background: transparent !important;
                padding: 0 !important;
                font-size: inherit !important;
            }}
            .terminal-content .nicegui-markdown ul,
            .terminal-content .nicegui-markdown ol {{
                margin: 0 !important;
                padding-left: 1.25rem !important;
            }}
            .terminal-content .nicegui-markdown li {{
                margin: 0 !important;
                line-height: inherit !important;
            }}
            .terminal-content .nicegui-markdown blockquote {{
                margin: 0 0 0.25rem 0 !important;
                padding: 0 0 0 1rem !important;
                border-left: 2px solid #d1d5db !important;
                color: inherit !important;
            }}
            .terminal-content .nicegui-markdown hr {{
                margin: 0.25rem 0 !important;
                border-color: #d1d5db !important;
            }}

            /* Tight heading scale: 1px difference between levels */
            .nicegui-markdown h1 {{ font-size: 1.125rem !important; line-height: 1.5rem !important; margin: 0.75rem 0 0.375rem 0 !important; font-weight: 600 !important; }}
            .nicegui-markdown h2 {{ font-size: 1.0625rem !important; line-height: 1.4rem !important; margin: 0.625rem 0 0.3125rem 0 !important; font-weight: 600 !important; }}
            .nicegui-markdown h3 {{ font-size: 1rem !important; line-height: 1.375rem !important; margin: 0.5rem 0 0.25rem 0 !important; font-weight: 600 !important; }}
            .nicegui-markdown h4 {{ font-size: 0.9375rem !important; line-height: 1.3rem !important; margin: 0.4375rem 0 0.1875rem 0 !important; font-weight: 600 !important; }}
            .nicegui-markdown h5 {{ font-size: 0.875rem !important; line-height: 1.25rem !important; margin: 0.375rem 0 0.125rem 0 !important; font-weight: 600 !important; }}
            .nicegui-markdown h6 {{ font-size: 0.8125rem !important; line-height: 1.2rem !important; margin: 0.3125rem 0 0.125rem 0 !important; font-weight: 600 !important; }}

            /* Sub-agent expansion: compact header */
            .sub-agent-expansion .q-item {{
                min-height: 22px !important;
                padding-top: 0 !important;
                padding-bottom: 0 !important;
                padding-left: 8px !important;
                padding-right: 8px !important;
            }}
            .sub-agent-expansion .q-item__section {{
                font-size: 0.6875rem !important;
            }}
            .sub-agent-expansion .q-expansion-item__content {{
                max-height: 200px;
                overflow-y: auto;
            }}
        </style>
        <script>
            document.addEventListener('DOMContentLoaded', function() {{
                var sizes = ['{c}', '{p}', '{r}', '{t}'];
                document.documentElement.style.setProperty('--terminal-content-size', sizes[0]);
                document.documentElement.style.setProperty('--terminal-prefix-size', sizes[1]);
                document.documentElement.style.setProperty('--terminal-reasoning-size', sizes[2]);
                document.documentElement.style.setProperty('--terminal-tool-size', sizes[3]);
                document.documentElement.style.setProperty('--terminal-line-height', '{ls}');
            }});
            document.addEventListener('click', function(e) {{
                var link = e.target.closest('.nicegui-markdown a');
                if (link) {{
                    e.preventDefault();
                    window.open(link.href, '_blank', 'noopener,noreferrer');
                }}
            }});
        </script>
    """)
    ui.query('body').classes('p-0 m-0 overflow-hidden')
    ui.query('.nicegui-content').classes('p-0 m-0')

    with ui.left_drawer(value=True).classes("bg-slate-100 p-2") as drawer:
        state.drawer = drawer
        state.sidebar_content = ui.column().classes("w-full gap-0")
        refresh_sidebar()

    settings_dialog = create_settings_dialog(apply_terminal_styles)

    with ui.column().classes("w-full h-screen no-wrap gap-0 p-0 m-0"):
        with ui.row().classes("w-full px-4 bg-primary text-white items-center").style("height: 50px; flex-shrink: 0;"):
            ui.button(icon="menu", on_click=lambda: state.drawer.toggle()).props("flat color=white dense")
            ui.label("Simplex AI").classes("font-bold text-lg")
            ui.space()
            ui.button(icon="settings", on_click=settings_dialog.open).props("flat color=white dense")

        state.scroll_area = ui.scroll_area().classes("w-full bg-white flex-grow min-h-0 overflow-y-auto")
        with state.scroll_area:
            state.chat_content = ui.column().classes("w-full p-4 gap-1")

        state.sub_agent_panel = ui.expansion(
            text="Sub-Agent Activity", icon="terminal",
            value=True,
        ).classes("sub-agent-expansion w-full border-t text-xs flex-shrink-0")
        with state.sub_agent_panel:
            state.sub_agent_content = ui.column().classes("w-full px-4 py-1 gap-0 bg-green-50")

        with ui.row().classes("w-full px-3 text-xs text-slate-400 bg-slate-100 border-t items-center").style("height: 24px; flex-shrink: 0;"):
            state.status_label = ui.label("Ready").classes("flex-grow")
            state.usage_label = ui.label("Context: 0k - 0.0% | Cost: $0.000").classes("text-right whitespace-nowrap")

        with ui.row().classes("w-full px-4 bg-slate-50 items-center border-t shadow-inner").style("height: 56px; flex-shrink: 0;"):
            from src.ui.chat_view import handle_send
            state.message_input = ui.input(placeholder="Message...").classes("flex-grow").props("outlined bg-color=white dense")
            state.message_input.on("keydown.enter", handle_send)
            ui.button(icon="send", on_click=handle_send).props("round flat color=primary size=md")
