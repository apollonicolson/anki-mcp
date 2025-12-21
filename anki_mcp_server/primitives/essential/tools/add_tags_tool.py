"""Add tags tool - Bulk add tags to notes."""
from typing import Any, Callable, Coroutine, Sequence
import logging

from ....handler_registry import register_handler

logger = logging.getLogger(__name__)


# ============================================================================
# HANDLER - Runs on Qt main thread, accesses mw.col
# ============================================================================

def _add_tags_handler(
    note_ids: Sequence[int],
    tags: str,
) -> dict[str, Any]:
    """
    Add tags to notes in bulk.

    This function runs on the Qt MAIN THREAD and has direct access to mw.col.

    Args:
        note_ids: List of note IDs to add tags to
        tags: Space-separated tags to add (e.g., "vocab important review")

    Returns:
        dict: Result with structure:
            - success (bool): Whether the operation succeeded
            - count (int): Number of notes modified
            - tags (str): Tags that were added
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
            "hint": "Provide space-separated tags to add.",
        }

    try:
        mw.requireReset()
        result = mw.col.tags.bulk_add(note_ids, tags)
        count = result.count
    finally:
        if mw.col:
            mw.maybeReset()

    return {
        "success": True,
        "count": count,
        "tags": tags,
        "noteCount": len(note_ids),
        "message": f'Added tags "{tags}" to {count} notes',
    }


# Register handler at import time
register_handler("addTags", _add_tags_handler)


# ============================================================================
# MCP TOOL - Runs in background thread, bridges to handler via queue
# ============================================================================

def register_add_tags_tool(
    mcp,  # FastMCP instance
    call_main_thread: Callable[[str, dict], Coroutine[Any, Any, Any]]
) -> None:
    """Register add-tags tool with the MCP server."""

    @mcp.tool(
        description=(
            "Add tags to multiple notes at once. Useful for organizing notes "
            "before deck consolidation - convert deck structure to tags."
        )
    )
    async def addTags(
        note_ids: list[int],
        tags: str,
    ) -> dict[str, Any]:
        """Add tags to notes in bulk.

        Args:
            note_ids: List of note IDs to add tags to
            tags: Space-separated tags to add (e.g., "vocab important")

        Returns:
            Dictionary containing:
            - success (bool): Whether the operation succeeded
            - count (int): Number of notes modified
            - tags (str): Tags that were added
            - noteCount (int): Total notes provided
            - message (str): Human-readable result message
            - error (str): Error message (if failed)

        Examples:
            Add single tag:
            >>> await addTags(
            ...     note_ids=[1234567890, 1234567891],
            ...     tags="important"
            ... )

            Add multiple tags:
            >>> await addTags(
            ...     note_ids=[1234567890],
            ...     tags="japanese vocabulary n5"
            ... )
        """
        arguments = {
            "note_ids": note_ids,
            "tags": tags,
        }
        return await call_main_thread("addTags", arguments)
