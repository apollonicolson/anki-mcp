"""Rename deck tool - MCP tool and handler in one file."""
from typing import Any, Callable, Coroutine
import logging

from ....handler_registry import register_handler

logger = logging.getLogger(__name__)


# ============================================================================
# HANDLER - Runs on Qt main thread, accesses mw.col
# ============================================================================

def _rename_deck_handler(
    deck_name: str,
    new_name: str,
) -> dict[str, Any]:
    """
    Rename an existing deck.

    This function runs on the Qt MAIN THREAD and has direct access to mw.col.

    Args:
        deck_name: Current name of the deck (e.g., "Languages::Japanese")
        new_name: New name for the deck (e.g., "Languages::日本語")

    Returns:
        dict: Result with structure:
            - success (bool): Whether the operation succeeded
            - oldName (str): Previous deck name
            - newName (str): New deck name
            - message (str): Human-readable result message

    Raises:
        RuntimeError: If collection is not loaded
    """
    from aqt import mw

    if mw.col is None:
        raise RuntimeError("Collection not loaded")

    # Get the deck by name
    deck = mw.col.decks.by_name(deck_name)
    if deck is None:
        return {
            "success": False,
            "error": f"Deck not found: {deck_name}",
            "hint": "Use list_decks tool to see available decks.",
        }

    # Check if target name already exists (and is different deck)
    existing = mw.col.decks.by_name(new_name)
    if existing and existing["id"] != deck["id"]:
        return {
            "success": False,
            "error": f"A deck with the name '{new_name}' already exists",
            "hint": "Choose a different name or merge the decks manually.",
        }

    try:
        mw.requireReset()
        mw.col.decks.rename(deck["id"], new_name)
    finally:
        if mw.col:
            mw.maybeReset()

    return {
        "success": True,
        "oldName": deck_name,
        "newName": new_name,
        "message": f'Successfully renamed deck from "{deck_name}" to "{new_name}"',
    }


# Register handler at import time
register_handler("renameDeck", _rename_deck_handler)


# ============================================================================
# MCP TOOL - Runs in background thread, bridges to handler via queue
# ============================================================================

def register_rename_deck_tool(
    mcp,  # FastMCP instance
    call_main_thread: Callable[[str, dict], Coroutine[Any, Any, Any]]
) -> None:
    """Register rename-deck tool with the MCP server."""

    @mcp.tool(
        description=(
            "Rename an existing Anki deck. This also updates all child decks "
            "if the deck has a hierarchical structure (parent::child). "
            "Use this for deck consolidation by flattening hierarchy."
        )
    )
    async def renameDeck(
        deck_name: str,
        new_name: str,
    ) -> dict[str, Any]:
        """Rename an existing Anki deck.

        Args:
            deck_name: Current name of the deck (e.g., "Languages::Japanese::Vocabulary")
            new_name: New name for the deck (e.g., "Japanese::Vocab")

        Returns:
            Dictionary containing:
            - success (bool): Whether the operation succeeded
            - oldName (str): Previous deck name
            - newName (str): New deck name
            - message (str): Human-readable result message
            - error (str): Error message (if failed)
            - hint (str): Helpful hint for resolving errors (if failed)

        Examples:
            Rename a deck:
            >>> await renameDeck(
            ...     deck_name="Old Name",
            ...     new_name="New Name"
            ... )

            Flatten hierarchy:
            >>> await renameDeck(
            ...     deck_name="Languages::Japanese::JLPT::N5",
            ...     new_name="Japanese N5"
            ... )
        """
        arguments = {
            "deck_name": deck_name,
            "new_name": new_name,
        }
        return await call_main_thread("renameDeck", arguments)
