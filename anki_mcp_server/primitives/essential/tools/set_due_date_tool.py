"""Set due date tool - Reschedule cards to specific due dates."""
from typing import Any, Callable, Coroutine, Sequence
import logging

from ....handler_registry import register_handler

logger = logging.getLogger(__name__)


# ============================================================================
# HANDLER - Runs on Qt main thread, accesses mw.col
# ============================================================================

def _set_due_date_handler(
    card_ids: Sequence[int],
    days: str,
) -> dict[str, Any]:
    """
    Set cards to be due in a specific number of days.

    This function runs on the Qt MAIN THREAD and has direct access to mw.col.

    Args:
        card_ids: List of card IDs to reschedule
        days: Days until due. Can be:
              - A single number: "5" (due in 5 days)
              - A range: "5-10" (randomly between 5-10 days)
              - "0" for today

    Returns:
        dict: Result with structure:
            - success (bool): Whether the operation succeeded
            - count (int): Number of cards rescheduled
            - days (str): The days parameter used
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
            "hint": "Use findCards to get card IDs.",
        }

    if not days:
        return {
            "success": False,
            "error": "No days parameter provided",
            "hint": "Provide days as '5' or '5-10' for a range.",
        }

    try:
        mw.requireReset()
        mw.col.sched.set_due_date(card_ids, days)
    finally:
        if mw.col:
            mw.maybeReset()

    return {
        "success": True,
        "count": len(card_ids),
        "days": days,
        "message": f"Set {len(card_ids)} cards to be due in {days} days",
    }


# Register handler at import time
register_handler("setDueDate", _set_due_date_handler)


# ============================================================================
# MCP TOOL - Runs in background thread, bridges to handler via queue
# ============================================================================

def register_set_due_date_tool(
    mcp,  # FastMCP instance
    call_main_thread: Callable[[str, dict], Coroutine[Any, Any, Any]]
) -> None:
    """Register set-due-date tool with the MCP server."""

    @mcp.tool(
        description=(
            "Set cards to be due in a specific number of days. This turns cards "
            "into review cards if they aren't already. Useful for rescheduling."
        )
    )
    async def setDueDate(
        card_ids: list[int],
        days: str,
    ) -> dict[str, Any]:
        """Set cards to be due in a specific number of days.

        Args:
            card_ids: List of card IDs to reschedule
            days: Days until due:
                  - Single number: "5" (due in exactly 5 days)
                  - Range: "5-10" (randomly between 5-10 days)
                  - "0" for today
                  - "1" for tomorrow

        Returns:
            Dictionary containing:
            - success (bool): Whether the operation succeeded
            - count (int): Number of cards rescheduled
            - days (str): The days parameter used
            - message (str): Human-readable result message
            - error (str): Error message (if failed)

        Examples:
            Set cards due today:
            >>> await setDueDate(card_ids=[1234567890], days="0")

            Set cards due in 7 days:
            >>> await setDueDate(card_ids=[1234567890], days="7")

            Set cards due in 5-10 days (random):
            >>> await setDueDate(card_ids=[1234567890], days="5-10")
        """
        arguments = {
            "card_ids": card_ids,
            "days": days,
        }
        return await call_main_thread("setDueDate", arguments)
