"""Backup tool - Create and list backups."""
from typing import Any, Callable, Coroutine, Optional
import os
import logging
from datetime import datetime

from ....handler_registry import register_handler

logger = logging.getLogger(__name__)


# ============================================================================
# HANDLERS - Run on Qt main thread, access mw.col
# ============================================================================

def _create_backup_handler(
    force: bool = True,
) -> dict[str, Any]:
    """
    Create a backup of the collection.

    This function runs on the Qt MAIN THREAD and has direct access to mw.col.

    Args:
        force: If True, create backup even if one was recently made

    Returns:
        dict: Result with structure:
            - success (bool): Whether the operation succeeded
            - created (bool): Whether a backup was actually created
            - backupFolder (str): Path to backup folder
            - message (str): Human-readable result message

    Raises:
        RuntimeError: If collection is not loaded
    """
    from aqt import mw

    if mw.col is None:
        raise RuntimeError("Collection not loaded")

    backup_folder = mw.pm.backupFolder()

    try:
        created = mw.col.create_backup(
            backup_folder=backup_folder,
            force=force,
            wait_for_completion=True,
        )
    except Exception as e:
        return {
            "success": False,
            "error": f"Backup failed: {str(e)}",
            "backupFolder": backup_folder,
        }

    if created:
        return {
            "success": True,
            "created": True,
            "backupFolder": backup_folder,
            "message": "Backup created successfully",
        }
    else:
        return {
            "success": True,
            "created": False,
            "backupFolder": backup_folder,
            "message": "No backup created (no changes since last backup)",
        }


def _list_backups_handler() -> dict[str, Any]:
    """
    List all available backups.

    This function runs on the Qt MAIN THREAD and has direct access to mw.

    Returns:
        dict: Result with structure:
            - success (bool): Whether the operation succeeded
            - backups (list): List of backup info dictionaries
            - backupFolder (str): Path to backup folder
            - count (int): Number of backups
            - message (str): Human-readable result message

    Raises:
        RuntimeError: If profile manager is not available
    """
    from aqt import mw

    if mw.pm is None:
        raise RuntimeError("Profile manager not available")

    backup_folder = mw.pm.backupFolder()

    if not os.path.exists(backup_folder):
        return {
            "success": True,
            "backups": [],
            "backupFolder": backup_folder,
            "count": 0,
            "message": "No backups found (backup folder doesn't exist)",
        }

    backups = []
    try:
        for filename in sorted(os.listdir(backup_folder), reverse=True):
            if filename.endswith(".colpkg"):
                filepath = os.path.join(backup_folder, filename)
                stat = os.stat(filepath)

                # Parse timestamp from filename (format: backup-YYYY-MM-DD-HH.MM.SS.colpkg)
                try:
                    # Try to parse the timestamp from filename
                    name_part = filename.replace("backup-", "").replace(".colpkg", "")
                    timestamp = datetime.strptime(name_part, "%Y-%m-%d-%H.%M.%S")
                    date_str = timestamp.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    # Fall back to file modification time
                    date_str = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")

                backups.append({
                    "filename": filename,
                    "path": filepath,
                    "size": stat.st_size,
                    "sizeHuman": _format_size(stat.st_size),
                    "date": date_str,
                    "modifiedTimestamp": stat.st_mtime,
                })
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to list backups: {str(e)}",
            "backupFolder": backup_folder,
        }

    return {
        "success": True,
        "backups": backups,
        "backupFolder": backup_folder,
        "count": len(backups),
        "message": f"Found {len(backups)} backups",
    }


def _format_size(size_bytes: int) -> str:
    """Format size in bytes to human-readable string."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


# Register handlers at import time
register_handler("createBackup", _create_backup_handler)
register_handler("listBackups", _list_backups_handler)


# ============================================================================
# MCP TOOLS - Run in background thread, bridge to handler via queue
# ============================================================================

def register_backup_tool(
    mcp,  # FastMCP instance
    call_main_thread: Callable[[str, dict], Coroutine[Any, Any, Any]]
) -> None:
    """Register backup tools with the MCP server."""

    @mcp.tool(
        description=(
            "Create a backup of the Anki collection. Backups are stored as .colpkg "
            "files in the profile's backup folder. IMPORTANT: Always create a backup "
            "before performing destructive operations like bulk deletes or merges."
        )
    )
    async def createBackup(
        force: bool = True,
    ) -> dict[str, Any]:
        """Create a backup of the collection.

        Args:
            force: If True, create backup even if one was recently made.
                   If False, only creates if enough time has passed since last backup.

        Returns:
            Dictionary containing:
            - success (bool): Whether the operation succeeded
            - created (bool): Whether a backup was actually created
            - backupFolder (str): Path to backup folder
            - message (str): Human-readable result message
            - error (str): Error message (if failed)

        Examples:
            Create a backup:
            >>> result = await createBackup()
            >>> print(result["message"])
            "Backup created successfully"
        """
        arguments = {"force": force}
        return await call_main_thread("createBackup", arguments)

    @mcp.tool(
        description=(
            "List all available backups in the profile's backup folder. "
            "Returns backup files sorted by date (newest first)."
        )
    )
    async def listBackups() -> dict[str, Any]:
        """List all available backups.

        Returns:
            Dictionary containing:
            - success (bool): Whether the operation succeeded
            - backups (list): List of backup info with:
                - filename (str): Backup filename
                - path (str): Full path to backup file
                - size (int): Size in bytes
                - sizeHuman (str): Human-readable size
                - date (str): Backup date/time
                - modifiedTimestamp (float): Unix timestamp
            - backupFolder (str): Path to backup folder
            - count (int): Number of backups
            - message (str): Human-readable result message

        Examples:
            List backups:
            >>> result = await listBackups()
            >>> for backup in result["backups"]:
            ...     print(f"{backup['date']}: {backup['sizeHuman']}")
        """
        return await call_main_thread("listBackups", {})
