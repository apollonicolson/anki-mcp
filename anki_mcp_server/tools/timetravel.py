"""Time travel - query and diff snapshots as immutable database values.

Snapshots are read with plain sqlite3 and `immutable=1`, never through Anki's
backend. That is safe precisely because a checkpointed snapshot is a complete,
frozen file: no locking, no -shm, no mutation, and readers never block Anki.

The live collection cannot participate directly - Anki holds it exclusively - so
"diff against now" takes an ephemeral snapshot first and compares two values.
"""
import os
import sqlite3

from .base import T, ToolError, col
from .history import _snap_root, snapshot_create

FORBIDDEN = ("INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "ATTACH", "DETACH", "PRAGMA")
MAX_ROWS = 1000


def _snapshot_db(name: str) -> str:
    path = os.path.join(_snap_root(), name, "collection.anki2")
    if not os.path.isfile(path):
        raise ToolError(f"No collection.anki2 in snapshot: {name}", hint="Use snapshot-list")
    return path


def _resolve(name: str) -> tuple:
    """Return (db_path, resolved_name). 'now' materialises an ephemeral snapshot."""
    if name in ("now", "live"):
        snap = snapshot_create(label="ephemeral")
        return _snapshot_db(snap["snapshot"]), snap["snapshot"]
    return _snapshot_db(name), name


def _guard(sql: str) -> str:
    import re

    if not sql.strip().upper().startswith("SELECT"):
        raise ToolError("Only SELECT queries allowed")
    for word in FORBIDDEN:
        if re.search(rf"\b{word}\b", sql.upper()):
            raise ToolError(f"Forbidden keyword: {word}")
    return sql


def _connect(db_path: str):
    """Read-only connection with Anki's custom collation registered.

    Anki declares text columns COLLATE unicase; a plain sqlite3 connection has no
    such collation and fails on any ORDER BY / GROUP BY touching them.
    """
    con = sqlite3.connect(f"file:{db_path}?immutable=1", uri=True)
    con.create_collation(
        "unicase",
        lambda a, b: (a.casefold() > b.casefold()) - (a.casefold() < b.casefold()),
    )
    return con


def _rows(cursor, limit: int = MAX_ROWS) -> dict:
    columns = [d[0] for d in cursor.description] if cursor.description else []
    fetched = cursor.fetchmany(limit + 1)
    truncated = len(fetched) > limit
    return {
        "columns": columns,
        "rows": [list(r) for r in fetched[:limit]],
        "count": min(len(fetched), limit),
        "truncated": truncated,
    }


def snapshot_query(snapshot: str, sql: str, params: list = None, limit: int = MAX_ROWS):
    """Query a point-in-time value of the collection. snapshot='now' snapshots first."""
    db_path, resolved = _resolve(snapshot)
    _guard(sql)
    con = _connect(db_path)
    try:
        result = _rows(con.execute(sql, params or []), limit)
    except sqlite3.Error as e:
        raise ToolError(f"SQL error: {e}")
    finally:
        con.close()
    return {"snapshot": resolved, **result}


def snapshot_diff(a: str, b: str, entity: str = "notes", limit: int = 200,
                  include_values: bool = False):
    """Set difference between two collection values.

    Returns added (in b only), removed (in a only) and changed (in both, differing).
    entity='notes' compares flds/tags/mod; entity='cards' compares due/queue/type/ivl.
    """
    if entity not in ("notes", "cards"):
        raise ToolError(f"entity must be notes or cards, got {entity}")

    a_path, a_name = _resolve(a)
    b_path, b_name = _resolve(b)
    if a_path == b_path:
        raise ToolError("a and b resolve to the same snapshot")

    # mid matters: a notetype change rewrites no field text, so comparing only
    # flds/tags reports "no change" for a retype.
    compare = ("x.flds <> y.flds OR x.tags <> y.tags OR x.mid <> y.mid"
               if entity == "notes"
               else "x.due <> y.due OR x.queue <> y.queue OR x.type <> y.type "
                    "OR x.ivl <> y.ivl OR x.did <> y.did OR x.ord <> y.ord")

    con = _connect(a_path)
    try:
        con.execute("ATTACH DATABASE ? AS b", (f"file:{b_path}?immutable=1",))
        counts = {
            "added": con.execute(
                f"SELECT count(*) FROM b.{entity} y WHERE y.id NOT IN (SELECT id FROM main.{entity})"
            ).fetchone()[0],
            "removed": con.execute(
                f"SELECT count(*) FROM main.{entity} x WHERE x.id NOT IN (SELECT id FROM b.{entity})"
            ).fetchone()[0],
            "changed": con.execute(
                f"SELECT count(*) FROM main.{entity} x JOIN b.{entity} y ON y.id = x.id WHERE {compare}"
            ).fetchone()[0],
        }
        if include_values and entity == "notes":
            cur = con.execute(
                "SELECT x.id, x.tags, y.tags, x.flds, y.flds FROM main.notes x "
                f"JOIN b.notes y ON y.id = x.id WHERE {compare} LIMIT ?", (limit,))
            changed = [{"id": r[0], "tags_a": r[1], "tags_b": r[2],
                        "flds_a": r[3][:300], "flds_b": r[4][:300]} for r in cur.fetchall()]
        else:
            cur = con.execute(
                f"SELECT x.id FROM main.{entity} x JOIN b.{entity} y ON y.id = x.id "
                f"WHERE {compare} LIMIT ?", (limit,))
            changed = [r[0] for r in cur.fetchall()]
    except sqlite3.Error as e:
        raise ToolError(f"SQL error: {e}")
    finally:
        con.close()

    return {"a": a_name, "b": b_name, "entity": entity, **counts,
            "changed_sample": changed, "sample_limit": limit}


def snapshot_as_of(note_id: int, snapshot: str):
    """Point-in-time read of a single note - the common case for 'what did this say?'."""
    db_path, resolved = _resolve(snapshot)
    con = _connect(db_path)
    try:
        row = con.execute(
            "SELECT id, mid, mod, usn, tags, flds FROM notes WHERE id = ?", (note_id,)
        ).fetchone()
    finally:
        con.close()
    if row is None:
        return {"snapshot": resolved, "note_id": note_id, "existed": False}
    return {
        "snapshot": resolved, "note_id": row[0], "existed": True,
        "mid": row[1], "mod": row[2], "usn": row[3], "tags": row[4],
        "fields": row[5].split("\x1f"),
    }


@T("collection-info", "Collection paths plus note/card/deck/notetype counts")
def collection_info():
    """get-collection-info returns paths but no counts; this answers the first question."""
    collection = col()
    scalar = collection.db.scalar
    return {
        "path": collection.path,
        "profile": os.path.basename(os.path.dirname(collection.path)),
        "notes": scalar("SELECT count(*) FROM notes"),
        "cards": scalar("SELECT count(*) FROM cards"),
        "decks": scalar("SELECT count(*) FROM decks"),
        "notetypes": scalar("SELECT count(*) FROM notetypes"),
        "revlog": scalar("SELECT count(*) FROM revlog"),
        "pending_sync": scalar("SELECT count(*) FROM notes WHERE usn = -1"),
        "snapshots": len([d for d in os.listdir(_snap_root())
                          if os.path.isdir(os.path.join(_snap_root(), d))]),
    }
