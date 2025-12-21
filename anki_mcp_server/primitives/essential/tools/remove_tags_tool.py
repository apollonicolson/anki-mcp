"""Remove tags tool - Bulk remove tags from notes."""
from typing import Any, Callable, Coroutine, Optional, Sequence
import logging

from ....handler_registry import register_handler

logger = logging.getLogger(__name__)


# ============================================================================
# HANDLER - Runs on Qt main thread, accesses mw.col
# ============================================================================

def _remove_tags_handler(
    note_ids: Sequence[int],
    tags: str,
) -> dict[str, Any]:
    """
    Remove tags from notes in bulk.

    This function runs on the Qt MAIN THREAD and has direct access to mw.col.

    Args:
        note_ids: List of note IDs to remove tags from
        tags: Space-separated tags to remove (e.g., "old obsolete")

    Returns:
        dict: Result with structure:
            - success (bool): Whether the operation succeeded
            - count (int): Number of notes modified
            - tags (str): Tags that were removed
            - message (str): Human-readable result message

    Raises:
        RuntimeError: If collection is not loaded
    """
    from aqt import mw

    if mw.col is None:
        raise RuntimeError("Collection not loaded")

    if not note_ids:
        return {
            "success": False,
            "error": "No note IDs provided",
            "hint": "Use findNotes to get note IDs first.",
        }

    if not tags or not tags.strip():
        return {
            "success": False,
            "error": "No tags provided",
            "hint": "Provide space-separated tags to remove.",
        }

    try:
        mw.requireReset()
        result = mw.col.tags.bulk_remove(note_ids, tags)
        count = result.count
    finally:
        if mw.col:
            mw.maybeReset()

    return {
        "success": True,
        "count": count,
        "tags": tags,
        "noteCount": len(note_ids),
        "message": f'Removed tags "{tags}" from {count} notes',
    }


# Register handler at import time
register_handler("removeTags", _remove_tags_handler)


# ============================================================================
# MCP TOOL - Runs in background thread, bridges to handler via queue
# ============================================================================

def register_remove_tags_tool(
    mcp,  # FastMCP instance
    call_main_thread: Callable[[str, dict], Coroutine[Any, Any, Any]]
) -> None:
    """Register remove-tags tool with the MCP server."""

    @mcp.tool(
        description=(
            "Remove tags from multiple notes at once. Useful for cleaning up "
            "or reorganizing your tag structure."
        )
    )
    async def removeTags(
        note_ids: list[int],
        tags: str,
    ) -> dict[str, Any]:
        """Remove tags from notes in bulk.

        Args:
            note_ids: List of note IDs to remove tags from
            tags: Space-separated tags to remove (e.g., "old obsolete")

        Returns:
            Dictionary containing:
            - success (bool): Whether the operation succeeded
            - count (int): Number of notes modified
            - tags (str): Tags that were removed
            - noteCount (int): Total notes provided
            - message (str): Human-readable result message
            - error (str): Error message (if failed)

        Examples:
            Remove single tag:
            >>> await removeTags(
            ...     note_ids=[1234567890, 1234567891],
            ...     tags="deprecated"
            ... )

            Remove multiple tags:
            >>> await removeTags(
            ...     note_ids=[1234567890],
            ...     tags="old temporary test"
            ... )
        """
        arguments = {
            "note_ids": note_ids,
            "tags": tags,
        }
        return await call_main_thread("removeTags", arguments)
