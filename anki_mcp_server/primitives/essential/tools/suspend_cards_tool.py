"""Suspend cards tool - Suspend or unsuspend cards."""
from typing import Any, Callable, Coroutine, Sequence
import logging

from ....handler_registry import register_handler

logger = logging.getLogger(__name__)


# ============================================================================
# HANDLER - Runs on Qt main thread, accesses mw.col
# ============================================================================

def _suspend_cards_handler(
    card_ids: Sequence[int],
) -> dict[str, Any]:
    """
    Suspend cards.

    This function runs on the Qt MAIN THREAD and has direct access to mw.col.

    Args:
        card_ids: List of card IDs to suspend

    Returns:
        dict: Result with structure:
            - success (bool): Whether the operation succeeded
            - count (int): Number of cards suspended
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
        result = mw.col.sched.suspend_cards(card_ids)
        count = result.count
    finally:
        if mw.col:
            mw.maybeReset()

    return {
        "success": True,
        "count": count,
        "message": f"Suspended {count} cards",
    }


def _unsuspend_cards_handler(
    card_ids: Sequence[int],
) -> dict[str, Any]:
    """
    Unsuspend cards.

    This function runs on the Qt MAIN THREAD and has direct access to mw.col.

    Args:
        card_ids: List of card IDs to unsuspend

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
            "hint": "Use findCards with 'is:suspended' to find suspended cards.",
        }

    try:
        mw.requireReset()
        mw.col.sched.unsuspend_cards(card_ids)
    finally:
        if mw.col:
            mw.maybeReset()

    return {
        "success": True,
        "count": len(card_ids),
        "message": f"Unsuspended {len(card_ids)} cards",
    }


# Register handlers at import time
register_handler("suspendCards", _suspend_cards_handler)
register_handler("unsuspendCards", _unsuspend_cards_handler)


# ============================================================================
# MCP TOOLS - Run in background thread, bridge to handler via queue
# ============================================================================

def register_suspend_cards_tool(
    mcp,  # FastMCP instance
    call_main_thread: Callable[[str, dict], Coroutine[Any, Any, Any]]
) -> None:
    """Register suspend/unsuspend cards tools with the MCP server."""

    @mcp.tool(
        description=(
            "Suspend cards to exclude them from review. Suspended cards won't "
            "appear in study sessions until unsuspended."
        )
    )
    async def suspendCards(
        card_ids: list[int],
    ) -> dict[str, Any]:
        """Suspend cards.

        Args:
            card_ids: List of card IDs to suspend

        Returns:
            Dictionary containing:
            - success (bool): Whether the operation succeeded
            - count (int): Number of cards suspended
            - message (str): Human-readable result message
            - error (str): Error message (if failed)

        Examples:
            Suspend specific cards:
            >>> await suspendCards(card_ids=[1234567890, 1234567891])
        """
        arguments = {"card_ids": card_ids}
        return await call_main_thread("suspendCards", arguments)

    @mcp.tool(
        description=(
            "Unsuspend cards to include them in review again. Cards will "
            "appear in study sessions based on their scheduling."
        )
    )
    async def unsuspendCards(
        card_ids: list[int],
    ) -> dict[str, Any]:
        """Unsuspend cards.

        Args:
            card_ids: List of card IDs to unsuspend

        Returns:
            Dictionary containing:
            - success (bool): Whether the operation succeeded
            - count (int): Number of cards unsuspended
            - message (str): Human-readable result message
            - error (str): Error message (if failed)

        Examples:
            Unsuspend specific cards:
            >>> await unsuspendCards(card_ids=[1234567890, 1234567891])
        """
        arguments = {"card_ids": card_ids}
        return await call_main_thread("unsuspendCards", arguments)
