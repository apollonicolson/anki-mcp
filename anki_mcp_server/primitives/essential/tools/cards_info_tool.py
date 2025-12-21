"""Cards info tool - Get detailed information about cards."""
from typing import Any, Callable, Coroutine, Sequence
import logging

from ....handler_registry import register_handler

logger = logging.getLogger(__name__)


# Card type constants
CARD_TYPE_NEW = 0
CARD_TYPE_LRN = 1
CARD_TYPE_REV = 2
CARD_TYPE_RELEARNING = 3

CARD_TYPE_NAMES = {
    0: "new",
    1: "learning",
    2: "review",
    3: "relearning",
}

# Queue constants
QUEUE_TYPE_MANUALLY_BURIED = -3
QUEUE_TYPE_SIBLING_BURIED = -2
QUEUE_TYPE_SUSPENDED = -1
QUEUE_TYPE_NEW = 0
QUEUE_TYPE_LRN = 1
QUEUE_TYPE_REV = 2
QUEUE_TYPE_DAY_LEARN_RELEARN = 3
QUEUE_TYPE_PREVIEW = 4

QUEUE_NAMES = {
    -3: "manually buried",
    -2: "sibling buried",
    -1: "suspended",
    0: "new",
    1: "learning",
    2: "review",
    3: "day learn relearn",
    4: "preview",
}


# ============================================================================
# HANDLER - Runs on Qt main thread, accesses mw.col
# ============================================================================

def _cards_info_handler(
    card_ids: Sequence[int],
) -> dict[str, Any]:
    """
    Get detailed information about cards.

    This function runs on the Qt MAIN THREAD and has direct access to mw.col.

    Args:
        card_ids: List of card IDs to get info for

    Returns:
        dict: Result with structure:
            - success (bool): Whether the operation succeeded
            - cards (list): List of card info dictionaries
            - count (int): Number of cards returned
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
            "hint": "Use findCards or findNotes to get card IDs.",
        }

    cards = []
    for card_id in card_ids:
        try:
            card = mw.col.get_card(card_id)
            note = card.note()
            deck = mw.col.decks.get(card.did)
            model = card.note_type()

            card_info = {
                "cardId": card.id,
                "noteId": card.nid,
                "deckId": card.did,
                "deckName": deck["name"] if deck else "Unknown",
                "modelId": note.mid,
                "modelName": model["name"] if model else "Unknown",
                "ord": card.ord,
                "type": card.type,
                "typeName": CARD_TYPE_NAMES.get(card.type, "unknown"),
                "queue": card.queue,
                "queueName": QUEUE_NAMES.get(card.queue, "unknown"),
                "due": card.due,
                "interval": card.ivl,
                "factor": card.factor,
                "reps": card.reps,
                "lapses": card.lapses,
                "left": card.left,
                "flags": card.flags,
                "question": card.question(),
                "answer": card.answer(),
            }
            cards.append(card_info)
        except Exception as e:
            logger.warning(f"Failed to get card info for {card_id}: {e}")
            cards.append({
                "cardId": card_id,
                "error": str(e),
            })

    return {
        "success": True,
        "cards": cards,
        "count": len(cards),
        "message": f"Retrieved info for {len(cards)} cards",
    }


# Register handler at import time
register_handler("cardsInfo", _cards_info_handler)


# ============================================================================
# MCP TOOL - Runs in background thread, bridges to handler via queue
# ============================================================================

def register_cards_info_tool(
    mcp,  # FastMCP instance
    call_main_thread: Callable[[str, dict], Coroutine[Any, Any, Any]]
) -> None:
    """Register cards-info tool with the MCP server."""

    @mcp.tool(
        description=(
            "Get detailed information about specific cards including scheduling "
            "info, deck, model, question/answer content, and more."
        )
    )
    async def cardsInfo(
        card_ids: list[int],
    ) -> dict[str, Any]:
        """Get detailed information about cards.

        Args:
            card_ids: List of card IDs to get info for

        Returns:
            Dictionary containing:
            - success (bool): Whether the operation succeeded
            - cards (list): List of card info dictionaries with:
                - cardId, noteId, deckId, deckName
                - modelId, modelName, ord
                - type, typeName (new/learning/review/relearning)
                - queue, queueName (suspended/buried/new/learning/review)
                - due, interval, factor, reps, lapses
                - flags, question, answer
            - count (int): Number of cards returned
            - message (str): Human-readable result message
            - error (str): Error message (if failed)

        Examples:
            Get card info:
            >>> result = await cardsInfo(card_ids=[1234567890])
            >>> print(result["cards"][0]["deckName"])
            "Japanese::Vocabulary"
        """
        arguments = {"card_ids": card_ids}
        return await call_main_thread("cardsInfo", arguments)
