"""Append-only write journal.

Every write=True tool passes through base._write_lock, which calls record() here.
The journal stores the tool call plus pre-images of any notes it could identify,
so a mutation can be inspected or reverted without restoring a whole snapshot.

Journal failures never propagate: a broken journal must not break a write.
"""
import json
import logging
import os
import time

logger = logging.getLogger(__name__)

# Keys whose values may carry note ids, in argument dicts of write tools.
_ID_KEYS = {"notes", "noteids", "note_ids", "nids", "ids", "noteid", "note_id", "nid"}

MAX_PRE_IMAGE_NOTES = 5000


def journal_dir(col_path: str) -> str:
    d = os.path.join(os.path.dirname(col_path), "mcp-journal")
    os.makedirs(d, exist_ok=True)
    return d


def _journal_path(col_path: str) -> str:
    # Month-sharded so a single file never grows unbounded.
    stamp = time.strftime("%Y-%m", time.localtime())
    return os.path.join(journal_dir(col_path), f"journal-{stamp}.jsonl")


_declared: dict = {}


def declare_targets(col, note_ids) -> None:
    """Called by a tool that has resolved its own targets, BEFORE it mutates them.

    Heuristic extraction from argument names cannot see ids a tool resolves
    internally (a search string, a nested target map). Declaring captures the
    pre-image at declare time - which is the only moment it is still the pre-image.
    """
    ids = sorted({int(i) for i in note_ids})
    _declared.clear()
    _declared.update({"ids": ids, "pre": capture_pre_image(col, ids)})


def take_declared() -> dict:
    declared = dict(_declared)
    _declared.clear()
    return declared


# Schema ops that only rewrite a notetype definition. Everything else also rewrites
# note field data or regenerates cards, and cannot be undone from the model dict.
DEFINITION_ONLY_OPS = frozenset({
    "styling-set", "templates-set", "template-rename", "field-rename",
})


def declare_schema(col, model_names, op: str) -> None:
    """Capture notetype definitions before a schema change.

    Definition-only ops are revertible by writing the stored dict back. Structural
    ops (field add/remove/reposition, template add/remove) also change note.flds or
    regenerate cards, so the dict alone is not enough - those stay snapshot-gated.
    """
    import copy

    models = []
    for name in [n for n in model_names if n]:
        model = col.models.by_name(name)
        if model is not None:
            # by_name hands back Anki's cached dict, not a copy. Storing the
            # reference means the "pre-image" mutates when the change is applied,
            # and the revert writes the post state back over itself.
            models.append(copy.deepcopy(model))
    _declared.clear()
    _declared.update({
        "schema": {
            "op": op,
            "revertible": op in DEFINITION_ONLY_OPS,
            "models": models,
            "reason": None if op in DEFINITION_ONLY_OPS else
                      "structural change also rewrites note fields or regenerates cards",
        }
    })


def extract_note_ids(arguments: dict, _depth: int = 0) -> list:
    """Best-effort note ids from tool arguments. Empty list means 'unknown'."""
    found = []

    def consume(value):
        if isinstance(value, bool):
            return
        if isinstance(value, int):
            found.append(value)
        elif isinstance(value, str) and value.isdigit():
            found.append(int(value))
        elif isinstance(value, (list, tuple)):
            for item in value:
                consume(item)
        elif isinstance(value, dict):
            for key in ("id", "noteId", "note_id"):
                if key in value:
                    consume(value[key])

    for key, value in (arguments or {}).items():
        if key.lower() in _ID_KEYS:
            consume(value)
        elif isinstance(value, dict) and _depth < 4:
            # Nested request maps, e.g. anki {"target": {"ids": [...]}}
            found.extend(extract_note_ids(value, _depth + 1))

    # Note ids are epoch-ms; anything smaller is an ordinal, not an id.
    return sorted({i for i in found if i > 10**11})


def capture_pre_image(col, note_ids: list) -> dict:
    """Current rows for the given notes, keyed by id. Truncates past the cap."""
    if not note_ids:
        return {"mode": "none", "reason": "no note ids derivable from arguments"}

    capped = note_ids[:MAX_PRE_IMAGE_NOTES]
    placeholders = ",".join(str(int(i)) for i in capped)
    rows = col.db.all(
        f"SELECT id, mid, mod, usn, tags, flds FROM notes WHERE id IN ({placeholders})"
    )
    # Cards too: flag, suspend, bury, due, ease and deck all live on cards, so a
    # notes-only image records those mutations as transactions with no facts -
    # journalled but not revertible.
    cards = col.db.all(
        "SELECT id, nid, did, ord, type, queue, due, ivl, factor, flags "
        f"FROM cards WHERE nid IN ({placeholders})"
    )
    return {
        "mode": "notes",
        "requested": len(note_ids),
        "captured": len(rows),
        "truncated": len(note_ids) - len(capped),
        "notes": [
            {"id": r[0], "mid": r[1], "mod": r[2], "usn": r[3], "tags": r[4], "flds": r[5]}
            for r in rows
        ],
        "cards": [
            {"id": c[0], "nid": c[1], "did": c[2], "ord": c[3], "type": c[4],
             "queue": c[5], "due": c[6], "ivl": c[7], "factor": c[8], "flags": c[9]}
            for c in cards
        ],
    }


def datoms(pre: dict, post: dict) -> list:
    """Derive [entity, attribute, value, op] facts from pre/post row images.

    A change is a retraction of the old value plus an assertion of the new one, so
    reverting is uniform: invert every op. Notes present in only one image yield a
    single assertion or retraction.
    """
    if pre.get("mode") != "notes" or post.get("mode") != "notes":
        return []

    before = {n["id"]: n for n in pre.get("notes", [])}
    after = {n["id"]: n for n in post.get("notes", [])}

    facts = []
    for note_id in sorted(set(before) | set(after)):
        old, new = before.get(note_id), after.get(note_id)
        for attribute in ("tags", "flds", "mid"):
            old_value = old.get(attribute) if old else None
            new_value = new.get(attribute) if new else None
            if old_value == new_value:
                continue
            if old_value is not None:
                facts.append([note_id, attribute, old_value, "retract"])
            if new_value is not None:
                facts.append([note_id, attribute, new_value, "assert"])

    # Card attributes, namespaced so entity type is unambiguous in the log.
    cards_before = {c["id"]: c for c in pre.get("cards", [])}
    cards_after = {c["id"]: c for c in post.get("cards", [])}
    for card_id in sorted(set(cards_before) | set(cards_after)):
        old, new = cards_before.get(card_id), cards_after.get(card_id)
        for attribute in ("did", "type", "queue", "due", "ivl", "factor", "flags"):
            old_value = old.get(attribute) if old else None
            new_value = new.get(attribute) if new else None
            if old_value == new_value:
                continue
            if old_value is not None:
                facts.append([card_id, f"card.{attribute}", old_value, "retract"])
            if new_value is not None:
                facts.append([card_id, f"card.{attribute}", new_value, "assert"])
    return facts


_read_only_call: list = []


def mark_read() -> None:
    """Declare the current call a read. Keeps queries out of an append-only log.

    A single tool can serve both reads and writes (the anki grammar does), so the
    write flag alone cannot tell them apart. The tool says which it was.
    """
    _read_only_call.append(True)


def take_read() -> bool:
    was_read = bool(_read_only_call)
    _read_only_call.clear()
    return was_read


# entity -> facts, rebuilt when any journal shard changes. Without it every
# history() call rescans the whole log.
_index_cache: dict = {"stamp": None, "entities": {}}


def _journal_stamp(col_path: str):
    d = journal_dir(col_path)
    return tuple(sorted(
        (f, os.path.getmtime(os.path.join(d, f)), os.path.getsize(os.path.join(d, f)))
        for f in os.listdir(d) if f.endswith(".jsonl")
    ))


def _entity_index(col_path: str) -> dict:
    stamp = _journal_stamp(col_path)
    if _index_cache["stamp"] == stamp:
        return _index_cache["entities"]

    entities: dict = {}
    # Oldest-first, preserving each transaction's own datom order (retract, assert).
    for entry in reversed(read_entries(col_path, limit=10**9)):
        for e, attribute, value, op in entry.get("datoms") or []:
            entities.setdefault(int(e), []).append({
                "txid": str(entry.get("txid")),
                "ts": entry.get("ts"),
                "tool": entry.get("tool"),
                "attribute": attribute,
                "value": value,
                "op": op,
            })
    _index_cache.update({"stamp": stamp, "entities": entities})
    return entities


def history(col_path: str, note_id: int, limit: int = 200) -> list:
    """Every recorded fact about one entity (note or card), oldest first."""
    return _entity_index(col_path).get(int(note_id), [])[-limit:]


def schema_of(entry: dict) -> dict:
    """The notetype pre-image recorded for a schema transaction, if any."""
    return (entry.get("schema") or {})


def blame(col_path: str, note_id: int) -> dict:
    """The most recent assertion for each attribute of one note."""
    latest = {}
    for fact in history(col_path, note_id, limit=100000):
        if fact["op"] == "assert":
            latest[fact["attribute"]] = fact
    return latest


def record(entry: dict, col_path: str) -> None:
    """Append one transaction entry. Swallows its own errors by design."""
    try:
        with open(_journal_path(col_path), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning(f"journal write failed (continuing): {e}")


def read_entries(col_path: str, limit: int = 50, tool: str = None, txid: int = None,
                 since: str = None, until: str = None):
    """Most-recent-first entries across all journal shards."""
    d = journal_dir(col_path)
    shards = sorted(
        (os.path.join(d, f) for f in os.listdir(d) if f.endswith(".jsonl")), reverse=True
    )
    out = []
    for shard in shards:
        try:
            with open(shard, encoding="utf-8") as fh:
                lines = fh.readlines()
        except OSError:
            continue
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if tool and entry.get("tool") != tool:
                continue
            # Compare as strings: older entries may carry an integer txid.
            if txid is not None and str(entry.get("txid")) != str(txid):
                continue
            # ISO-8601 timestamps sort lexicographically within one offset.
            if since and str(entry.get("ts", "")) < since:
                continue
            if until and str(entry.get("ts", "")) > until:
                continue
            out.append(entry)
            if len(out) >= limit:
                return out
    return out
