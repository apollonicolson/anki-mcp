"""Change deck tool - Move cards between decks."""
from typing import Any, Callable, Coroutine, Sequence
import logging

from ....handler_registry import register_handler

logger = logging.getLogger(__name__)


# ============================================================================
# HANDLER - Runs on Qt main thread, accesses mw.col
# ============================================================================

def _change_deck_handler(
    card_ids: Sequence[int],
    deck_name: str,
) -> dict[str, Any]:
    """
    Move cards to a different deck.

    This function runs on the Qt MAIN THREAD and has direct access to mw.col.

    Args:
        card_ids: List of card IDs to move
        deck_name: Target deck name

    Returns:
        dict: Result with structure:
            - success (bool): Whether the operation succeeded
            - count (int): Number of cards moved
            - deckName (str): Target deck name
            - message (str): Human-readable result message

    Raises:
        RuntimeError: If collection is not loaded
    """
    from aqt import mw

    if mw.col is None:
        raise RuntimeError("Collection not loaded")

    if not card_ids:
        return {
            "success": False,
            "error": "No card IDs provided",
            "hint": "Use findNotes and get card IDs from notes to move.",
        }

    # Get or create the target deck
    deck_id = mw.col.decks.id(deck_name)
    if deck_id is None:
        return {
            "success": False,
            "error": f"Could not get or create deck: {deck_name}",
        }

    try:
        mw.requireReset()
        result = mw.col.set_deck(card_ids, deck_id)
        count = result.count
    finally:
        if mw.col:
            mw.maybeReset()

    return {
        "success": True,
        "count": count,
        "deckName": deck_name,
        "message": f'Moved {count} cards to deck "{deck_name}"',
    }


# Register handler at import time
register_handler("changeDeck", _change_deck_handler)


# ============================================================================
# MCP TOOL - Runs in background thread, bridges to handler via queue
# ============================================================================

def register_change_deck_tool(
    mcp,  # FastMCP instance
    call_main_thread: Callable[[str, dict], Coroutine[Any, Any, Any]]
) -> None:
    """Register change-deck tool with the MCP server."""

    @mcp.tool(
        description=(
            "Move cards to a different deck. Useful for consolidating decks "
            "or reorganizing your collection. The target deck will be created "
            "if it doesn't exist."
        )
    )
    async def changeDeck(
        card_ids: list[int],
        deck_name: str,
    ) -> dict[str, Any]:
        """Move cards to a different deck.

        Args:
            card_ids: List of card IDs to move
            deck_name: Target deck name (will be created if it doesn't exist)

        Returns:
            Dictionary containing:
            - success (bool): Whether the operation succeeded
            - count (int): Number of cards moved
            - deckName (str): Target deck name
            - message (str): Human-readable result message
            - error (str): Error message (if failed)

        Examples:
            Move specific cards:
            >>> await changeDeck(
            ...     card_ids=[1234567890, 1234567891],
            ...     deck_name="New Deck"
            ... )

        Note:
            To get card IDs, use findNotes to find notes, then use the
            cards_info tool or query by deck.
        """
        arguments = {
            "card_ids": card_ids,
            "deck_name": deck_name,
        }
        return await call_main_thread("changeDeck", arguments)
