"""MCP Resources - Expose Anki data in read-only format.

Resources provide a way to expose Anki data as readable URIs that AI clients
can access. They are read-only and provide structured data access.
"""
from typing import Any, Callable, Coroutine
import json


def register_all_resources(
    mcp,
    call_main_thread: Callable[[str, dict], Coroutine[Any, Any, Any]]
) -> None:
    """Register all MCP resources with the server."""

    # ========================================================================
    # SYSTEM INFO
    # ========================================================================

    @mcp.resource("anki://system-info")
    async def system_info() -> str:
        """Get Anki system information."""
        from .handler_registry import execute
        import sys
        import platform

        try:
            result = await call_main_thread("get-collection-info", {})
            result["python_version"] = sys.version.split()[0]
            result["platform"] = platform.system()
            result["mcp_server_version"] = "1.0.0"
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)})

    # ========================================================================
    # DECKS
    # ========================================================================

    @mcp.resource("anki://decks")
    async def decks_list() -> str:
        """List all decks with metadata."""
        result = await call_main_thread("list-decks", {"include_stats": True})
        return json.dumps(result, indent=2)

    @mcp.resource("anki://deck/{deck_name}")
    async def deck_info(deck_name: str) -> str:
        """Get detailed information about a specific deck."""
        # Get deck stats
        stats = await call_main_thread("get-deck-stats", {"deck_name": deck_name})

        # Get deck config
        config = await call_main_thread("get-deck-config", {"deck_name": deck_name})

        # Get card counts by type
        cards = await call_main_thread("find-cards", {"query": f'deck:"{deck_name}"'})

        result = {
            "deckName": deck_name,
            "stats": stats,
            "config": config.get("config", {}),
            "totalCards": len(cards.get("result", [])) if isinstance(cards, dict) else 0,
        }
        return json.dumps(result, indent=2)

    # ========================================================================
    # MODELS (NOTE TYPES)
    # ========================================================================

    @mcp.resource("anki://models")
    async def models_list() -> str:
        """List all note types (models)."""
        result = await call_main_thread("list-models", {})
        return json.dumps(result, indent=2)

    @mcp.resource("anki://model/{model_name}")
    async def model_info(model_name: str) -> str:
        """Get detailed information about a note type."""
        fields = await call_main_thread("model-field-names", {"modelName": model_name})
        templates = await call_main_thread("model-templates", {"modelName": model_name})
        styling = await call_main_thread("model-styling", {"modelName": model_name})

        result = {
            "modelName": model_name,
            "fields": fields.get("result", fields) if isinstance(fields, dict) else fields,
            "templates": templates.get("templates", []),
            "css": styling.get("css", ""),
        }
        return json.dumps(result, indent=2)

    # ========================================================================
    # TAGS
    # ========================================================================

    @mcp.resource("anki://tags")
    async def tags_list() -> str:
        """Get all tags in the collection."""
        result = await call_main_thread("list-tags", {})
        tags = result.get("result", result) if isinstance(result, dict) else result

        # Organize into hierarchy
        hierarchy = {}
        for tag in tags:
            parts = tag.split("::")
            current = hierarchy
            for part in parts:
                if part not in current:
                    current[part] = {}
                current = current[part]

        return json.dumps({
            "tags": tags,
            "hierarchy": hierarchy,
            "count": len(tags),
        }, indent=2)

    # ========================================================================
    # STATISTICS
    # ========================================================================

    @mcp.resource("anki://stats/today")
    async def stats_today() -> str:
        """Get today's study statistics."""
        result = await call_main_thread("get-studied-today", {})
        return json.dumps(result, indent=2)

    @mcp.resource("anki://stats/forecast")
    async def stats_forecast() -> str:
        """Get review forecast for the next 30 days."""
        result = await call_main_thread("get-forecast", {"days": 30})
        return json.dumps(result, indent=2)

    @mcp.resource("anki://stats/retention")
    async def stats_retention() -> str:
        """Get retention analysis across interval ranges."""
        result = await call_main_thread("get-retention-analysis", {})
        return json.dumps(result, indent=2)

    @mcp.resource("anki://stats/difficulty")
    async def stats_difficulty() -> str:
        """Get card difficulty distribution."""
        result = await call_main_thread("get-difficulty-distribution", {})
        return json.dumps(result, indent=2)

    @mcp.resource("anki://stats/collection")
    async def stats_collection() -> str:
        """Get overall collection statistics."""
        result = await call_main_thread("get-collection-stats", {})
        return json.dumps(result, indent=2)

    # ========================================================================
    # DUE CARDS
    # ========================================================================

    @mcp.resource("anki://due")
    async def due_overview() -> str:
        """Get overview of due cards across all decks."""
        tree = await call_main_thread("get-deck-due-tree", {})
        return json.dumps(tree, indent=2)

    @mcp.resource("anki://due/{deck_name}")
    async def due_deck(deck_name: str) -> str:
        """Get due cards for a specific deck."""
        result = await call_main_thread("get-due-cards", {
            "deck_name": deck_name,
            "limit": 100
        })
        return json.dumps(result, indent=2)

    # ========================================================================
    # LEECHES
    # ========================================================================

    @mcp.resource("anki://leeches")
    async def leeches_list() -> str:
        """Get all leech cards (frequently failed)."""
        result = await call_main_thread("get-leech-cards", {"threshold": 8})
        return json.dumps(result, indent=2)

    # ========================================================================
    # BACKUPS
    # ========================================================================

    @mcp.resource("anki://backups")
    async def backups_list() -> str:
        """List available backups."""
        result = await call_main_thread("list-backups", {})
        return json.dumps(result, indent=2)
