"""Import/Export tool - Import and export decks and collections."""
from typing import Any, Callable, Coroutine, Optional, Sequence
import os
import logging

from ....handler_registry import register_handler

logger = logging.getLogger(__name__)


# ============================================================================
# HANDLERS - Run on Qt main thread, access mw.col
# ============================================================================

def _export_deck_handler(
    deck_name: Optional[str] = None,
    out_path: str = "",
    include_scheduling: bool = True,
    include_media: bool = True,
) -> dict[str, Any]:
    """
    Export a deck or the entire collection as .apkg.

    This function runs on the Qt MAIN THREAD and has direct access to mw.col.

    Args:
        deck_name: Name of deck to export. If None, exports all decks.
        out_path: Output file path. If empty, uses default location.
        include_scheduling: Include review history and scheduling info
        include_media: Include media files

    Returns:
        dict: Result with structure:
            - success (bool): Whether the operation succeeded
            - path (str): Path to exported file
            - message (str): Human-readable result message

    Raises:
        RuntimeError: If collection is not loaded
    """
    from aqt import mw
    from anki.exporting import AnkiPackageExporter
    from anki.decks import DeckId

    if mw.col is None:
        raise RuntimeError("Collection not loaded")

    # Determine output path
    if not out_path:
        export_folder = os.path.join(mw.pm.profileFolder(), "exports")
        os.makedirs(export_folder, exist_ok=True)

        if deck_name:
            safe_name = "".join(c if c.isalnum() or c in " -_" else "_" for c in deck_name)
            out_path = os.path.join(export_folder, f"{safe_name}.apkg")
        else:
            out_path = os.path.join(export_folder, "collection.apkg")

    # Get deck ID if specified
    did: Optional[DeckId] = None
    if deck_name:
        deck = mw.col.decks.by_name(deck_name)
        if deck is None:
            return {
                "success": False,
                "error": f"Deck not found: {deck_name}",
                "hint": "Use list_decks to see available decks.",
            }
        did = deck["id"]

    try:
        exporter = AnkiPackageExporter(mw.col)
        exporter.includeSched = include_scheduling
        exporter.includeMedia = include_media
        if did:
            exporter.did = did
        exporter.exportInto(out_path)
    except Exception as e:
        return {
            "success": False,
            "error": f"Export failed: {str(e)}",
        }

    return {
        "success": True,
        "path": out_path,
        "deckName": deck_name or "All decks",
        "includeScheduling": include_scheduling,
        "includeMedia": include_media,
        "message": f"Exported to {out_path}",
    }


def _import_package_handler(
    path: str,
) -> dict[str, Any]:
    """
    Import an .apkg package.

    This function runs on the Qt MAIN THREAD and has direct access to mw.col.

    Args:
        path: Path to the .apkg file to import

    Returns:
        dict: Result with structure:
            - success (bool): Whether the operation succeeded
            - message (str): Human-readable result message

    Raises:
        RuntimeError: If collection is not loaded
    """
    from aqt import mw
    from anki.importing.anki2 import Anki2Importer

    if mw.col is None:
        raise RuntimeError("Collection not loaded")

    if not os.path.exists(path):
        return {
            "success": False,
            "error": f"File not found: {path}",
        }

    if not path.endswith(".apkg") and not path.endswith(".colpkg"):
        return {
            "success": False,
            "error": "File must be .apkg or .colpkg",
            "hint": "Only Anki package files can be imported.",
        }

    try:
        mw.requireReset()

        # Use the modern import API
        from anki.import_export_pb2 import ImportAnkiPackageRequest
        request = ImportAnkiPackageRequest(
            package_path=path,
        )
        log = mw.col.import_anki_package(request)

    except Exception as e:
        return {
            "success": False,
            "error": f"Import failed: {str(e)}",
        }
    finally:
        if mw.col:
            mw.maybeReset()

    return {
        "success": True,
        "path": path,
        "message": f"Successfully imported {os.path.basename(path)}",
    }


def _export_collection_handler(
    out_path: str = "",
    include_media: bool = True,
) -> dict[str, Any]:
    """
    Export the entire collection as .colpkg (backup format).

    This function runs on the Qt MAIN THREAD and has direct access to mw.col.

    Args:
        out_path: Output file path. If empty, uses default location.
        include_media: Include media files

    Returns:
        dict: Result with structure:
            - success (bool): Whether the operation succeeded
            - path (str): Path to exported file
            - message (str): Human-readable result message

    Raises:
        RuntimeError: If collection is not loaded
    """
    from aqt import mw

    if mw.col is None:
        raise RuntimeError("Collection not loaded")

    # Determine output path
    if not out_path:
        export_folder = os.path.join(mw.pm.profileFolder(), "exports")
        os.makedirs(export_folder, exist_ok=True)
        out_path = os.path.join(export_folder, "collection.colpkg")

    try:
        mw.col.export_collection_package(
            out_path=out_path,
            include_media=include_media,
            legacy=False,
        )
    except Exception as e:
        return {
            "success": False,
            "error": f"Export failed: {str(e)}",
        }

    return {
        "success": True,
        "path": out_path,
        "includeMedia": include_media,
        "message": f"Exported collection to {out_path}",
    }


# Register handlers at import time
register_handler("exportDeck", _export_deck_handler)
register_handler("importPackage", _import_package_handler)
register_handler("exportCollection", _export_collection_handler)


# ============================================================================
# MCP TOOLS - Run in background thread, bridge to handler via queue
# ============================================================================

def register_import_export_tool(
    mcp,  # FastMCP instance
    call_main_thread: Callable[[str, dict], Coroutine[Any, Any, Any]]
) -> None:
    """Register import/export tools with the MCP server."""

    @mcp.tool(
        description=(
            "Export a deck or all decks as an .apkg file. This can be shared "
            "with others or used as a portable backup of specific decks."
        )
    )
    async def exportDeck(
        deck_name: Optional[str] = None,
        out_path: str = "",
        include_scheduling: bool = True,
        include_media: bool = True,
    ) -> dict[str, Any]:
        """Export a deck as .apkg file.

        Args:
            deck_name: Name of deck to export. If not provided, exports all decks.
            out_path: Output file path. If empty, uses default exports folder.
            include_scheduling: Include review history and scheduling info
            include_media: Include media files

        Returns:
            Dictionary containing:
            - success (bool): Whether the operation succeeded
            - path (str): Path to exported file
            - deckName (str): Name of exported deck
            - message (str): Human-readable result message
            - error (str): Error message (if failed)

        Examples:
            Export a specific deck:
            >>> await exportDeck(deck_name="Japanese::Vocabulary")

            Export all decks without media:
            >>> await exportDeck(include_media=False)

            Export to specific path:
            >>> await exportDeck(
            ...     deck_name="French",
            ...     out_path="C:/backups/french.apkg"
            ... )
        """
        arguments = {
            "deck_name": deck_name,
            "out_path": out_path,
            "include_scheduling": include_scheduling,
            "include_media": include_media,
        }
        return await call_main_thread("exportDeck", arguments)

    @mcp.tool(
        description=(
            "Import an .apkg package into Anki. This adds new cards and updates "
            "existing ones based on note GUIDs."
        )
    )
    async def importPackage(
        path: str,
    ) -> dict[str, Any]:
        """Import an .apkg package.

        Args:
            path: Full path to the .apkg file to import

        Returns:
            Dictionary containing:
            - success (bool): Whether the operation succeeded
            - path (str): Path to imported file
            - message (str): Human-readable result message
            - error (str): Error message (if failed)

        Examples:
            Import a package:
            >>> await importPackage(path="C:/downloads/shared_deck.apkg")
        """
        arguments = {"path": path}
        return await call_main_thread("importPackage", arguments)

    @mcp.tool(
        description=(
            "Export the entire collection as a .colpkg file. This is the same "
            "format used for backups and can be used to restore or transfer "
            "your entire Anki collection."
        )
    )
    async def exportCollection(
        out_path: str = "",
        include_media: bool = True,
    ) -> dict[str, Any]:
        """Export the entire collection as .colpkg.

        Args:
            out_path: Output file path. If empty, uses default exports folder.
            include_media: Include media files (can make file much larger)

        Returns:
            Dictionary containing:
            - success (bool): Whether the operation succeeded
            - path (str): Path to exported file
            - includeMedia (bool): Whether media was included
            - message (str): Human-readable result message
            - error (str): Error message (if failed)

        Examples:
            Export collection with media:
            >>> await exportCollection()

            Export without media (smaller file):
            >>> await exportCollection(include_media=False)

            Export to specific path:
            >>> await exportCollection(out_path="C:/backups/my_collection.colpkg")
        """
        arguments = {
            "out_path": out_path,
            "include_media": include_media,
        }
        return await call_main_thread("exportCollection", arguments)
