"""Update note tags tool - Set tags for a specific note."""
from typing import Any, Callable, Coroutine, Sequence
import logging

from ....handler_registry import register_handler

logger = logging.getLogger(__name__)


# ============================================================================
# HANDLER - Runs on Qt main thread, accesses mw.col
# ============================================================================

def _update_note_tags_handler(
    note_id: int,
    tags: Sequence[str],
) -> dict[str, Any]:
    """
    Set the tags for a specific note (replaces existing tags).

    This function runs on the Qt MAIN THREAD and has direct access to mw.col.

    Args:
        note_id: ID of the note to update
        tags: List of tags to set (replaces all existing tags)

    Returns:
        dict: Result with structure:
            - success (bool): Whether the operation succeeded
            - noteId (int): The note ID
            - tags (list): The new tags
            - message (str): Human-readable result message

    Raises:
        RuntimeError: If collection is not loaded
    """
    from aqt import mw

    if mw.col is None:
        raise RuntimeError("Collection not loaded")

    try:
        note = mw.col.get_note(note_id)
    except Exception as e:
        return {
            "success": False,
            "error": f"Note not found: {note_id}",
            "hint": "Use findNotes to get valid note IDs.",
        }

    try:
        mw.requireReset()
        note.tags = list(tags)
        mw.col.update_note(note)
    finally:
        if mw.col:
            mw.maybeReset()

    return {
        "success": True,
        "noteId": note_id,
        "tags": list(tags),
        "message": f"Updated tags for note {note_id}",
    }


# Register handler at import time
register_handler("updateNoteTags", _update_note_tags_handler)


# ============================================================================
# MCP TOOL - Runs in background thread, bridges to handler via queue
# ============================================================================

def register_update_note_tags_tool(
    mcp,  # FastMCP instance
    call_main_thread: Callable[[str, dict], Coroutine[Any, Any, Any]]
) -> None:
    """Register update-note-tags tool with the MCP server."""

    @mcp.tool(
        description=(
            "Set the tags for a specific note. This replaces all existing tags. "
            "Use addTags/removeTags for bulk operations or to add/remove specific tags."
        )
    )
    async def updateNoteTags(
        note_id: int,
        tags: list[str],
    ) -> dict[str, Any]:
        """Set the tags for a specific note.

        Args:
            note_id: ID of the note to update
            tags: List of tags to set (replaces ALL existing tags)

        Returns:
            Dictionary containing:
            - success (bool): Whether the operation succeeded
            - noteId (int): The note ID
            - tags (list): The new tags
            - message (str): Human-readable result message
            - error (str): Error message (if failed)

        Examples:
            Set tags for a note:
            >>> await updateNoteTags(
            ...     note_id=1234567890,
            ...     tags=["japanese", "vocabulary", "n5"]
            ... )

            Clear all tags:
            >>> await updateNoteTags(note_id=1234567890, tags=[])
        """
        arguments = {
            "note_id": note_id,
            "tags": tags,
        }
        return await call_main_thread("updateNoteTags", arguments)
