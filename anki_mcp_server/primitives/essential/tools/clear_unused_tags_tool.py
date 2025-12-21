"""Clear unused tags tool - Remove orphaned tags from the collection."""
from typing import Any, Callable, Coroutine
import logging

from ....handler_registry import register_handler

logger = logging.getLogger(__name__)


# ============================================================================
# HANDLER - Runs on Qt main thread, accesses mw.col
# ============================================================================

def _clear_unused_tags_handler() -> dict[str, Any]:
    """
    Clear unused tags from the collection.

    This function runs on the Qt MAIN THREAD and has direct access to mw.col.

    Returns:
        dict: Result with structure:
            - success (bool): Whether the operation succeeded
            - count (int): Number of tags removed
            - message (str): Human-readable result message

    Raises:
        RuntimeError: If collection is not loaded
    """
    from aqt import mw

    if mw.col is None:
        raise RuntimeError("Collection not loaded")

    try:
        mw.requireReset()
        result = mw.col.tags.clear_unused_tags()
        count = result.count
    finally:
        if mw.col:
            mw.maybeReset()

    return {
        "success": True,
        "count": count,
        "message": f"Removed {count} unused tags" if count > 0 else "No unused tags found",
    }


# Register handler at import time
register_handler("clearUnusedTags", _clear_unused_tags_handler)


# ============================================================================
# MCP TOOL - Runs in background thread, bridges to handler via queue
# ============================================================================

def register_clear_unused_tags_tool(
    mcp,  # FastMCP instance
    call_main_thread: Callable[[str, dict], Coroutine[Any, Any, Any]]
) -> None:
    """Register clear-unused-tags tool with the MCP server."""

    @mcp.tool(
        description=(
            "Remove unused (orphaned) tags from the collection. These are tags "
            "that exist in the tag list but are not used by any notes."
        )
    )
    async def clearUnusedTags() -> dict[str, Any]:
        """Remove unused tags from the collection.

        Returns:
            Dictionary containing:
            - success (bool): Whether the operation succeeded
            - count (int): Number of tags removed
            - message (str): Human-readable result message

        Examples:
            Clear unused tags:
            >>> result = await clearUnusedTags()
            >>> print(result["message"])
            "Removed 15 unused tags"
        """
        return await call_main_thread("clearUnusedTags", {})
