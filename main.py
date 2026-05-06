"""
main.py · Main Entry Point · Initializes and runs the NiceGUI application.
"""

import asyncio
from nicegui import ui
from src.engine.chat import stream_chat
from src.config import settings

from src.storage import storage
from src.engine.tools import tool

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
messages = [{"role": "system", "content": settings.system_prompt}]
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
    ui.query('body').classes('bg-slate-50')

    with ui.column().classes("w-full max-w-3xl mx-auto p-4 h-screen items-stretch"):
        with ui.row().classes("w-full items-center justify-between mb-4"):
            with ui.row().classes("items-center gap-4"):
                ui.label("Simplex AI").classes("text-3xl font-bold text-primary")
                ui.badge("v1.0.0 (NiceGUI Native)").classes("p-2")
            
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
