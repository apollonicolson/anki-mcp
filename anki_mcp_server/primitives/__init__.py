# primitives/__init__.py
"""MCP primitives module - tools, prompts, and resources."""

from ..tools import register_tools
from ..prompts import register_all_prompts
from ..resources import register_all_resources


def register_all_tools(mcp, call_main_thread):
    """Register all tools with MCP server."""
    register_tools(mcp, call_main_thread)


__all__ = ["register_all_tools", "register_all_resources", "register_all_prompts"]
