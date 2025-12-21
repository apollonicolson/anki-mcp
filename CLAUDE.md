# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Reference

```bash
./package.sh                    # Build .ankiaddon package
# Install: double-click anki_mcp_server.ankiaddon or Tools → Add-ons → Install from file
# Restart Anki after installation
```

## Project Overview

Anki addon that runs an MCP server inside Anki, exposing collection operations to AI assistants. Uses FastMCP + uvicorn for HTTP transport.

- **Package**: `anki_mcp_server.ankiaddon`
- **Default Port**: 3141
- **License**: AGPL-3.0-or-later

## Architecture

### Threading Model

```
┌─────────────────────────────────────────┐
│          AI Client (HTTP)               │
└───────────────┬─────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────┐
│    Background Thread (asyncio)          │
│  - MCP Server (FastMCP + uvicorn)       │
│  - Tool handlers bridge to main thread  │
└───────────────┬─────────────────────────┘
                │
                │ queue.Queue (thread-safe)
                ▼
┌─────────────────────────────────────────┐
│        QueueBridge                      │
│  - request_queue                        │
│  - response_queue                       │
└───────────────┬─────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────┐
│     Qt Main Thread                      │
│  - QTimer (25ms polling)                │
│  - RequestProcessor                     │
│  - Access to mw.col (safe here)         │
└─────────────────────────────────────────┘
```

**Key Principle**: Never access `mw.col` from background threads. All Anki operations must go through the queue bridge to execute on the main Qt thread.

### File Structure

```
anki_mcp_server/
├── __init__.py              # Entry point, hooks registration, pydantic_core loader
├── config.py                # Configuration from Anki's addon config
├── mcp_server.py            # FastMCP server in background thread
├── queue_bridge.py          # Thread-safe request/response queue
├── request_processor.py     # Main thread handler dispatcher
├── handler_registry.py      # Maps tool names to handler functions
├── tools/                   # MCP tools (modular by category)
│   ├── __init__.py          # Imports all modules, exports register_tools
│   ├── base.py              # T() decorator framework
│   ├── misc.py              # sync, version, profiles
│   ├── decks.py             # Deck management
│   ├── notes.py             # Note operations
│   ├── cards.py             # Card operations
│   ├── tags.py              # Tag management
│   ├── models.py            # Note type management
│   ├── media.py             # Media file operations
│   ├── review.py            # Review & scheduling
│   ├── stats.py             # Statistics & collection info
│   ├── backup.py            # Backup & import/export
│   ├── gui.py               # GUI interaction
│   ├── introspection.py     # schema, query-syntax, raw-sql
│   └── image_occlusion.py   # Image occlusion tools
├── resources.py             # MCP resources (anki://decks, etc.)
├── prompts.py               # MCP prompts (review_session, etc.)
├── connection_manager.py    # Connection lifecycle management
├── dependency_loader.py     # Runtime dependency loading (pydantic_core)
├── primitives/              # Re-exports for mcp_server.py
├── ui/                      # Qt UI components
├── transport/               # Transport layer (HTTP)
└── vendor/                  # Vendored dependencies
```

### Tool Framework (tools/base.py)

Tools use a progressive disclosure pattern with the `T()` class:

```python
# Level 1: One-liner (trivial tools)
T("list-tags", "List all tags", lambda: col().tags.all())

# Level 2: Decorator (typed tools)
@T("find-notes", "Search notes")
def find_notes(query: str, limit: int = 100) -> dict:
    return {"noteIds": col().find_notes(query)[:limit]}

# Level 3: Full control (complex tools)
@T("add-note", "Add a note", write=True)
def add_note(deckName: str, modelName: str, fields: dict) -> dict:
    deck = col().decks.by_name(deckName)
    if not deck:
        raise ToolError(f"Deck not found: {deckName}", hint="Use list-decks")
    ...
```

**Conventions**:
- Tool names use **kebab-case** (MCP standard): `find-notes`, `add-note`, `gui-browse`
- Tools require collection by default (`require_col=True`)
- Tools are read-only by default (`write=True` for mutations)
- `ToolError` provides structured errors with hints
- All tools run on Qt main thread (automatic queue bridging)

## Adding New Tools

1. Add tool to the appropriate module in `tools/` (e.g., `tools/decks.py`)
2. Import `T`, `ToolError`, `col` from `.base`
3. Use `write=True` for mutation operations
4. Use `category="gui"` for GUI-interaction tools
5. Rebuild: `./package.sh`

Example:
```python
# In tools/decks.py
from .base import T, ToolError, col

@T("my-tool", "Description here", write=True)
def my_tool(arg: str, optional_arg: int = 10) -> dict:
    # Safe to access col() - runs on main thread
    return {"result": "..."}
```

## Tool Design Patterns

### Tool Naming Convention

| Prefix | Use For | Examples |
|--------|---------|----------|
| `list-*` | Get collections/arrays | `list-decks`, `list-tags`, `list-media-files` |
| `get-*` | Get single item or specific data | `get-deck-config`, `get-note-tags` |
| `find-*` | Search with query | `find-notes`, `find-cards`, `find-duplicates` |
| `create-*` | Create new | `create-deck`, `create-model` |
| `add-*` | Add to existing | `add-note`, `add-tags` |
| `update-*` | Modify existing | `update-note`, `update-model-styling` |
| `delete-*` | Permanently remove | `delete-deck`, `delete-notes` |
| `remove-*` | Remove association | `remove-tags` (from notes) |
| `are-*` / `is-*` | Boolean checks | `are-suspended`, `are-due` |
| `can-*` | Permission/capability checks | `can-add-notes` |

### Pagination

All list/search tools support pagination to avoid returning unbounded lists:

```python
@T("find-notes", "Search for notes")
def find_notes(query: str, limit: int = 100, offset: int = 0):
    all_ids = col().find_notes(query)
    return {
        "noteIds": all_ids[offset:offset + limit],
        "count": min(limit, len(all_ids) - offset),
        "total": len(all_ids),
        "hasMore": offset + limit < len(all_ids),
        "offset": offset,
        "limit": limit,
    }
```

Paginated tools: `find-notes`, `find-cards`, `list-decks`, `list-tags`, `list-media-files`

### Consolidated Tools

Redundant tools have been merged with optional parameters:

| Tool | Replaces | Key Options |
|------|----------|-------------|
| `list-decks` | `deckNames`, `deckNamesAndIds` | `include_stats`, `pattern`, `top_level_only` |
| `get-deck-due-tree` | `getDeckDueTree` | (none - returns full tree) |
| `list-models` | `modelNames`, `modelNamesAndIds`, `findModelsById`, `findModelsByName` | `pattern`, `ids`, `names`, `include_fields` |
| `get-reviews` | `cardReviews`, `getReviewsOfCards`, `getReviewLogs` | `card_ids`, `deck`, `detailed` |
| `replace-tags` | `replaceTags`, `replaceTagsInAllNotes` | `notes` (optional, all if omitted) |
| `can-add-notes` | `canAddNotes`, `canAddNotesWithErrorDetail` | `include_errors` |
| `update-note` | `updateNote`, `updateNoteFields`, `updateNoteTags` | `fields`, `tags` |
| `get-notes-info` | `notesInfo` | (renamed for consistency) |
| `get-cards-info` | `cardsInfo` | (renamed for consistency) |
| `get-notes-for-cards` | `cardsToNotes` | (renamed for clarity) |
| `delete-empty-notes` | `removeEmptyNotes` | (renamed for consistency) |
| `delete-deck-config` | `removeDeckConfigId` | (renamed for consistency) |
| `set-cards-suspended` | `suspendCards`, `unsuspendCards` | `suspended` (bool, default true) |
| `set-cards-buried` | `buryCards`, `unburyCards` | `buried` (bool, default true) |
| `get-collection-stats` | `getNumCardsReviewedToday` | (absorbed - returns `reviewsToday`) |

### Boolean List Tools

Tools that check card states return mapped results (not raw boolean arrays):

```python
@T("are-suspended", "Check if cards are suspended")
def are_suspended(cards: list[int]):
    return {card_id: col().get_card(card_id).queue == -1 for card_id in cards}
# Returns: {1234: true, 5678: false} instead of [true, false]
```

## Key Implementation Details

### Profile Lifecycle

- Server starts on `profile_did_open` hook
- Server stops on `profile_will_close` hook
- Fallback cleanup on `app_will_close` (Edge case: called on profile switch)

### DNS Rebinding Protection

Disabled in `mcp_server.py` to allow tunnel/proxy access (Cloudflare, ngrok). Users explicitly configure tunnel access.

### Vendored Dependencies

Dependencies are vendored in `vendor/shared/` to avoid conflicts with other addons. The `__init__.py` prepends vendor path to `sys.path`.

`pydantic_core` is special - it's lazy-loaded from PyPI at runtime due to platform-specific binaries.

## Introspection Tools

Three tools help AI understand Anki's data model and query capabilities:

### `schema`
Exposes Anki's complete data model:
- **Entities**: note, card, deck, model, revlog, tag
- **Fields**: All columns with types and descriptions
- **Relations**: Foreign keys and cardinality (one-to-many, many-to-one)
- **Key concepts**: note vs card, model, deck hierarchy, scheduling

### `query-syntax`
Documents Anki's search syntax for `find-notes` and `find-cards`:
- Basic searches, wildcards, field searches
- Deck/tag filters, card state (`is:due`, `is:new`)
- Card properties (`prop:ivl>30`, `prop:ease<2`)
- Date searches, combining with AND/OR/NOT
- Practical examples

### `raw-sql`
Read-only SQLite escape hatch for advanced queries:
- Only SELECT queries allowed (INSERT/UPDATE/DELETE blocked)
- Returns columns, rows, count
- Limited to 1000 rows
- Supports parameterized queries

## Documentation

- [Anki Add-on Docs](https://addon-docs.ankiweb.net/) - Official addon development documentation
- [MCP Protocol](https://modelcontextprotocol.io/) - Model Context Protocol specification
- [FastMCP](https://gofastmcp.com/) - MCP SDK used by this addon

## Common Issues

### UI Freezes During Operations

Long operations (like `sync`) run synchronously on main thread and can freeze UI. This is acceptable for v1 - same behavior as AnkiConnect.

### Port Already in Use

Change port in Anki's addon config: *Tools → Add-ons → AnkiMCP Server → Config*

### Restart Required for Config Changes

Port/host changes require Anki restart to take effect.
