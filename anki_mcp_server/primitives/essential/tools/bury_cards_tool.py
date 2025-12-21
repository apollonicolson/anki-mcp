"""Bury cards tool - Bury or unbury cards."""
from typing import Any, Callable, Coroutine, Sequence
import logging

from ....handler_registry import register_handler

logger = logging.getLogger(__name__)


# ============================================================================
# HANDLER - Runs on Qt main thread, accesses mw.col
# ============================================================================

def _bury_cards_handler(
    card_ids: Sequence[int],
) -> dict[str, Any]:
    """
    Bury cards until the next day.

    This function runs on the Qt MAIN THREAD and has direct access to mw.col.

    Args:
        card_ids: List of card IDs to bury

    Returns:
        dict: Result with structure:
            - success (bool): Whether the operation succeeded
            - count (int): Number of cards buried
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

    try:
        mw.requireReset()
        result = mw.col.sched.bury_cards(card_ids, manual=True)
        count = result.count
    finally:
        if mw.col:
            mw.maybeReset()

    return {
        "success": True,
        "count": count,
        "message": f"Buried {count} cards until next day",
    }


def _unbury_cards_handler(
    card_ids: Sequence[int],
) -> dict[str, Any]:
    """
    Unbury cards.

    This function runs on the Qt MAIN THREAD and has direct access to mw.col.

    Args:
        card_ids: List of card IDs to unbury

    Returns:
        dict: Result with structure:
            - success (bool): Whether the operation succeeded
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
            "hint": "Use findCards with 'is:buried' to find buried cards.",
        }

    try:
        mw.requireReset()
        mw.col.sched.unbury_cards(card_ids)
    finally:
        if mw.col:
            mw.maybeReset()

    return {
        "success": True,
        "count": len(card_ids),
        "message": f"Unburied {len(card_ids)} cards",
    }


# Register handlers at import time
register_handler("buryCards", _bury_cards_handler)
register_handler("unburyCards", _unbury_cards_handler)


# ============================================================================
# MCP TOOLS - Run in background thread, bridge to handler via queue
# ============================================================================

def register_bury_cards_tool(
    mcp,  # FastMCP instance
    call_main_thread: Callable[[str, dict], Coroutine[Any, Any, Any]]
) -> None:
    """Register bury/unbury cards tools with the MCP server."""

    @mcp.tool(
        description=(
            "Bury cards until the next day. Buried cards won't appear in "
            "today's study sessions but will automatically unbury tomorrow."
        )
    )
    async def buryCards(
        card_ids: list[int],
    ) -> dict[str, Any]:
        """Bury cards until the next day.

        Args:
            card_ids: List of card IDs to bury

        Returns:
            Dictionary containing:
            - success (bool): Whether the operation succeeded
            - count (int): Number of cards buried
            - message (str): Human-readable result message
            - error (str): Error message (if failed)

        Examples:
            Bury specific cards:
            >>> await buryCards(card_ids=[1234567890, 1234567891])
        """
        arguments = {"card_ids": card_ids}
        return await call_main_thread("buryCards", arguments)

    @mcp.tool(
        description=(
            "Unbury cards to make them available for study again today."
        )
    )
    async def unburyCards(
        card_ids: list[int],
    ) -> dict[str, Any]:
        """Unbury cards.

        Args:
            card_ids: List of card IDs to unbury

        Returns:
            Dictionary containing:
            - success (bool): Whether the operation succeeded
            - count (int): Number of cards unburied
            - message (str): Human-readable result message
            - error (str): Error message (if failed)

        Examples:
            Unbury specific cards:
            >>> await unburyCards(card_ids=[1234567890, 1234567891])
        """
        arguments = {"card_ids": card_ids}
        return await call_main_thread("unburyCards", arguments)
