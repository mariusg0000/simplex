"""
main.py · Entry Point · Initializes and runs the Simplex AI application.
"""

from nicegui import ui
from src.config import settings
from src.ui.app import init_ui

# Import tool modules to register them with the tool registry
import src.engine.builtin_tools   # noqa: F401
import src.engine.file_search     # noqa: F401
import src.engine.doc_reader      # noqa: F401
import src.engine.file_management # noqa: F401
import src.engine.bash_tool       # noqa: F401
import src.engine.file_open       # noqa: F401

# Disable all tools except bash and open_file
from src.engine.tools import registry
for tool_name in list(registry.tools.keys()):
    if tool_name not in ("bash", "open_file"):
        registry.disable(tool_name)

if __name__ in {"__main__", "__mp_main__"}:
    init_ui()
    ui.run(title="Simplex AI", native=settings.native_mode, window_size=(1200, 800), reload=False)
