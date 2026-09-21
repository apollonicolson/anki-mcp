"""Note management tools."""
from typing import Optional
from .base import T, ToolError, col


def _model_field_names(model) -> list[str]:
    return [f["name"] for f in model["flds"]]


def _fields_for_note(note) -> dict[str, str]:
    model = note.note_type()
    return {field["name"]: note.fields[i] for i, field in enumerate(model["flds"])}


def _require_model(model_name: str):
    model = col().models.by_name(model_name)
    if not model:
        raise ToolError(f"Model not found: {model_name}", hint="Use list-models to list available")
    return model


def _validate_fields(model, fields: dict[str, str], require_all: bool = True) -> list[str]:
    model_fields = _model_field_names(model)
    missing = [f for f in model_fields if f not in fields]
    if require_all and missing:
        raise ToolError(f"Missing fields: {missing}", hint=f"Required: {model_fields}")
    return model_fields


def _note_key(fields: dict[str, str], key_field: str, key_prefix: str = "") -> Optional[str]:
    value = fields.get(key_field, "")
    if not key_prefix:
        return value or None
    for line in str(value).splitlines():
        if line.startswith(key_prefix):
            return line[len(key_prefix):].strip()
    return None


def _note_row(note_id: int) -> dict:
    note = col().get_note(note_id)
    return {
        "noteId": note_id,
        "modelName": note.note_type()["name"],
        "fields": _fields_for_note(note),
        "tags": list(note.tags),
        "cards": [card.id for card in note.cards()],
    }


def find_notes(query: str, limit: int = 100, offset: int = 0):
    """Search for notes with pagination."""
    all_notes = col().find_notes(query)
    total = len(all_notes)
    notes = all_notes[offset:offset + limit]
    return {"noteIds": notes, "count": len(notes), "total": total, "hasMore": offset + limit < total, "offset": offset, "limit": limit}




def add_note(
    deckName: str,
    modelName: str,
    fields: dict[str, str],
    tags: Optional[list[str]] = None,
    allowDuplicate: bool = False,
):
    from anki.notes import Note

    deck_id = col().decks.id(deckName)
    model = _require_model(modelName)
    model_fields = _validate_fields(model, fields, require_all=True)

    note = Note(col(), model)
    note.note_type()["did"] = deck_id
    for name, value in fields.items():
        if name in model_fields:
            note[name] = value
    if tags:
        note.tags = tags

    changes = col().add_note(note, deck_id)
    note_id = getattr(changes, "note_id", None) or getattr(note, "id", None)
    if not changes or not note_id:
        raise ToolError("Failed to create note")

    return {"noteId": note_id, "deckName": deckName, "modelName": modelName}


def add_notes(notes: list[dict]) -> dict:
    results = []
    for n in notes:
        try:
            result = add_note(**n)
            results.append({"success": True, "noteId": result.get("noteId")})
        except ToolError as e:
            results.append({"success": False, "error": e.message})
        except Exception as e:
            results.append({"success": False, "error": str(e)})
    return {"results": results, "added": sum(1 for r in results if r["success"])}


@T("import-notes-file", "Add notes from a local JSON file of note dicts", write=True)
def import_notes_file(path: str, deck_name: str = None, model_name: str = None,
                      dry_run: bool = True, allow_duplicate: bool = False):
    """Bulk-add from a file so large batches never travel through the tool call.

    A book chapter is thousands of lines of JSON; inlining it in the request wastes
    the caller's context and hits response limits. The file is the payload.

    Expects a JSON list of {deckName, modelName, fields, tags}. deck_name/model_name
    override per-note values, for the common case of one deck and one notetype.
    Insertion order is preserved, so it also fixes the new-card sequence.
    """
    import json
    import os

    if not os.path.isfile(path):
        raise ToolError(f"No such file: {path}")
    with open(path, encoding="utf-8") as fh:
        batch = json.load(fh)
    if not isinstance(batch, list):
        raise ToolError("File must contain a JSON list of note objects")

    prepared = []
    for i, note in enumerate(batch):
        if not isinstance(note, dict) or "fields" not in note:
            raise ToolError(f"Entry {i} is not a note object with 'fields'")
        prepared.append({
            "deckName": deck_name or note.get("deckName"),
            "modelName": model_name or note.get("modelName"),
            "fields": note["fields"],
            "tags": note.get("tags"),
            "allowDuplicate": allow_duplicate,
        })
    missing = [i for i, n in enumerate(prepared) if not n["deckName"] or not n["modelName"]]
    if missing:
        raise ToolError(f"Entries missing deckName/modelName: {missing[:10]}")

    decks = sorted({n["deckName"] for n in prepared})
    models = sorted({n["modelName"] for n in prepared})
    if dry_run:
        first = prepared[0]
        return {"dry_run": True, "path": path, "count": len(prepared),
                "decks": decks, "models": models,
                "field_names": sorted(first["fields"]),
                "first": {k: (v[:120] + "..." if len(v) > 120 else v)
                          for k, v in first["fields"].items()},
                "hint": "re-run with dry_run=false to apply"}

    result = add_notes(prepared)
    failures = [{"index": i, "error": r.get("error")}
                for i, r in enumerate(result["results"]) if not r["success"]]
    return {"dry_run": False, "path": path, "requested": len(prepared),
            "added": result["added"], "failed": len(failures),
            "failures": failures[:20], "decks": decks, "models": models,
            "noteIds": [r.get("noteId") for r in result["results"] if r["success"]]}


@T("update-fields-file", "Bulk-fill one field on notes matched by a key field, from a JSON file", write=True)
def update_fields_file(path: str, dry_run: bool = True):
    """Fill a single field on many existing notes, matched by a stable key field.

    Built for parallel-corpus population: a whole-Bible {ref: text} map fills, say,
    the Hebrew "Text MT" field on every Logos PCE note whose "Ref." matches - one
    journaled pass, no per-note tool calls. The file carries the payload so 31k
    verses never travel through the request.

    File shape:
        {"query": "note:\\"Logos PCE\\"",   # REQUIRED scope - never the whole collection
         "match_field": "Ref.",            # key field to join on (default "Ref.")
         "field": "Text MT",               # field to fill
         "values": {"Genesis 1:1": "...", ...}}

    Reports matched / unmatched so versification gaps (e.g. Psalm numbering) surface
    as concrete unmatched refs instead of silent misses.
    """
    import json
    import os

    from . import _journal

    if not os.path.isfile(path):
        raise ToolError(f"No such file: {path}")
    doc = json.load(open(path, encoding="utf-8"))
    query = doc.get("query")
    field = doc.get("field")
    match_field = doc.get("match_field", "Ref.")
    values = doc.get("values")
    if not query:
        raise ToolError('File needs a "query" scope', hint='e.g. "query": "note:\\"Logos PCE\\""')
    if not field:
        raise ToolError('File needs a "field" to fill')
    if not isinstance(values, dict) or not values:
        raise ToolError('File needs "values": {key: text}')

    # Map key-field value -> (note_id, field_index) over the scoped notes only.
    key_to_note: dict[str, tuple] = {}
    ambiguous = 0
    for nid in col().find_notes(query):
        note = col().get_note(nid)
        names = [f["name"] for f in note.note_type()["flds"]]
        if match_field not in names or field not in names:
            continue
        k = note.fields[names.index(match_field)]
        if k in key_to_note:
            ambiguous += 1
        else:
            key_to_note[k] = (nid, names.index(field))

    matched = {k: v for k, v in values.items() if k in key_to_note}
    unmatched = [k for k in values if k not in key_to_note]
    summary = {"field": field, "match_field": match_field, "query": query,
               "provided": len(values), "matched": len(matched),
               "unmatched": len(unmatched), "unmatched_sample": unmatched[:25],
               "ambiguous_keys_in_scope": ambiguous}
    if dry_run:
        summary["dry_run"] = True
        summary["hint"] = "re-run with dry_run=false to apply"
        return summary

    _journal.declare_targets(col(), [key_to_note[k][0] for k in matched])
    updated = 0
    for k, val in matched.items():
        nid, fidx = key_to_note[k]
        note = col().get_note(nid)
        note.fields[fidx] = str(val)
        col().update_note(note)
        updated += 1
    summary["dry_run"] = False
    summary["updated"] = updated
    return summary


def delete_notes(notes: list[int], confirmDeletion: bool = False):
    if not confirmDeletion:
        raise ToolError("Must confirm deletion", hint="Set confirmDeletion=true")
    col().remove_notes(notes)
    return {"deleted": len(notes)}


@T("delete-empty-notes", "Delete notes with no cards", write=True)
def delete_empty_notes():
    report = col().get_empty_cards()
    count = len(report.notes)
    if count > 0:
        col().remove_notes_by_card([r.card_id for r in report.notes])
    return {"removed": count}


@T("can-add-notes", "Check if notes can be added without duplicates")
def can_add_notes(notes: list[dict], include_errors: bool = False):
    results = []
    for n in notes:
        model = col().models.by_name(n.get("modelName", ""))
        if not model:
            results.append({"canAdd": False, "error": "Model not found"} if include_errors else False)
            continue
        fields = n.get("fields", {})
        first_field = list(fields.values())[0] if fields else ""
        dupes = col().find_notes(f'"{first_field}"')
        if dupes:
            results.append({"canAdd": False, "error": "Duplicate"} if include_errors else False)
        else:
            results.append({"canAdd": True} if include_errors else True)
    return {"results": results, "count": len(results)}


def upsert_notes(
    notes: list[dict],
    key_field: str,
    key_prefix: str = "",
    query: str = "",
    dry_run: bool = True,
    update_existing: bool = True,
    add_missing: bool = True,
):
    """Upsert notes by a stable key extracted from a note field.

    Args:
        notes: Anki note maps with deckName, modelName, fields, and optional tags.
        key_field: Field containing the stable key, e.g. "Notes".
        key_prefix: Optional line prefix, e.g. "rep:".
        query: Optional search limiting existing notes considered for matches.
        dry_run: When true, return a plan without writing.
        update_existing: Update fields/tags of notes with one matching key.
        add_missing: Add notes with no matching key.
    """
    existing_query = query or ""
    existing_ids = col().find_notes(existing_query) if existing_query else []
    existing_by_key: dict[str, list[int]] = {}
    for note_id in existing_ids:
        row = _note_row(note_id)
        key = _note_key(row["fields"], key_field, key_prefix)
        if key:
            existing_by_key.setdefault(key, []).append(note_id)

    results = []
    changed = {"added": 0, "updated": 0, "skipped": 0, "duplicates": 0, "errors": 0}
    for item in notes:
        fields = item.get("fields", {})
        key = _note_key(fields, key_field, key_prefix)
        if not key:
            results.append({"success": False, "action": "error", "error": "Missing key", "key": None})
            changed["errors"] += 1
            continue

        matches = existing_by_key.get(key, [])
        if len(matches) > 1:
            results.append({"success": False, "action": "duplicate", "key": key, "noteIds": matches})
            changed["duplicates"] += 1
            continue

        try:
            model = _require_model(item.get("modelName", ""))
            model_fields = _validate_fields(model, fields, require_all=True)
            if matches:
                note_id = matches[0]
                if not update_existing:
                    results.append({"success": True, "action": "skip-existing", "key": key, "noteId": note_id})
                    changed["skipped"] += 1
                    continue
                if dry_run:
                    results.append({"success": True, "action": "update", "dryRun": True, "key": key, "noteId": note_id})
                    changed["updated"] += 1
                    continue
                note = col().get_note(note_id)
                for name, value in fields.items():
                    if name in model_fields:
                        note[name] = value
                if "tags" in item:
                    note.tags = item["tags"]
                col().update_note(note)
                results.append({"success": True, "action": "update", "key": key, "noteId": note_id})
                changed["updated"] += 1
            else:
                if not add_missing:
                    results.append({"success": True, "action": "skip-missing", "key": key})
                    changed["skipped"] += 1
                    continue
                if dry_run:
                    results.append({"success": True, "action": "add", "dryRun": True, "key": key})
                    changed["added"] += 1
                    continue
                result = add_note(**item)
                note_id = result.get("noteId")
                results.append({"success": True, "action": "add", "key": key, "noteId": note_id})
                existing_by_key.setdefault(key, []).append(note_id)
                changed["added"] += 1
        except ToolError as e:
            results.append({"success": False, "action": "error", "key": key, "error": e.message})
            changed["errors"] += 1
        except Exception as e:
            results.append({"success": False, "action": "error", "key": key, "error": str(e)})
            changed["errors"] += 1

    return {
        "dryRun": dry_run,
        "query": existing_query,
        "keyField": key_field,
        "keyPrefix": key_prefix,
        "count": len(notes),
        **changed,
        "results": results,
    }


def update_note(note: dict):
    nid = note.get("id")
    n = col().get_note(nid)
    if not n:
        raise ToolError(f"Note not found: {nid}")
    for field, value in note.get("fields", {}).items():
        if field in [f["name"] for f in n.note_type()["flds"]]:
            n[field] = value
    if "tags" in note:
        n.tags = note["tags"]
    col().update_note(n)
    return {"noteId": nid, "updated": True}


def update_note_model(note_id: int, model_name: str, field_map: dict = None, card_map: dict = None):
    n = col().get_note(note_id)
    if not n:
        raise ToolError(f"Note not found: {note_id}")
    new_model = col().models.by_name(model_name)
    if not new_model:
        raise ToolError(f"Model not found: {model_name}")
    col().models.change(n.note_type(), [note_id], new_model, field_map or {}, card_map or {})
    return {"noteId": note_id, "newModel": model_name}




