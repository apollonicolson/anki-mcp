"""Find cards tool - Search for cards using Anki query syntax."""
from typing import Any, Callable, Coroutine, Optional
import logging

from ....handler_registry import register_handler

logger = logging.getLogger(__name__)


# ============================================================================
# HANDLER - Runs on Qt main thread, accesses mw.col
# ============================================================================

def _find_cards_handler(
    query: str,
) -> dict[str, Any]:
    """
    Search for cards using Anki query syntax.

    This function runs on the Qt MAIN THREAD and has direct access to mw.col.

    Args:
        query: Anki search query (e.g., "deck:Japanese is:due")

    Returns:
        dict: Result with structure:
            - success (bool): Whether the operation succeeded
            - cardIds (list[int]): List of matching card IDs
            - count (int): Number of cards found
            - query (str): The query that was executed
            - message (str): Human-readable result message

    Raises:
        RuntimeError: If collection is not loaded
    """
    from aqt import mw

    if mw.col is None:
        raise RuntimeError("Collection not loaded")

    if not query or not query.strip():
        return {
            "success": False,
            "error": "No query provided",
            "hint": "Provide an Anki search query like 'deck:Japanese' or 'is:due'",
        }

    try:
        card_ids = list(mw.col.find_cards(query))
    except Exception as e:
        return {
            "success": False,
            "error": f"Search failed: {str(e)}",
            "query": query,
            "hint": "Check the query syntax. Examples: 'deck:Name', 'tag:word', 'is:due', 'is:suspended'",
        }

    return {
        "success": True,
        "cardIds": card_ids,
        "count": len(card_ids),
        "query": query,
        "message": f"Found {len(card_ids)} cards matching '{query}'",
    }


# Register handler at import time
register_handler("findCards", _find_cards_handler)


# ============================================================================
# MCP TOOL - Runs in background thread, bridges to handler via queue
# ============================================================================

def register_find_cards_tool(
    mcp,  # FastMCP instance
    call_main_thread: Callable[[str, dict], Coroutine[Any, Any, Any]]
) -> None:
    """Register find-cards tool with the MCP server."""

    @mcp.tool(
        description=(
            "Search for cards using Anki query syntax. Returns card IDs that can be "
            "used with other card operations like suspend, bury, changeDeck, etc. "
            "Unlike findNotes, this returns card IDs (a note can have multiple cards)."
        )
    )
    async def findCards(
        query: str,
    ) -> dict[str, Any]:
        """Search for cards using Anki query syntax.

        Args:
            query: Anki search query. Examples:
                   - "deck:Japanese" - cards in Japanese deck
                   - "is:due" - cards due for review
                   - "is:suspended" - suspended cards
                   - "is:buried" - buried cards
                   - "is:new" - new cards
                   - "is:learn" - cards in learning
                   - "is:review" - review cards
                   - "flag:1" - cards with red flag
                   - "tag:vocab" - cards from notes with tag
                   - "prop:due>7" - cards due in more than 7 days
                   - "prop:ivl>=30" - cards with interval >= 30 days
                   - "added:7" - cards added in last 7 days
                   - "rated:1" - cards rated today
                   - Combined: "deck:Japanese is:due -is:suspended"

        Returns:
            Dictionary containing:
            - success (bool): Whether the operation succeeded
            - cardIds (list[int]): List of matching card IDs
            - count (int): Number of cards found
            - query (str): The query that was executed
            - message (str): Human-readable result message
            - error (str): Error message (if failed)

        Examples:
            Find due cards in a deck:
            >>> result = await findCards(query="deck:Japanese is:due")
            >>> print(result["count"])
            42

            Find suspended cards:
            >>> result = await findCards(query="is:suspended")

            Find cards with interval over 30 days:
            >>> result = await findCards(query="prop:ivl>=30")
        """
        arguments = {"query": query}
        return await call_main_thread("findCards", arguments)
