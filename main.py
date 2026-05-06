"""
main.py · Main Entry Point · Initializes and runs the NiceGUI application.
"""

import asyncio
from nicegui import ui
from src.engine.chat import stream_chat
from src.config import settings

from src.storage import storage
from src.engine.tools import tool
from src.engine.file_search import file_search, list_directory
from src.engine.doc_reader import read_document_content

# --- Example Tools ---
@tool
def get_current_time():
    """Returns the current server time."""
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

@tool
def calculator(expression: str):
    """Evaluates a simple mathematical expression."""
    try:
        # Warning: eval is dangerous in production, use a safe math parser for real use
        return str(eval(expression, {"__builtins__": None}, {}))
    except Exception as e:
        return f"Error: {str(e)}"
# --- End Example Tools ---

# State management for the chat
messages = [
    {
        "role": "system", 
        "content": settings.system_prompt + (
            "\n\nSTRATEGIC GUIDELINES:\n"
            "1. BE EFFICIENT: Do not perform more than 2 search attempts for the same request.\n"
            "2. TRUST THE TOOLS: If a search tool returns results, those are the best matches. Present them immediately.\n"
            "3. NO REDUNDANCY: Do not call the same tool with slightly different parameters if you already have relevant data.\n"
            "4. RERANKER TRUST: The file search tool uses an internal Reranker. The top results it returns are the final candidates."
        )
    }
]
active_task: asyncio.Task = None

async def handle_preference_change(e):
    """Saves preference changes to local storage."""
    storage.update_preference("show_reasoning", e.value)

async def handle_send():
    """
    WHAT:    Handles user submission, cancels previous tasks, and shows thinking state.
    WHY:     Ensures only one active LLM call and provides visual feedback.
    HOW:     Cancels active_task if it exists, adds a spinner, then starts a new stream task.
    """
    global active_task
    
    user_input = message_input.value
    if not user_input.strip():
        return

    # 1. Cancel ongoing response if any
    if active_task and not active_task.done():
        active_task.cancel()
        try:
            await active_task
        except asyncio.CancelledError:
            pass

    # 2. Display user message
    message_input.value = ""
    with chat_content:
        ui.chat_message(user_input, name="You", sent=True, avatar="https://api.dicebear.com/7.x/avataaars/svg?seed=User")
        
    messages.append({"role": "user", "content": user_input})
    
    # 3. Create thinking indicator
    with chat_content:
        thinking_container = ui.row().classes("items-center gap-2 text-gray-400 italic")
        with thinking_container:
            ui.spinner(size="sm")
            ui.label("Thinking...")
    
    scroll_area.scroll_to(percent=1.0, duration=0.2)
    
    # 4. Start the streaming task
    active_task = asyncio.create_task(process_response(thinking_container))

async def process_response(thinking_indicator: ui.element):
    """
    Logic for streaming response, handles reasoning, tools, and final content.
    """
    try:
        full_response = ""
        full_reasoning = ""
        response_container = None
        reasoning_card = None
        reasoning_scroll = None
        reasoning_container = None
        tool_indicator = None
        chunk_count = 0
        
        async for chunk in stream_chat(messages):
            if chunk["type"] == "reasoning":
                # Create reasoning box if it doesn't exist
                if reasoning_container is None:
                    if thinking_indicator:
                        try: thinking_indicator.delete()
                        except: pass
                        thinking_indicator = None
                    
                    with chat_content:
                        # gap-0 eliminates the space between the label and the scroll area
                        reasoning_card = ui.card().classes("w-full bg-slate-100 px-3 py-1 shadow-none border-l-4 border-primary gap-0")
                        with reasoning_card:
                            # Explicit height and line-height for the label
                            ui.label("Reasoning Process:").classes("text-[10px] font-bold text-primary m-0 p-0 uppercase").style("line-height: 12px; height: 12px;")
                            # Ensure scroll area has no extra margins/paddings
                            reasoning_scroll = ui.scroll_area().classes("h-20 w-full m-0 p-0")
                            with reasoning_scroll:
                                reasoning_container = ui.label("").classes("text-sm text-gray-600 italic leading-tight m-0 p-0")
                
                full_reasoning += chunk["content"]
                reasoning_container.set_text(full_reasoning)
                reasoning_scroll.scroll_to(percent=1.0, duration=0)
                scroll_area.scroll_to(percent=1.0, duration=0.1)

            elif chunk["type"] == "tool":
                # Show tool execution status
                if thinking_indicator:
                    try: thinking_indicator.delete()
                    except: pass
                    thinking_indicator = None
                
                if tool_indicator:
                    try: tool_indicator.delete()
                    except: pass

                with chat_content:
                    tool_indicator = ui.row().classes("items-center gap-2 text-amber-600 italic text-sm bg-amber-50 p-1 rounded px-2 border border-amber-200")
                    with tool_indicator:
                        ui.icon("settings", size="xs")
                        ui.label(chunk["content"])
                scroll_area.scroll_to(percent=1.0, duration=0.1)

            elif chunk["type"] == "content":
                # When actual content starts, handle reasoning/thinking/tool cleanup
                if response_container is None:
                    if thinking_indicator:
                        try: thinking_indicator.delete()
                        except: pass
                    
                    if tool_indicator:
                        try: tool_indicator.delete()
                        except: pass
                    
                    if reasoning_card:
                        if not show_reasoning_checkbox.value:
                            try: reasoning_card.delete()
                            except: pass
                        else:
                            # Dim the reasoning card to show it's historical
                            reasoning_card.classes("opacity-60 bg-slate-50")
                    
                    with chat_content:
                        with ui.chat_message(name="Simplex AI", sent=False, avatar="https://api.dicebear.com/7.x/bottts/svg?seed=Simplex"):
                            response_container = ui.markdown("")
                
                full_response += chunk["content"]
                response_container.set_content(full_response)
                
                chunk_count += 1
                if chunk_count % 2 == 0:
                    scroll_area.scroll_to(percent=1.0, duration=0)
        
        # Final adjustment
        await asyncio.sleep(0.1)
        scroll_area.scroll_to(percent=1.0, duration=0.2)
        messages.append({"role": "assistant", "content": full_response})
        
    except asyncio.CancelledError:
        if response_container:
            response_container.set_content(full_response + " _(interrupted)_")
        else:
            if thinking_indicator:
                try:
                    thinking_indicator.delete()
                except:
                    pass
            if reasoning_card:
                try:
                    reasoning_card.delete()
                except:
                    pass
        raise

# UI Layout
def init_ui():
    # Force text selection and normalize Markdown styling
    ui.add_head_html("""
        <style>
            /* Selection and basic text */
            .q-message-text, .q-markdown, .q-markdown * {
                user-select: text !important;
                -webkit-user-select: text !important;
            }
            
            /* Normalized Markdown - GitHub Style - Aggressive Normalization */
            .q-markdown {
                font-size: 14px !important;
                line-height: 1.5 !important;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif !important;
            }
            .q-markdown h1, .q-markdown h2, .q-markdown h3, 
            .q-markdown h4, .q-markdown h5, .q-markdown h6 {
                margin-top: 12px !important;
                margin-bottom: 4px !important;
                font-weight: 600 !important;
                line-height: 1.25 !important;
                color: #24292e !important;
                border-bottom: none !important;
            }
            .q-markdown h1 { font-size: 1.25em !important; margin-top: 0 !important; }
            .q-markdown h2 { font-size: 1.15em !important; }
            .q-markdown h3 { font-size: 1.05em !important; }
            .q-markdown h4 { font-size: 1em !important; }
            
            .q-markdown p { margin-bottom: 8px !important; }
            
            /* Code blocks */
            .q-markdown pre {
                background-color: #f6f8fa;
                border-radius: 6px;
                padding: 16px;
                overflow: auto;
                font-family: 'Fira Code', 'Cascadia Code', monospace;
                font-size: 85%;
                border: 1px solid #d1d5da;
            }
        </style>
    """)
    
    ui.query('body').classes('bg-slate-50')

    # Settings Dialog
    with ui.dialog() as settings_dialog, ui.card().classes('w-96 p-4'):
        ui.label('Settings').classes('text-xl font-bold mb-2')
        ui.label('Working Directories').classes('text-sm font-semibold text-gray-500 mb-1')
        
        folders_container = ui.column().classes('w-full gap-1 mb-4')
        
        def refresh_folders():
            folders_container.clear()
            for path in storage.prefs.working_directories:
                with folders_container, ui.row().classes('w-full items-center justify-between bg-gray-100 p-2 rounded'):
                    ui.label(path).classes('text-xs truncate flex-grow')
                    ui.button(icon='delete', on_click=lambda p=path: remove_folder(p)).props('flat round dense color=red size=sm')
        
        def remove_folder(path):
            storage.prefs.working_directories.remove(path)
            storage.save()
            refresh_folders()
            
        def add_folder():
            path = new_folder_input.value.strip()
            if path and path not in storage.prefs.working_directories:
                storage.prefs.working_directories.append(path)
                storage.save()
                new_folder_input.value = ''
                refresh_folders()
        
        refresh_folders()
        
        with ui.row().classes('w-full gap-2 items-center'):
            new_folder_input = ui.input(placeholder='Add folder path...').classes('flex-grow').props('outlined dense')
            ui.button(icon='add', on_click=add_folder).props('flat round color=primary')
            
        ui.button('Close', on_click=settings_dialog.close).classes('w-full mt-4')

    with ui.column().classes("w-full max-w-3xl mx-auto p-4 h-screen items-stretch"):
        with ui.row().classes("w-full items-center justify-between mb-4"):
            with ui.row().classes("items-center gap-4"):
                ui.label("Simplex AI").classes("text-3xl font-bold text-primary")
                ui.badge("v1.0.0 (NiceGUI Native)").classes("p-2")
            
            with ui.row().classes("items-center gap-2"):
                # Settings button
                ui.button(icon='settings', on_click=settings_dialog.open).props('flat round color=gray')
                # Feature toggle
                global show_reasoning_checkbox
                show_reasoning_checkbox = ui.checkbox(
                    "Show Reasoning", 
                    value=storage.prefs.show_reasoning,
                    on_change=handle_preference_change
                ).classes("text-xs text-gray-500")
        
        # Reliable scroll area
        global scroll_area, chat_content
        scroll_area = ui.scroll_area().classes("flex-grow w-full mb-4 bg-white rounded-lg shadow-sm border")
        with scroll_area:
            chat_content = ui.column().classes("w-full p-6 gap-4")
        
        # Input area fixed at bottom
        with ui.card().classes("w-full p-2 mb-4 shadow-md"):
            with ui.row().classes("w-full gap-2 items-center"):
                global message_input
                message_input = ui.input(placeholder="How can I help you today?").classes("flex-grow").props("outlined dense")
                message_input.on("keydown.enter", handle_send)
                ui.button(on_click=handle_send).props("icon=send color=primary round flat")

if __name__ in {"__main__", "__mp_main__"}:
    init_ui()
    ui.run(
        title="Simplex AI", 
        port=8080, 
        dark=False, 
        native=settings.native_mode,
        window_size=(1200, 800),
        reload=False  # Recommended for native mode to avoid some multiprocessing issues
    )
