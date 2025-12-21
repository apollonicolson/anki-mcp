"""Get tags tool - List all tags in the collection."""
from typing import Any, Callable, Coroutine
import logging

from ....handler_registry import register_handler

logger = logging.getLogger(__name__)


# ============================================================================
# HANDLER - Runs on Qt main thread, accesses mw.col
# ============================================================================

def _get_tags_handler() -> dict[str, Any]:
    """
    Get all tags in the collection.

    This function runs on the Qt MAIN THREAD and has direct access to mw.col.

    Returns:
        dict: Result with structure:
            - success (bool): Whether the operation succeeded
            - tags (list[str]): List of all tags
            - count (int): Number of tags
            - message (str): Human-readable result message

    Raises:
        RuntimeError: If collection is not loaded
    """
    from aqt import mw

    if mw.col is None:
        raise RuntimeError("Collection not loaded")

    tags = mw.col.tags.all()

    return {
        "success": True,
        "tags": tags,
        "count": len(tags),
        "message": f"Found {len(tags)} tags in the collection",
    }


# Register handler at import time
register_handler("getTags", _get_tags_handler)


# ============================================================================
# MCP TOOL - Runs in background thread, bridges to handler via queue
# ============================================================================

def register_get_tags_tool(
    mcp,  # FastMCP instance
    call_main_thread: Callable[[str, dict], Coroutine[Any, Any, Any]]
) -> None:
    """Register get-tags tool with the MCP server."""

    @mcp.tool(
        description=(
            "Get all tags in the Anki collection. Useful for understanding "
            "your current tag structure before reorganizing."
        )
    )
    async def getTags() -> dict[str, Any]:
        """Get all tags in the collection.

        Returns:
            Dictionary containing:
            - success (bool): Whether the operation succeeded
            - tags (list[str]): List of all tags
            - count (int): Number of tags
            - message (str): Human-readable result message

        Examples:
            Get all tags:
            >>> result = await getTags()
            >>> print(result["tags"])
            ["japanese", "vocabulary", "grammar", "n5", ...]
        """
        return await call_main_thread("getTags", {})
