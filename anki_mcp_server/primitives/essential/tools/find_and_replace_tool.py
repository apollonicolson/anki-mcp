"""Find and replace tool - Find and replace text in note fields."""
from typing import Any, Callable, Coroutine, Optional, Sequence
import logging

from ....handler_registry import register_handler

logger = logging.getLogger(__name__)


# ============================================================================
# HANDLER - Runs on Qt main thread, accesses mw.col
# ============================================================================

def _find_and_replace_handler(
    note_ids: Sequence[int],
    search: str,
    replacement: str,
    field_name: Optional[str] = None,
    regex: bool = False,
    match_case: bool = False,
) -> dict[str, Any]:
    """
    Find and replace text in note fields.

    This function runs on the Qt MAIN THREAD and has direct access to mw.col.

    Args:
        note_ids: List of note IDs to process
        search: Text or regex pattern to search for
        replacement: Replacement text
        field_name: Optional specific field to search in (all fields if None)
        regex: If True, treat search as a regular expression
        match_case: If True, search is case-sensitive

    Returns:
        dict: Result with structure:
            - success (bool): Whether the operation succeeded
            - count (int): Number of notes modified
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
            "hint": "Use findNotes to get note IDs.",
        }

    if not search:
        return {
            "success": False,
            "error": "No search pattern provided",
        }

    try:
        mw.requireReset()
        result = mw.col.find_and_replace(
            note_ids=note_ids,
            search=search,
            replacement=replacement,
            regex=regex,
            match_case=match_case,
            field_name=field_name,
        )
        count = result.count
    except Exception as e:
        return {
            "success": False,
            "error": f"Find and replace failed: {str(e)}",
            "hint": "Check your search pattern, especially if using regex.",
        }
    finally:
        if mw.col:
            mw.maybeReset()

    return {
        "success": True,
        "count": count,
        "search": search,
        "replacement": replacement,
        "regex": regex,
        "matchCase": match_case,
        "fieldName": field_name,
        "message": f"Replaced '{search}' with '{replacement}' in {count} notes",
    }


# Register handler at import time
register_handler("findAndReplace", _find_and_replace_handler)


# ============================================================================
# MCP TOOL - Runs in background thread, bridges to handler via queue
# ============================================================================

def register_find_and_replace_tool(
    mcp,  # FastMCP instance
    call_main_thread: Callable[[str, dict], Coroutine[Any, Any, Any]]
) -> None:
    """Register find-and-replace tool with the MCP server."""

    @mcp.tool(
        description=(
            "Find and replace text in note fields. Supports plain text or regex. "
            "Useful for bulk corrections or formatting changes."
        )
    )
    async def findAndReplace(
        note_ids: list[int],
        search: str,
        replacement: str,
        field_name: Optional[str] = None,
        regex: bool = False,
        match_case: bool = False,
    ) -> dict[str, Any]:
        """Find and replace text in note fields.

        Args:
            note_ids: List of note IDs to process
            search: Text or regex pattern to search for
            replacement: Replacement text (can use regex groups like \\1)
            field_name: Optional specific field to search in.
                        If not provided, searches all fields.
            regex: If True, treat search as a regular expression
            match_case: If True, search is case-sensitive

        Returns:
            Dictionary containing:
            - success (bool): Whether the operation succeeded
            - count (int): Number of notes modified
            - search (str): The search pattern used
            - replacement (str): The replacement text
            - regex (bool): Whether regex was used
            - matchCase (bool): Whether case-sensitive
            - fieldName (str|null): Field that was searched
            - message (str): Human-readable result message
            - error (str): Error message (if failed)

        Examples:
            Simple replacement:
            >>> await findAndReplace(
            ...     note_ids=[1234567890],
            ...     search="colour",
            ...     replacement="color"
            ... )

            Regex replacement:
            >>> await findAndReplace(
            ...     note_ids=[1234567890],
            ...     search="<br\\s*/?>",
            ...     replacement="<br>",
            ...     regex=True
            ... )

            Field-specific replacement:
            >>> await findAndReplace(
            ...     note_ids=[1234567890],
            ...     search="old",
            ...     replacement="new",
            ...     field_name="Front"
            ... )
        """
        arguments = {
            "note_ids": note_ids,
            "search": search,
            "replacement": replacement,
            "field_name": field_name,
            "regex": regex,
            "match_case": match_case,
        }
        return await call_main_thread("findAndReplace", arguments)
