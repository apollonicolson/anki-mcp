"""Restore backup tool - Restore collection from a backup."""
from typing import Any, Callable, Coroutine
import os
import logging

from ....handler_registry import register_handler

logger = logging.getLogger(__name__)


# ============================================================================
# HANDLER - Runs on Qt main thread, accesses mw
# ============================================================================

def _restore_backup_handler(
    backup_path: str,
) -> dict[str, Any]:
    """
    Restore collection from a backup.

    WARNING: This replaces your entire collection with the backup.
    All changes since the backup was created will be lost.

    This function runs on the Qt MAIN THREAD and has direct access to mw.

    Args:
        backup_path: Path to the .colpkg backup file

    Returns:
        dict: Result with structure:
            - success (bool): Whether the operation succeeded
            - requiresRestart (bool): Whether Anki needs to restart
            - message (str): Human-readable result message

    Raises:
        RuntimeError: If collection is not loaded
    """
    from aqt import mw

    if mw is None:
        raise RuntimeError("Main window not available")

    if not os.path.exists(backup_path):
        return {
            "success": False,
            "error": f"Backup file not found: {backup_path}",
            "hint": "Use listBackups to see available backups.",
        }

    if not backup_path.endswith(".colpkg"):
        return {
            "success": False,
            "error": "File must be a .colpkg backup file",
            "hint": "Only .colpkg files can be restored as full collection backups.",
        }

    # Note: Actually restoring requires unloading the collection and restarting
    # This is a complex operation that requires GUI interaction in Anki.
    # We return instructions for the user instead of doing it programmatically.

    return {
        "success": True,
        "requiresManualAction": True,
        "backupPath": backup_path,
        "backupName": os.path.basename(backup_path),
        "message": (
            "To restore this backup, go to Anki menu: File > Switch Profile, "
            "then click 'Open Backup' and select the backup file. "
            "This will replace your current collection."
        ),
        "instructions": [
            "1. In Anki, go to File > Switch Profile",
            "2. Click 'Open Backup' button",
            f"3. Select: {backup_path}",
            "4. Confirm the restore",
            "5. Anki will restart with the restored collection",
        ],
    }


# Register handler at import time
register_handler("restoreBackup", _restore_backup_handler)


# ============================================================================
# MCP TOOL - Runs in background thread, bridges to handler via queue
# ============================================================================

def register_restore_backup_tool(
    mcp,  # FastMCP instance
    call_main_thread: Callable[[str, dict], Coroutine[Any, Any, Any]]
) -> None:
    """Register restore-backup tool with the MCP server."""

    @mcp.tool(
        description=(
            "Get instructions for restoring a collection from a backup. "
            "CRITICAL: Restoring a backup replaces your ENTIRE collection. "
            "All changes since the backup will be LOST. This requires manual "
            "action in Anki's GUI due to the need to unload the collection."
        )
    )
    async def restoreBackup(
        backup_path: str,
    ) -> dict[str, Any]:
        """Get instructions for restoring from a backup.

        Args:
            backup_path: Full path to the .colpkg backup file

        Returns:
            Dictionary containing:
            - success (bool): Whether the backup file was found
            - requiresManualAction (bool): True (restore needs GUI)
            - backupPath (str): Path to backup file
            - backupName (str): Backup filename
            - message (str): Human-readable instructions
            - instructions (list): Step-by-step restore instructions
            - error (str): Error message (if failed)

        Examples:
            Get restore instructions:
            >>> result = await restoreBackup(
            ...     backup_path="C:/Users/.../backups/backup-2024-01-15.colpkg"
            ... )
            >>> for step in result["instructions"]:
            ...     print(step)

        Note:
            Due to Anki's architecture, restoring a backup requires:
            1. Unloading the current collection
            2. Replacing the database files
            3. Reloading the collection

            This cannot be done safely while the collection is in use.
            Use Anki's File > Switch Profile > Open Backup for safe restoration.
        """
        arguments = {"backup_path": backup_path}
        return await call_main_thread("restoreBackup", arguments)
