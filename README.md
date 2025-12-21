# AnkiMCP Server (Addon)

An Anki addon that exposes your collection to AI assistants via the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/).

## What is this?

AnkiMCP Server runs a local MCP server inside Anki, allowing AI assistants like Claude to interact with your flashcard collection. This enables AI-powered study sessions, card creation, and collection management.

Part of the [ankimcp.ai](https://ankimcp.ai) project.

## Note on First Run

On first run, this addon downloads `pydantic_core` (~2MB) from PyPI. This is required because pydantic_core contains platform-specific binaries (Windows/macOS/Linux) that cannot be bundled in a single addon file.

## Features

- **Local HTTP server** - Runs on `http://127.0.0.1:3141/` by default
- **MCP protocol** - Compatible with any MCP client (Claude Desktop, etc.)
- **Auto-start** - Server starts automatically when Anki opens
- **Tunnel-friendly** - Works with Cloudflare Tunnel, ngrok, etc.
- **Cross-platform** - Works on macOS, Windows, and Linux (x64 and ARM)

## Installation

### From AnkiWeb (recommended)

1. Open Anki and go to *Tools → Add-ons → Get Add-ons...*
2. Enter code: `124672614`
3. Restart Anki

### From GitHub Releases

1. Download `anki_mcp_server.ankiaddon` from [Releases](https://github.com/ankimcp/anki-mcp-server-addon/releases)
2. Double-click to install, or use *Tools → Add-ons → Install from file...*
3. Restart Anki

## Usage

The server starts automatically when you open Anki. Check status via *Tools → AnkiMCP Server Settings...*

### Connect with Claude Desktop

Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "anki": {
      "url": "http://127.0.0.1:3141/"
    }
  }
}
```

## Configuration

Edit via Anki's *Tools → Add-ons → AnkiMCP Server → Config*:

```json
{
  "mode": "http",
  "http_port": 3141,
  "http_host": "127.0.0.1",
  "auto_connect_on_startup": true
}
```

## Available Tools

Over 100 tools organized by category. All search/list tools support pagination with `limit` and `offset` parameters.

### Core Tools

| Tool | Description |
|------|-------------|
| `sync` | Synchronize collection with AnkiWeb |
| `schema` | Get Anki's data model (entities, fields, relationships) |
| `query-syntax` | Get documentation for Anki's search syntax |
| `raw-sql` | Execute read-only SQL queries on Anki's database |

### Decks & Notes

| Tool | Description |
|------|-------------|
| `list-decks` | List decks with optional stats and filtering |
| `create-deck` | Create a new deck |
| `find-notes` | Search for notes using Anki's search syntax |
| `find-cards` | Search for cards using Anki's search syntax |
| `get-notes-info` | Get detailed information about notes |
| `get-cards-info` | Get detailed information about cards |
| `add-note` | Add a new note to a deck |
| `update-note` | Update fields and/or tags of existing notes |
| `delete-notes` | Delete notes from the collection |

### Review & Scheduling

| Tool | Description |
|------|-------------|
| `get-due-cards` | Get cards due for review |
| `present-card` | Get card content for review |
| `rate-card` | Rate a card (Again/Hard/Good/Easy) |
| `get-forecast` | Predict cards due in coming days |
| `get-retention-analysis` | Analyze success rate by interval |
| `get-leech-cards` | Find frequently failed cards |

### Note Types & Media

| Tool | Description |
|------|-------------|
| `list-models` | List available note types |
| `model-field-names` | Get field names for a note type |
| `create-model` | Create a new note type |
| `store-media-file` | Store a media file (image/audio) |
| `list-media-files` | List media files matching a pattern |

### GUI Tools

| Tool | Description |
|------|-------------|
| `gui-browse` | Open the card browser with a search query |
| `gui-add-cards` | Open the Add Cards dialog |
| `gui-edit-note` | Open the note editor for a specific note |
| `gui-deck-browser` | Navigate to deck browser |
| `gui-deck-review` | Start reviewing a deck |

### Resources

Read-only data exposed via MCP resource URIs:

| URI | Description |
|-----|-------------|
| `anki://system-info` | Anki version and system information |
| `anki://decks` | All decks with metadata |
| `anki://deck/{name}` | Specific deck details |
| `anki://models` | All note types |
| `anki://tags` | Tag hierarchy |
| `anki://stats/today` | Today's study statistics |
| `anki://stats/forecast` | 30-day review forecast |
| `anki://due` | Due cards overview |
| `anki://leeches` | Problem cards |

### Prompts

Guided workflows for common tasks:

| Prompt | Description |
|--------|-------------|
| `review_session` | Conduct an interactive review session |
| `deck_consolidation` | Merge and reorganize decks |
| `card_improvement` | Analyze and improve card quality |
| `leech_remediation` | Handle frequently failed cards |
| `study_planning` | Create a study schedule |
| `note_creation` | Best practices for creating notes |
| `collection_cleanup` | Maintain and optimize the collection |
| `cloze_creation` | Create effective cloze deletions |
| `language_learning` | Specialized language learning workflow |

## Requirements

- Anki 25.x or later (Python 3.13)

## Architecture

The addon runs an MCP server in a background thread with HTTP transport (FastMCP + uvicorn). All Anki operations are bridged to the main Qt thread via a queue system, following the same proven pattern as AnkiConnect.

For details, see [Anki Add-on Development Documentation](https://addon-docs.ankiweb.net/).

## License

AGPL-3.0-or-later

## Links

- [ankimcp.ai](https://ankimcp.ai) - Project homepage
- [MCP Protocol](https://modelcontextprotocol.io/) - Model Context Protocol specification
- [Anki Add-on Docs](https://addon-docs.ankiweb.net/) - Official Anki addon development documentation
