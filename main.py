"""
main.py · Main Entry Point · Initializes and runs the NiceGUI application.
"""

import asyncio
import uuid
import json
from nicegui import ui
from src.engine.chat import stream_chat
from src.config import settings

from src.storage import storage
from src.db import db
from src.engine.tools import tool
from src.engine.file_search import file_search, list_directory
from src.engine.doc_reader import read_document_content

# --- Global State ---
current_session_id = str(uuid.uuid4())
chat_title = "New Chat"
messages = []
active_task: asyncio.Task = None

def get_system_prompt():
    """Returns the current system prompt with strategic guidelines."""
    return {
        "role": "system", 
        "content": settings.system_prompt + (
            "\n\nSTRATEGIC GUIDELINES:\n"
            "1. BE EFFICIENT: Do not perform more than 2 search attempts for the same request.\n"
            "2. TRUST THE TOOLS: If a search tool returns results, those are the best matches. Present them immediately.\n"
            "3. NO REDUNDANCY: Do not call the same tool with slightly different parameters if you already have relevant data.\n"
            "4. RERANKER TRUST: The file search tool uses an internal Reranker. The top results it returns are the final candidates."
        )
    }

def init_messages():
    """Initializes messages with the dynamic system prompt."""
    global messages
    messages = [get_system_prompt()]

init_messages()

# --- Tool Examples ---
@tool
def get_current_time():
    """Returns the current server time."""
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

@tool
def calculator(expression: str):
    """Evaluates a simple mathematical expression."""
    try:
        return str(eval(expression, {"__builtins__": None}, {}))
    except Exception as e:
        return f"Error: {str(e)}"

# --- Chat Logic ---

async def start_new_chat():
    """Resets the UI and state for a fresh conversation."""
    global current_session_id, chat_title, active_task
    
    if active_task and not active_task.done():
        active_task.cancel()
    
    current_session_id = str(uuid.uuid4())
    chat_title = "New Chat"
    init_messages()
    chat_content.clear()
    refresh_sidebar()
    ui.notify("Started new conversation")

async def refresh_chat_display():
    """Re-renders all messages based on current state and preferences."""
    chat_content.clear()
    with chat_content:
        # We skip the system prompt (index 0)
        dialogue = messages[1:] if messages and messages[0]["role"] == "system" else messages
        
        for msg in dialogue:
            if msg["role"] == "user":
                ui.chat_message(msg["content"], name="You", sent=True, avatar="https://api.dicebear.com/7.x/avataaars/svg?seed=User")
            
            elif msg["role"] == "assistant":
                # Render reasoning if present AND preference is enabled
                if msg.get("reasoning_content") and storage.prefs.show_reasoning:
                    with ui.card().classes("w-full bg-slate-50 px-3 py-1 shadow-none border-l-4 border-gray-300 gap-0 opacity-70"):
                        ui.label("Reasoning:").classes("text-[10px] font-bold text-gray-500 m-0 p-0 uppercase")
                        with ui.scroll_area().classes("h-16 w-full m-0 p-0"):
                            ui.markdown(msg["reasoning_content"]).classes("text-sm text-gray-500 italic selectable-text")
                
                # Render final response
                if msg.get("content"):
                    with ui.chat_message(name="Simplex AI", sent=False, avatar="https://api.dicebear.com/7.x/bottts/svg?seed=Simplex"):
                        ui.markdown(msg["content"])
            
            elif msg["role"] == "tool":
                ui.label(f"Used tool: {msg.get('name', 'unknown')}").classes("text-[10px] text-gray-400 italic")

    await asyncio.sleep(0.1) # Wait for UI to settle
    scroll_area.scroll_to(percent=1.0, duration=0.2)

async def load_chat(session_id: str):
    """Loads a previous session from the database."""
    global current_session_id, chat_title, messages, active_task
    
    if active_task and not active_task.done():
        active_task.cancel()

    session = db.get_session(session_id)
    if not session:
        ui.notify("Error: Session not found", type='negative')
        return

    current_session_id = session_id
    chat_title = session["title"]
    
    # Re-inject system prompt + load historical dialogue
    messages = [get_system_prompt()] + session["messages"]
    
    await refresh_chat_display()
    ui.notify(f"Loaded: {chat_title}")

async def handle_send():
    """Handles user input and starts LLM processing."""
    global active_task, chat_title
    
    user_input = message_input.value
    if not user_input.strip():
        return

    if active_task and not active_task.done():
        active_task.cancel()
        try: await active_task
        except asyncio.CancelledError: pass

    # Update title if it's the first message
    if chat_title == "New Chat":
        chat_title = user_input[:40] + ("..." if len(user_input) > 40 else "")
        refresh_sidebar()

    message_input.value = ""
    with chat_content:
        ui.chat_message(user_input, name="You", sent=True, avatar="https://api.dicebear.com/7.x/avataaars/svg?seed=User")
        
    messages.append({"role": "user", "content": user_input})
    
    with chat_content:
        thinking_container = ui.row().classes("items-center gap-2 text-gray-400 italic")
        with thinking_container:
            ui.spinner(size="sm")
            ui.label("Thinking...")
    
    scroll_area.scroll_to(percent=1.0, duration=0.2)
    active_task = asyncio.create_task(process_response(thinking_container))

async def process_response(thinking_indicator: ui.element):
    """Streams the LLM response and saves to database at the end."""
    try:
        full_response = ""
        full_reasoning = ""
        response_container = None
        reasoning_card = None
        reasoning_container = None
        reasoning_scroll = None
        tool_indicator = None
        
        async for chunk in stream_chat(messages):
            if chunk["type"] == "reasoning":
                if reasoning_container is None:
                    if thinking_indicator:
                        try: thinking_indicator.delete()
                        except: pass
                        thinking_indicator = None
                    with chat_content:
                        reasoning_card = ui.card().classes("w-full bg-slate-100 px-3 py-1 shadow-none border-l-4 border-primary gap-0")
                        with reasoning_card:
                            ui.label("Reasoning Process:").classes("text-[10px] font-bold text-primary m-0 p-0 uppercase")
                            reasoning_scroll = ui.scroll_area().classes("h-20 w-full m-0 p-0")
                            with reasoning_scroll:
                                reasoning_container = ui.markdown("").classes("text-sm text-gray-600 italic selectable-text")
                
                full_reasoning += chunk["content"]
                reasoning_container.set_content(full_reasoning)
                if reasoning_scroll:
                    reasoning_scroll.scroll_to(percent=1.0, duration=0)
                scroll_area.scroll_to(percent=1.0, duration=0.1)

            elif chunk["type"] == "tool":
                if thinking_indicator:
                    try: thinking_indicator.delete()
                    except: pass
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
                if response_container is None:
                    if thinking_indicator:
                        try: thinking_indicator.delete()
                        except: pass
                    if tool_indicator:
                        try: tool_indicator.delete()
                        except: pass
                    if reasoning_card and not storage.prefs.show_reasoning:
                        try: reasoning_card.delete()
                        except: pass
                    with chat_content:
                        with ui.chat_message(name="Simplex AI", sent=False, avatar="https://api.dicebear.com/7.x/bottts/svg?seed=Simplex"):
                            response_container = ui.markdown("")
                
                full_response += chunk["content"]
                response_container.set_content(full_response)
                scroll_area.scroll_to(percent=1.0, duration=0)
        
        messages.append({
            "role": "assistant", 
            "content": full_response,
            "reasoning_content": full_reasoning if full_reasoning else None
        })
        # SAVE TO DB
        db.save_session(current_session_id, chat_title, messages)
        refresh_sidebar()
        
    except asyncio.CancelledError:
        if response_container:
            response_container.set_content(full_response + " _(interrupted)_")
        raise

# --- UI Layout ---

def refresh_sidebar():
    """Updates the list of chat sessions in the drawer."""
    sidebar_content.clear()
    sessions = db.list_sessions()
    with sidebar_content:
        ui.button("New Chat", icon="add", on_click=start_new_chat).classes("w-full mb-4").props("outline color=primary")
        
        if not sessions:
            ui.label("No history yet").classes("text-gray-400 italic text-sm text-center w-full")
            return

        for s in sessions:
            with ui.row().classes("w-full items-center gap-1 group"):
                # Use a button that stretches to fill
                btn = ui.button(s["title"], on_click=lambda sid=s["id"]: load_chat(sid)).classes("flex-grow truncate text-left lowercase").props("flat dense color=black")
                btn.style("text-transform: none; max-width: 180px; justify-content: flex-start;")
                
                # Delete button visible on hover (simulated with group)
                with ui.button(icon="delete", on_click=lambda sid=s["id"]: delete_chat(sid)).props("flat round dense color=red size=sm").classes("opacity-0 group-hover:opacity-100"):
                    pass

async def delete_chat(session_id: str):
    """Deletes a chat and refreshes the list."""
    global current_session_id
    db.delete_session(session_id)
    if current_session_id == session_id:
        await start_new_chat()
    else:
        refresh_sidebar()
    ui.notify("Chat deleted")

def init_ui():
    # 1. CSS to kill ALL margins and force the screen size
    ui.add_head_html("""
        <style>
            html, body { margin: 0; padding: 0; height: 100vh; overflow: hidden; }
            .nicegui-content { padding: 0 !important; margin: 0 !important; }
            .q-message-text, .q-markdown { user-select: text !important; }
        </style>
    """)
    
    # Strip NiceGUI default padding
    ui.query('body').classes('p-0 m-0 overflow-hidden')
    ui.query('.nicegui-content').classes('p-0 m-0')

    # Side Menu
    global drawer, sidebar_content
    with ui.left_drawer(value=True).classes("bg-slate-100") as drawer:
        ui.label("HISTORY").classes("font-bold mb-2")
        sidebar_content = ui.column().classes("w-full")
        refresh_sidebar()

    # Settings
    with ui.dialog() as settings_dialog, ui.card().classes('w-96 p-4'):
        ui.label('Settings').classes('text-xl font-bold mb-2')
        
        # Reasoning Toggle
        global show_reasoning_checkbox
        async def toggle_reasoning(e):
            storage.update_preference("show_reasoning", e.value)
            await refresh_chat_display()
        
        show_reasoning_checkbox = ui.checkbox(
            "Show Reasoning", 
            value=storage.prefs.show_reasoning,
            on_change=toggle_reasoning
        ).classes("mb-4")

        # Working Directories
        ui.label('Working Directories').classes('text-sm font-semibold text-gray-500 mb-1')
        folders_container = ui.column().classes('w-full gap-1 mb-4')
        def refresh_folders():
            folders_container.clear()
            for path in storage.prefs.working_directories:
                with folders_container, ui.row().classes('w-full items-center justify-between bg-gray-100 p-1 rounded px-2'):
                    ui.label(path).classes('text-xs truncate flex-grow')
                    ui.button(icon='delete', on_click=lambda p=path: remove_folder(p)).props('flat round dense color=red size=xs')
        def remove_folder(path):
            storage.prefs.working_directories.remove(path); storage.save(); refresh_folders()
        def add_folder():
            path = new_folder_input.value.strip()
            if path: storage.prefs.working_directories.append(path); storage.save(); new_folder_input.value = ''; refresh_folders()
        
        refresh_folders()
        with ui.row().classes('w-full gap-2 items-center'):
            new_folder_input = ui.input(placeholder='Path...').classes('flex-grow').props('outlined dense')
            ui.button(icon='add', on_click=add_folder).props('flat round color=primary')
            
        ui.button('Close', on_click=settings_dialog.close).classes('w-full mt-4')

    # --- THE STRUCTURE (Fixed Pixel Heights) ---
    with ui.column().classes("w-full h-screen no-wrap gap-0 p-0 m-0"):
        
        # 1. HEADER (Exactly 50px)
        with ui.row().classes("w-full px-4 bg-primary text-white items-center").style("height: 50px;"):
            ui.button(icon="menu", on_click=lambda: drawer.toggle()).props("flat color=white dense")
            ui.label("Simplex AI").classes("font-bold text-lg")
            ui.space()
            ui.button(icon="settings", on_click=settings_dialog.open).props("flat color=white dense")

        # 2. CHAT WINDOW (Calculated height: 100vh - header - footer)
        global scroll_area, chat_content
        scroll_area = ui.scroll_area().classes("w-full bg-white").style("height: calc(100vh - 130px);")
        with scroll_area:
            chat_content = ui.column().classes("w-full p-4 gap-4")

        # 3. INPUT AREA (Exactly 80px)
        with ui.row().classes("w-full px-4 bg-slate-50 items-center border-t shadow-inner").style("height: 80px;"):
            global message_input
            message_input = ui.input(placeholder="Message...").classes("flex-grow").props("outlined bg-color=white")
            message_input.on("keydown.enter", handle_send)
            ui.button(icon="send", on_click=handle_send).props("round flat color=primary size=lg")

if __name__ in {"__main__", "__mp_main__"}:
    init_ui()
    ui.run(title="Simplex AI", native=settings.native_mode, window_size=(1200, 800), reload=False)
