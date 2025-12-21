"""MCP Tools - Modular tool definitions.

Drop a .py file in this directory to add tools. Auto-discovered on import.
"""
from pathlib import Path
import importlib

# Auto-import all .py files to trigger T() registrations
for _file in Path(__file__).parent.glob("*.py"):
    if _file.stem not in ("__init__", "base"):
        importlib.import_module(f".{_file.stem}", __package__)

# Export the registration function
from .base import register_tools, ToolError, col

__all__ = ["register_tools", "ToolError", "col"]
