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




