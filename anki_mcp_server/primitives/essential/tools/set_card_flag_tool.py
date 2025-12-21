"""Set card flag tool - Set flags on cards."""
from typing import Any, Callable, Coroutine, Sequence
import logging

from ....handler_registry import register_handler

logger = logging.getLogger(__name__)


# Flag constants
FLAG_NONE = 0
FLAG_RED = 1
FLAG_ORANGE = 2
FLAG_GREEN = 3
FLAG_BLUE = 4
FLAG_PINK = 5
FLAG_TURQUOISE = 6
FLAG_PURPLE = 7

FLAG_NAMES = {
    0: "none",
    1: "red",
    2: "orange",
    3: "green",
    4: "blue",
    5: "pink",
    6: "turquoise",
    7: "purple",
}


# ============================================================================
# HANDLER - Runs on Qt main thread, accesses mw.col
# ============================================================================

def _set_card_flag_handler(
    card_ids: Sequence[int],
    flag: int,
) -> dict[str, Any]:
    """
    Set a flag on cards.

    This function runs on the Qt MAIN THREAD and has direct access to mw.col.

    Args:
        card_ids: List of card IDs to set flag on
        flag: Flag number (0=none, 1=red, 2=orange, 3=green, 4=blue,
              5=pink, 6=turquoise, 7=purple)

    Returns:
        dict: Result with structure:
            - success (bool): Whether the operation succeeded
            - count (int): Number of cards updated
            - flag (int): Flag number that was set
            - flagName (str): Human-readable flag name
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

    if flag < 0 or flag > 7:
        return {
            "success": False,
            "error": f"Invalid flag number: {flag}",
            "hint": "Flag must be 0-7 (0=none, 1=red, 2=orange, 3=green, 4=blue, 5=pink, 6=turquoise, 7=purple)",
        }

    try:
        mw.requireReset()
        mw.col.set_user_flag_for_cards(flag, card_ids)
    finally:
        if mw.col:
            mw.maybeReset()

    flag_name = FLAG_NAMES.get(flag, "unknown")

    return {
        "success": True,
        "count": len(card_ids),
        "flag": flag,
        "flagName": flag_name,
        "message": f"Set {flag_name} flag on {len(card_ids)} cards" if flag > 0 else f"Removed flags from {len(card_ids)} cards",
    }


# Register handler at import time
register_handler("setCardFlag", _set_card_flag_handler)


# ============================================================================
# MCP TOOL - Runs in background thread, bridges to handler via queue
# ============================================================================

def register_set_card_flag_tool(
    mcp,  # FastMCP instance
    call_main_thread: Callable[[str, dict], Coroutine[Any, Any, Any]]
) -> None:
    """Register set-card-flag tool with the MCP server."""

    @mcp.tool(
        description=(
            "Set a colored flag on cards. Flags help you mark cards for later "
            "review or categorization. Use flag 0 to remove flags."
        )
    )
    async def setCardFlag(
        card_ids: list[int],
        flag: int,
    ) -> dict[str, Any]:
        """Set a flag on cards.

        Args:
            card_ids: List of card IDs to set flag on
            flag: Flag number:
                  0 = none (remove flag)
                  1 = red
                  2 = orange
                  3 = green
                  4 = blue
                  5 = pink
                  6 = turquoise
                  7 = purple

        Returns:
            Dictionary containing:
            - success (bool): Whether the operation succeeded
            - count (int): Number of cards updated
            - flag (int): Flag number that was set
            - flagName (str): Human-readable flag name
            - message (str): Human-readable result message
            - error (str): Error message (if failed)

        Examples:
            Set red flag:
            >>> await setCardFlag(card_ids=[1234567890], flag=1)

            Remove flags:
            >>> await setCardFlag(card_ids=[1234567890], flag=0)

        Note:
            To find flagged cards, use findCards with query "flag:1" (red),
            "flag:2" (orange), etc.
        """
        arguments = {
            "card_ids": card_ids,
            "flag": flag,
        }
        return await call_main_thread("setCardFlag", arguments)
