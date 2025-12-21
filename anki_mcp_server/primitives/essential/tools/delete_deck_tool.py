"""Delete deck tool - MCP tool and handler in one file."""
from typing import Any, Callable, Coroutine
import logging

from ....handler_registry import register_handler

logger = logging.getLogger(__name__)


# ============================================================================
# HANDLER - Runs on Qt main thread, accesses mw.col
# ============================================================================

def _delete_deck_handler(
    deck_name: str,
    cards_too: bool = False,
) -> dict[str, Any]:
    """
    Delete an Anki deck.

    This function runs on the Qt MAIN THREAD and has direct access to mw.col.

    Args:
        deck_name: Name of the deck to delete
        cards_too: If True, also delete all cards in the deck.
                   If False (default), cards are moved to the Default deck.

    Returns:
        dict: Result with structure:
            - success (bool): Whether the operation succeeded
            - deckName (str): Name of the deleted deck
            - cardsMoved (bool): Whether cards were moved to Default
            - cardsDeleted (bool): Whether cards were deleted
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

    deck_id = deck["id"]

    # Prevent deletion of the Default deck
    if deck_id == 1:
        return {
            "success": False,
            "error": "Cannot delete the Default deck",
            "hint": "The Default deck is required by Anki and cannot be deleted.",
        }

    # Count cards in the deck (including child decks)
    card_count = len(mw.col.find_cards(f'"deck:{deck_name}"'))

    try:
        mw.requireReset()
        # Remove the deck
        # If cards_too is False, Anki moves cards to Default deck automatically
        mw.col.decks.remove([deck_id])
    finally:
        if mw.col:
            mw.maybeReset()

    if cards_too:
        # Cards were deleted along with the deck
        return {
            "success": True,
            "deckName": deck_name,
            "cardsDeleted": True,
            "cardsMoved": False,
            "cardCount": card_count,
            "message": f'Deleted deck "{deck_name}" and {card_count} cards',
        }
    else:
        return {
            "success": True,
            "deckName": deck_name,
            "cardsDeleted": False,
            "cardsMoved": card_count > 0,
            "cardCount": card_count,
            "message": f'Deleted deck "{deck_name}". {card_count} cards moved to Default deck.' if card_count > 0 else f'Deleted empty deck "{deck_name}"',
        }


# Register handler at import time
register_handler("deleteDeck", _delete_deck_handler)


# ============================================================================
# MCP TOOL - Runs in background thread, bridges to handler via queue
# ============================================================================

def register_delete_deck_tool(
    mcp,  # FastMCP instance
    call_main_thread: Callable[[str, dict], Coroutine[Any, Any, Any]]
) -> None:
    """Register delete-deck tool with the MCP server."""

    @mcp.tool(
        description=(
            "Delete an Anki deck. By default, cards are moved to the Default deck. "
            "Use cards_too=True to permanently delete cards as well. "
            "CRITICAL: This is destructive - only delete decks the user explicitly confirmed."
        )
    )
    async def deleteDeck(
        deck_name: str,
        cards_too: bool = False,
    ) -> dict[str, Any]:
        """Delete an Anki deck.

        Args:
            deck_name: Name of the deck to delete (e.g., "Old Deck")
            cards_too: If True, permanently delete all cards in the deck.
                       If False (default), cards are moved to the Default deck.

        Returns:
            Dictionary containing:
            - success (bool): Whether the operation succeeded
            - deckName (str): Name of the deleted deck
            - cardsDeleted (bool): Whether cards were deleted
            - cardsMoved (bool): Whether cards were moved to Default
            - cardCount (int): Number of cards affected
            - message (str): Human-readable result message
            - error (str): Error message (if failed)

        Examples:
            Delete deck, keep cards:
            >>> await deleteDeck(deck_name="Old Deck")

            Delete deck and cards:
            >>> await deleteDeck(deck_name="Temporary", cards_too=True)
        """
        arguments = {
            "deck_name": deck_name,
            "cards_too": cards_too,
        }
        return await call_main_thread("deleteDeck", arguments)
