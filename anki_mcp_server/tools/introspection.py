"""Introspection tools - schema, query syntax, raw SQL."""
from .base import T, ToolError, col


@T("schema", "Get Anki's data model schema for understanding entities and relationships")
def schema():
    """Expose Anki's complete data model."""
    return {
        "entities": {
            "note": {
                "description": "A note contains the actual content (fields). One note can generate multiple cards.",
                "fields": {
                    "id": {"type": "integer", "description": "Unique note ID (epoch milliseconds)"},
                    "mid": {"type": "integer", "description": "Model (note type) ID"},
                    "mod": {"type": "integer", "description": "Modification timestamp"},
                    "usn": {"type": "integer", "description": "Update sequence number for sync"},
                    "tags": {"type": "string", "description": "Space-separated tags"},
                    "flds": {"type": "string", "description": "Fields separated by 0x1f character"},
                    "sfld": {"type": "string", "description": "Sort field (for sorting in browser)"},
                    "csum": {"type": "integer", "description": "Checksum for duplicate detection"},
                    "flags": {"type": "integer", "description": "Unused"},
                    "data": {"type": "string", "description": "Unused"},
                },
                "relations": {
                    "model": {"target": "model", "type": "many-to-one", "via": "mid"},
                    "cards": {"target": "card", "type": "one-to-many", "via": "nid"},
                },
            },
            "card": {
                "description": "A card is a reviewable item generated from a note via a template.",
                "fields": {
                    "id": {"type": "integer", "description": "Unique card ID (epoch milliseconds)"},
                    "nid": {"type": "integer", "description": "Note ID this card belongs to"},
                    "did": {"type": "integer", "description": "Deck ID"},
                    "ord": {"type": "integer", "description": "Template ordinal (0-based)"},
                    "mod": {"type": "integer", "description": "Modification timestamp"},
                    "usn": {"type": "integer", "description": "Update sequence number"},
                    "type": {"type": "integer", "description": "0=new, 1=learning, 2=review, 3=relearning"},
                    "queue": {"type": "integer", "description": "-3=sched buried, -2=user buried, -1=suspended, 0=new, 1=learning, 2=review, 3=day learning, 4=preview"},
                    "due": {"type": "integer", "description": "Due date (day number for review, seconds for learning)"},
                    "ivl": {"type": "integer", "description": "Current interval in days"},
                    "factor": {"type": "integer", "description": "Ease factor (2500 = 250%)"},
                    "reps": {"type": "integer", "description": "Total number of reviews"},
                    "lapses": {"type": "integer", "description": "Number of times card went from review to relearning"},
                    "left": {"type": "integer", "description": "Learning steps remaining"},
                    "odue": {"type": "integer", "description": "Original due (for filtered decks)"},
                    "odid": {"type": "integer", "description": "Original deck ID (for filtered decks)"},
                    "flags": {"type": "integer", "description": "Card flags (1-7 for colors)"},
                    "data": {"type": "string", "description": "Extra data (JSON)"},
                },
                "relations": {
                    "note": {"target": "note", "type": "many-to-one", "via": "nid"},
                    "deck": {"target": "deck", "type": "many-to-one", "via": "did"},
                    "reviews": {"target": "revlog", "type": "one-to-many", "via": "cid"},
                },
            },
            "deck": {
                "description": "A deck is a collection of cards. Supports hierarchy via '::' separator.",
                "fields": {
                    "id": {"type": "integer", "description": "Unique deck ID"},
                    "name": {"type": "string", "description": "Deck name (:: for hierarchy)"},
                    "mod": {"type": "integer", "description": "Modification timestamp"},
                    "usn": {"type": "integer", "description": "Update sequence number"},
                    "conf": {"type": "integer", "description": "Deck config ID"},
                    "desc": {"type": "string", "description": "Deck description"},
                    "dyn": {"type": "integer", "description": "1 if filtered deck, 0 otherwise"},
                },
                "relations": {
                    "cards": {"target": "card", "type": "one-to-many", "via": "did"},
                    "config": {"target": "dconf", "type": "many-to-one", "via": "conf"},
                },
            },
            "model": {
                "description": "A model (note type) defines fields and card templates.",
                "fields": {
                    "id": {"type": "integer", "description": "Unique model ID"},
                    "name": {"type": "string", "description": "Model name"},
                    "type": {"type": "integer", "description": "0=standard, 1=cloze"},
                    "mod": {"type": "integer", "description": "Modification timestamp"},
                    "usn": {"type": "integer", "description": "Update sequence number"},
                    "flds": {"type": "array", "description": "Field definitions"},
                    "tmpls": {"type": "array", "description": "Card templates"},
                    "css": {"type": "string", "description": "Shared CSS for cards"},
                    "sortf": {"type": "integer", "description": "Sort field index"},
                },
                "relations": {
                    "notes": {"target": "note", "type": "one-to-many", "via": "mid"},
                },
            },
            "revlog": {
                "description": "Review log - records every review for statistics and undo.",
                "fields": {
                    "id": {"type": "integer", "description": "Review ID (epoch milliseconds)"},
                    "cid": {"type": "integer", "description": "Card ID"},
                    "usn": {"type": "integer", "description": "Update sequence number"},
                    "ease": {"type": "integer", "description": "Button pressed: 1=Again, 2=Hard, 3=Good, 4=Easy"},
                    "ivl": {"type": "integer", "description": "New interval (negative = seconds, positive = days)"},
                    "lastIvl": {"type": "integer", "description": "Previous interval"},
                    "factor": {"type": "integer", "description": "New ease factor"},
                    "time": {"type": "integer", "description": "Review duration in milliseconds"},
                    "type": {"type": "integer", "description": "0=learn, 1=review, 2=relearn, 3=cram"},
                },
                "relations": {
                    "card": {"target": "card", "type": "many-to-one", "via": "cid"},
                },
            },
            "tag": {
                "description": "Tags are stored on notes as space-separated strings. Hierarchy via '::'.",
                "fields": {"name": {"type": "string", "description": "Tag name"}},
                "notes": "Tags are not a separate table - they're stored in the notes.tags field.",
            },
        },
        "key_concepts": {
            "note_vs_card": "A Note holds content (fields). A Card is generated from a Note via a Template. One Note can produce multiple Cards.",
            "model": "Also called 'Note Type'. Defines which fields a note has and which card templates generate cards.",
            "deck_hierarchy": "Decks use '::' for nesting: 'Parent::Child::Grandchild'. Moving a parent moves all children.",
            "scheduling": "Cards have type (new/learning/review) and queue (determines when shown). FSRS or SM-2 algorithm.",
            "filtered_decks": "Dynamic decks that pull cards matching a search query. Cards return to original deck after review.",
        },
        "sqlite_tables": ["notes", "cards", "decks", "dconf", "revlog", "graves", "col"],
    }


@T("query-syntax", "Get documentation for Anki's search/query syntax")
def query_syntax():
    """Document Anki's powerful search syntax used in find-notes and find-cards."""
    return {
        "description": "Anki's search syntax for find-notes and find-cards tools",
        "basic_searches": {
            "text": "Searches in all fields: 'hello' matches notes containing 'hello'",
            "exact_phrase": 'Use quotes: "hello world" matches exact phrase',
            "wildcards": "'hell*' matches hello, help, etc. '*tion' matches action, motion",
        },
        "field_searches": {
            "field:value": "front:hello - search specific field",
            "field:*value*": "front:*hello* - wildcards in field search",
            "field:": "front: - find notes where field is non-empty",
        },
        "deck_and_tag": {
            "deck:NAME": "deck:Japanese - cards in deck (includes subdecks)",
            "deck:NAME*": "deck:Japanese* - wildcard deck matching",
            "tag:NAME": "tag:verb - notes with tag",
            "tag:none": "Notes with no tags",
        },
        "card_state": {
            "is:due": "Cards due for review today",
            "is:new": "New cards (never seen)",
            "is:learn": "Cards in learning phase",
            "is:review": "Review cards (graduated)",
            "is:suspended": "Suspended cards",
            "is:buried": "Buried cards",
        },
        "card_properties": {
            "prop:ivl>N": "prop:ivl>30 - interval greater than 30 days",
            "prop:due>N": "prop:due>5 - due more than 5 days from now",
            "prop:ease>N": "prop:ease<2.1 - ease factor below 210%",
            "prop:reps>N": "prop:reps>10 - reviewed more than 10 times",
            "prop:lapses>N": "prop:lapses>3 - lapsed more than 3 times",
        },
        "date_searches": {
            "added:N": "added:7 - added in last 7 days",
            "edited:N": "edited:1 - edited today",
            "rated:N": "rated:7 - reviewed in last 7 days",
            "rated:N:A": "rated:7:1 - rated 'Again' in last 7 days",
        },
        "combining": {
            "AND": "Implicit: 'deck:Japanese tag:verb' means both",
            "OR": "Use OR: 'tag:verb OR tag:noun'",
            "NOT": "Use -: '-tag:verb' excludes verb tag",
            "grouping": "Use parentheses: '(tag:verb OR tag:noun) deck:Japanese'",
        },
        "examples": [
            {"query": "deck:Japanese is:due", "description": "Due cards in Japanese deck"},
            {"query": "tag:leech prop:lapses>8", "description": "Leeches with many lapses"},
            {"query": "added:7 -is:review", "description": "Cards added this week, not yet graduated"},
            {"query": "prop:ease<2 prop:ivl>21", "description": "Struggling cards with long intervals"},
        ],
    }


@T("raw-sql", "Execute read-only SQL query on Anki's database")
def raw_sql(sql: str, params: list = None):
    """Execute a read-only SQL query on Anki's SQLite database."""
    sql_upper = sql.strip().upper()
    if not sql_upper.startswith("SELECT"):
        raise ToolError("Only SELECT queries allowed", hint="raw-sql is read-only. Use other tools for modifications.")

    dangerous = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "ATTACH", "DETACH"]
    for keyword in dangerous:
        if keyword in sql_upper:
            raise ToolError(f"Forbidden keyword: {keyword}", hint="raw-sql is read-only.")

    try:
        cursor = col().db.execute(sql, params or [])
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        rows = cursor.fetchall()

        max_rows = 1000
        truncated = len(rows) > max_rows
        if truncated:
            rows = rows[:max_rows]

        return {
            "columns": columns,
            "rows": [list(row) for row in rows],
            "count": len(rows),
            "truncated": truncated,
            "max_rows": max_rows if truncated else None,
        }
    except Exception as e:
        raise ToolError(f"SQL error: {str(e)}", hint="Check your query syntax and table/column names")
