"""Forget cards tool - Reset cards to new state."""
from typing import Any, Callable, Coroutine, Sequence
import logging

from ....handler_registry import register_handler

logger = logging.getLogger(__name__)


# ============================================================================
# HANDLER - Runs on Qt main thread, accesses mw.col
# ============================================================================

def _forget_cards_handler(
    card_ids: Sequence[int],
    restore_position: bool = False,
    reset_counts: bool = False,
) -> dict[str, Any]:
    """
    Forget cards - reset them to new state.

    This function runs on the Qt MAIN THREAD and has direct access to mw.col.

    Args:
        card_ids: List of card IDs to forget
        restore_position: If True, restore original new card position
        reset_counts: If True, reset review and lapse counts

    Returns:
        dict: Result with structure:
            - success (bool): Whether the operation succeeded
            - count (int): Number of cards reset
            - message (str): Human-readable result message

    Raises:
        RuntimeError: If collection is not loaded
    """
    from aqt import mw
    from anki.scheduler.base import ScheduleCardsAsNew

    if mw.col is None:
        raise RuntimeError("Collection not loaded")

    if not card_ids:
        return {
            "success": False,
            "error": "No card IDs provided",
            "hint": "Use findCards to get card IDs.",
        }

    try:
        mw.requireReset()
        mw.col.sched.schedule_cards_as_new(
            card_ids,
            restore_position=restore_position,
            reset_counts=reset_counts,
        )
    finally:
        if mw.col:
            mw.maybeReset()

    return {
        "success": True,
        "count": len(card_ids),
        "restorePosition": restore_position,
        "resetCounts": reset_counts,
        "message": f"Reset {len(card_ids)} cards to new state",
    }


# Register handler at import time
register_handler("forgetCards", _forget_cards_handler)


# ============================================================================
# MCP TOOL - Runs in background thread, bridges to handler via queue
# ============================================================================

def register_forget_cards_tool(
    mcp,  # FastMCP instance
    call_main_thread: Callable[[str, dict], Coroutine[Any, Any, Any]]
) -> None:
    """Register forget-cards tool with the MCP server."""

    @mcp.tool(
        description=(
            "Forget cards - reset them to new state. This places cards back "
            "in the new queue as if they've never been studied."
        )
    )
    async def forgetCards(
        card_ids: list[int],
        restore_position: bool = False,
        reset_counts: bool = False,
    ) -> dict[str, Any]:
        """Forget cards - reset them to new state.

        Args:
            card_ids: List of card IDs to forget
            restore_position: If True, restore original new card position
                              (useful for re-learning in order)
            reset_counts: If True, also reset review and lapse counts
                          (makes it like the card was never studied)

        Returns:
            Dictionary containing:
            - success (bool): Whether the operation succeeded
            - count (int): Number of cards reset
            - restorePosition (bool): Whether position was restored
            - resetCounts (bool): Whether counts were reset
            - message (str): Human-readable result message
            - error (str): Error message (if failed)

        Examples:
            Forget cards (keep history):
            >>> await forgetCards(card_ids=[1234567890])

            Forget cards completely (reset everything):
            >>> await forgetCards(
            ...     card_ids=[1234567890],
            ...     restore_position=True,
            ...     reset_counts=True
            ... )
        """
        arguments = {
            "card_ids": card_ids,
            "restore_position": restore_position,
            "reset_counts": reset_counts,
        }
        return await call_main_thread("forgetCards", arguments)
