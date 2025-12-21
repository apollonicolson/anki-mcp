"""Get collection stats tool - Get statistics about the collection."""
from typing import Any, Callable, Coroutine, Optional
import logging

from ....handler_registry import register_handler

logger = logging.getLogger(__name__)


# ============================================================================
# HANDLER - Runs on Qt main thread, accesses mw.col
# ============================================================================

def _get_collection_stats_handler(
    deck_name: Optional[str] = None,
) -> dict[str, Any]:
    """
    Get statistics about the collection or a specific deck.

    This function runs on the Qt MAIN THREAD and has direct access to mw.col.

    Args:
        deck_name: Optional deck name to get stats for. If None, gets global stats.

    Returns:
        dict: Result with structure:
            - success (bool): Whether the operation succeeded
            - stats (dict): Statistics including card counts, due counts, etc.
            - message (str): Human-readable result message

    Raises:
        RuntimeError: If collection is not loaded
    """
    from aqt import mw

    if mw.col is None:
        raise RuntimeError("Collection not loaded")

    # Get deck ID if deck name provided
    deck_id = None
    if deck_name:
        deck = mw.col.decks.by_name(deck_name)
        if deck is None:
            return {
                "success": False,
                "error": f"Deck not found: {deck_name}",
                "hint": "Use list_decks to see available decks.",
            }
        deck_id = deck["id"]

    # Build query prefix
    query_prefix = f'"deck:{deck_name}" ' if deck_name else ""

    # Get various counts
    total_cards = len(mw.col.find_cards(f"{query_prefix}"))
    new_cards = len(mw.col.find_cards(f"{query_prefix}is:new"))
    learning_cards = len(mw.col.find_cards(f"{query_prefix}is:learn"))
    review_cards = len(mw.col.find_cards(f"{query_prefix}is:review"))
    due_cards = len(mw.col.find_cards(f"{query_prefix}is:due"))
    suspended_cards = len(mw.col.find_cards(f"{query_prefix}is:suspended"))
    buried_cards = len(mw.col.find_cards(f"{query_prefix}is:buried"))

    # Get note count
    total_notes = len(mw.col.find_notes(f"{query_prefix}"))

    stats = {
        "totalCards": total_cards,
        "totalNotes": total_notes,
        "newCards": new_cards,
        "learningCards": learning_cards,
        "reviewCards": review_cards,
        "dueCards": due_cards,
        "suspendedCards": suspended_cards,
        "buriedCards": buried_cards,
    }

    if deck_name:
        stats["deckName"] = deck_name

    return {
        "success": True,
        "stats": stats,
        "message": f"Statistics for {'deck ' + deck_name if deck_name else 'entire collection'}",
    }


# Register handler at import time
register_handler("getCollectionStats", _get_collection_stats_handler)


# ============================================================================
# MCP TOOL - Runs in background thread, bridges to handler via queue
# ============================================================================

def register_get_collection_stats_tool(
    mcp,  # FastMCP instance
    call_main_thread: Callable[[str, dict], Coroutine[Any, Any, Any]]
) -> None:
    """Register get-collection-stats tool with the MCP server."""

    @mcp.tool(
        description=(
            "Get statistics about your Anki collection or a specific deck. "
            "Returns card counts, due counts, and more."
        )
    )
    async def getCollectionStats(
        deck_name: Optional[str] = None,
    ) -> dict[str, Any]:
        """Get statistics about the collection or a specific deck.

        Args:
            deck_name: Optional deck name to get stats for.
                       If not provided, returns stats for the entire collection.

        Returns:
            Dictionary containing:
            - success (bool): Whether the operation succeeded
            - stats (dict): Statistics including:
                - totalCards: Total number of cards
                - totalNotes: Total number of notes
                - newCards: Cards that haven't been studied
                - learningCards: Cards currently being learned
                - reviewCards: Cards in review state
                - dueCards: Cards due for review
                - suspendedCards: Suspended cards
                - buriedCards: Buried cards
                - deckName (if deck specified)
            - message (str): Human-readable result message
            - error (str): Error message (if failed)

        Examples:
            Get collection stats:
            >>> result = await getCollectionStats()
            >>> print(result["stats"]["totalCards"])
            5000

            Get deck stats:
            >>> result = await getCollectionStats(deck_name="Japanese")
            >>> print(result["stats"]["dueCards"])
            42
        """
        arguments = {"deck_name": deck_name}
        return await call_main_thread("getCollectionStats", arguments)
