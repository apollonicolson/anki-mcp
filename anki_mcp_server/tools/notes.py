"""Note management tools."""
from typing import Optional
from .base import T, ToolError, col


@T("find-notes", "Search for notes using Anki query syntax")
def find_notes(query: str, limit: int = 100, offset: int = 0):
    """Search for notes with pagination."""
    all_notes = col().find_notes(query)
    total = len(all_notes)
    notes = all_notes[offset:offset + limit]
    return {"noteIds": notes, "count": len(notes), "total": total, "hasMore": offset + limit < total, "offset": offset, "limit": limit}


@T("get-notes-info", "Get detailed info about notes")
def get_notes_info(notes: list[int]):
    result = []
    for nid in notes:
        try:
            note = col().get_note(nid)
            model = note.note_type()
            result.append({
                "noteId": nid,
                "modelName": model["name"],
                "fields": {f["name"]: note.fields[i] for i, f in enumerate(model["flds"])},
                "tags": note.tags,
                "cards": [c.id for c in note.cards()],
            })
        except:
            result.append({"noteId": nid, "error": "Not found"})
    return {"notes": result}


@T("add-note", "Add a new note to Anki", write=True)
def add_note(
    deckName: str,
    modelName: str,
    fields: dict[str, str],
    tags: Optional[list[str]] = None,
    allowDuplicate: bool = False,
):
    from anki.notes import Note

    deck_id = col().decks.id(deckName)
    model = col().models.by_name(modelName)
    if not model:
        raise ToolError(f"Model not found: {modelName}", hint="Use list-models to list available")

    model_fields = [f["name"] for f in model["flds"]]
    missing = [f for f in model_fields if f not in fields]
    if missing:
        raise ToolError(f"Missing fields: {missing}", hint=f"Required: {model_fields}")

    note = Note(col(), model)
    note.note_type()["did"] = deck_id
    for name, value in fields.items():
        if name in model_fields:
            note[name] = value
    if tags:
        note.tags = tags

    changes = col().add_note(note, deck_id)
    if not changes or not changes.note_id:
        raise ToolError("Failed to create note")

    return {"noteId": changes.note_id, "deckName": deckName, "modelName": modelName}


@T("add-notes", "Add multiple notes at once", write=True)
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


@T("delete-notes", "Delete notes permanently", write=True)
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


@T("update-note", "Update note fields and tags", write=True)
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


@T("update-note-model", "Change note's model/note type", write=True)
def update_note_model(note_id: int, model_name: str, field_map: dict = None, card_map: dict = None):
    n = col().get_note(note_id)
    if not n:
        raise ToolError(f"Note not found: {note_id}")
    new_model = col().models.by_name(model_name)
    if not new_model:
        raise ToolError(f"Model not found: {model_name}")
    col().models.change(n.note_type(), [note_id], new_model, field_map or {}, card_map or {})
    return {"noteId": note_id, "newModel": model_name}


@T("get-note-tags", "Get tags for a specific note")
def get_note_tags(note_id: int):
    n = col().get_note(note_id)
    if not n:
        raise ToolError(f"Note not found: {note_id}")
    return {"noteId": note_id, "tags": n.tags}


@T("get-notes-mod-time", "Get modification times for notes")
def get_notes_mod_time(notes: list[int]):
    return {str(nid): col().get_note(nid).mod for nid in notes}
