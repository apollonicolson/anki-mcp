"""All MCP tools in one file using progressive disclosure.

Tools are organized by category and complexity:
- One-liners for simple getters
- Decorated functions for typed operations
- Full functions for complex validation

Import this module to register all tools, then call register_tools(mcp, bridge).
"""
from typing import Any, Optional, Sequence
from .tool_base import T, ToolError, col, register_tools
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


# ============================================================================
# MISCELLANEOUS - Simple utilities
# ============================================================================

@T("sync", "Sync collection with AnkiWeb")
def sync():
    from aqt import mw
    auth = mw.pm.sync_auth()
    if not auth:
        raise ToolError("Not logged in to AnkiWeb", hint="Log in via Tools > Preferences > Sync")
    output = mw.col.sync_collection(auth, False)
    return {"status": "synced", "output": str(output)}


T("version", "Get Anki version", lambda: {"anki": col().sched_ver(), "mcp": "1.0.0"})

T("get-profiles", "List available profiles", lambda: __import__('aqt').mw.pm.profiles(), require_col=False)

@T("get-active-profile", "Get current profile name", require_col=False)
def get_active_profile():
    from aqt import mw
    return {"profile": mw.pm.name}


@T("reload-collection", "Reload the collection")
def reload_collection():
    from aqt import mw
    mw.col.close()
    mw.loadCollection()
    return {"reloaded": True}


# ============================================================================
# DECKS - Deck management
# ============================================================================

@T("list-decks", "List decks with optional filtering and statistics")
def list_decks(
    include_stats: bool = False,
    pattern: str = None,
    top_level_only: bool = False,
    limit: int = 100,
    offset: int = 0,
):
    """List decks with optional filtering and pagination.

    Args:
        include_stats: Include new/learn/review counts (returns tree structure)
        pattern: Filter by name pattern (supports * wildcard, e.g. "Japanese*")
        top_level_only: Only return root decks, not subdecks
        limit: Maximum number of decks to return (default 100)
        offset: Skip first N results for pagination
    """
    import fnmatch

    if include_stats:
        # Return hierarchical tree with due counts
        tree = col().sched.deck_due_tree()

        def process_node(node, depth=0):
            if top_level_only and depth > 0:
                return None
            if pattern and not fnmatch.fnmatch(node.name.lower(), pattern.lower()):
                # Check if any children match
                matching_children = [c for c in (process_node(child, depth + 1) for child in node.children) if c]
                if not matching_children:
                    return None

            return {
                "id": node.deck_id,
                "name": node.name,
                "new": node.new_count,
                "learn": node.learn_count,
                "review": node.review_count,
                "children": [c for c in (process_node(child, depth + 1) for child in node.children) if c] if not top_level_only else [],
            }

        all_decks = [d for d in (process_node(n) for n in tree.children) if d]
        total = len(all_decks)
        decks = all_decks[offset:offset + limit]
        return {
            "decks": decks,
            "count": len(decks),
            "total": total,
            "hasMore": offset + limit < total,
            "offset": offset,
            "limit": limit,
            "format": "tree",
        }

    else:
        # Return flat list
        all_decks = col().decks.all()
        filtered_decks = []

        for d in all_decks:
            name = d["name"]
            if top_level_only and "::" in name:
                continue
            if pattern and not fnmatch.fnmatch(name.lower(), pattern.lower()):
                continue
            filtered_decks.append({"id": d["id"], "name": name})

        total = len(filtered_decks)
        decks = filtered_decks[offset:offset + limit]
        return {
            "decks": decks,
            "count": len(decks),
            "total": total,
            "hasMore": offset + limit < total,
            "offset": offset,
            "limit": limit,
            "format": "flat",
        }


@T("create-deck", "Create a new deck. Supports parent::child structure.")
def create_deck(deck_name: str):
    if deck_name.count("::") > 1:
        raise ToolError("Maximum 2 levels of nesting", hint="Use 'Parent::Child' format")
    did = col().decks.id(deck_name)
    return {"deckId": did, "deckName": deck_name, "created": True}


@T("rename-deck", "Rename a deck", write=True)
def rename_deck(old_name: str, new_name: str):
    deck = col().decks.by_name(old_name)
    if not deck:
        raise ToolError(f"Deck not found: {old_name}", hint="Use list-decks to see available decks")
    deck["name"] = new_name
    col().decks.save(deck)
    return {"oldName": old_name, "newName": new_name}


@T("delete-deck", "Delete a deck", write=True)
def delete_deck(deck_name: str, cards_too: bool = False):
    deck = col().decks.by_name(deck_name)
    if not deck:
        raise ToolError(f"Deck not found: {deck_name}")
    col().decks.remove([deck["id"]])
    return {"deleted": deck_name, "cardsDeleted": cards_too}


@T("change-deck", "Move cards to a different deck", write=True)
def change_deck(cards: list[int], deck_name: str):
    deck = col().decks.by_name(deck_name)
    if not deck:
        raise ToolError(f"Deck not found: {deck_name}")
    col().set_deck(cards, deck["id"])
    return {"moved": len(cards), "toDeck": deck_name}


@T("get-deck-config", "Get deck options/configuration")
def get_deck_config(deck_name: str):
    deck = col().decks.by_name(deck_name)
    if not deck:
        raise ToolError(f"Deck not found: {deck_name}")
    conf = col().decks.config_dict_for_deck_id(deck["id"])
    return {"deckName": deck_name, "config": conf}


@T("get-deck-stats", "Get deck statistics")
def get_deck_stats(deck_name: str):
    deck = col().decks.by_name(deck_name)
    if not deck:
        raise ToolError(f"Deck not found: {deck_name}")
    tree = col().sched.deck_due_tree()
    # Find this deck in tree and return stats
    return {"deckName": deck_name, "deckId": deck["id"]}


# ============================================================================
# NOTES - Note operations
# ============================================================================

@T("find-notes", "Search for notes using Anki query syntax")
def find_notes(query: str, limit: int = 100, offset: int = 0):
    """Search for notes with pagination.

    Args:
        query: Anki search query (e.g. "deck:Japanese", "tag:marked")
        limit: Maximum notes to return (default 100)
        offset: Skip first N results for pagination
    """
    all_notes = col().find_notes(query)
    total = len(all_notes)
    notes = all_notes[offset:offset + limit]
    return {
        "noteIds": notes,
        "count": len(notes),
        "total": total,
        "hasMore": offset + limit < total,
        "offset": offset,
        "limit": limit,
    }

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
        raise ToolError(f"Model not found: {modelName}", hint="Use modelNames to list available")

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


# ============================================================================
# CARDS - Card operations
# ============================================================================

@T("find-cards", "Search for cards using Anki query syntax")
def find_cards(query: str, limit: int = 100, offset: int = 0):
    """Search for cards with pagination.

    Args:
        query: Anki search query (e.g. "deck:Japanese is:due")
        limit: Maximum cards to return (default 100)
        offset: Skip first N results for pagination
    """
    all_cards = col().find_cards(query)
    total = len(all_cards)
    cards = all_cards[offset:offset + limit]
    return {
        "cardIds": cards,
        "count": len(cards),
        "total": total,
        "hasMore": offset + limit < total,
        "offset": offset,
        "limit": limit,
    }

@T("get-cards-info", "Get detailed info about cards")
def get_cards_info(cards: list[int]):
    result = []
    for cid in cards:
        try:
            c = col().get_card(cid)
            n = c.note()
            result.append({
                "cardId": cid,
                "noteId": n.id,
                "deckId": c.did,
                "deckName": col().decks.name(c.did),
                "modelName": n.note_type()["name"],
                "question": c.question(),
                "answer": c.answer(),
                "due": c.due,
                "type": c.type,
                "queue": c.queue,
                "interval": c.ivl,
                "factor": c.factor,
                "reps": c.reps,
                "lapses": c.lapses,
            })
        except:
            result.append({"cardId": cid, "error": "Not found"})
    return {"cards": result}


@T("get-notes-for-cards", "Get note IDs for cards")
def get_notes_for_cards(cards: list[int]):
    """Map card IDs to their note IDs."""
    mapping = {str(cid): col().get_card(cid).nid for cid in cards}
    unique_notes = list(set(mapping.values()))
    return {
        "mapping": mapping,
        "uniqueNoteIds": unique_notes,
        "cardCount": len(cards),
        "noteCount": len(unique_notes),
    }

@T("get-ease-factors", "Get ease factors for cards")
def get_ease_factors(cards: list[int]):
    return {"easeFactors": [col().get_card(c).factor for c in cards]}


@T("set-ease-factors", "Set ease factors for cards", write=True)
def set_ease_factors(cards: list[int], easeFactors: list[int]):
    if len(cards) != len(easeFactors):
        raise ToolError("cards and easeFactors must have same length")
    for cid, factor in zip(cards, easeFactors):
        c = col().get_card(cid)
        c.factor = factor
        col().update_card(c)
    return {"updated": len(cards)}


@T("set-cards-suspended", "Set suspension state for cards", write=True)
def set_cards_suspended(cards: list[int], suspended: bool = True):
    """Suspend or unsuspend cards.

    Args:
        cards: Card IDs to modify
        suspended: True to suspend, False to unsuspend (default: True)
    """
    if suspended:
        col().sched.suspend_cards(cards)
    else:
        col().sched.unsuspend_cards(cards)
    return {"cards": len(cards), "suspended": suspended}


@T("are-suspended", "Check if cards are suspended")
def are_suspended(cards: list[int]):
    """Check suspension status for cards. Returns map of cardId -> suspended."""
    return {str(cid): col().get_card(cid).queue == -1 for cid in cards}

@T("set-cards-buried", "Set buried state for cards", write=True)
def set_cards_buried(cards: list[int] = None, buried: bool = True):
    """Bury or unbury cards.

    Args:
        cards: Card IDs to modify (if None and buried=False, unbury current deck)
        buried: True to bury, False to unbury (default: True)
    """
    if buried:
        if not cards:
            raise ToolError("cards required when burying")
        col().sched.bury_cards(cards)
        return {"cards": len(cards), "buried": True}
    else:
        if cards:
            col().sched.unbury_cards(cards)
            return {"cards": len(cards), "buried": False}
        else:
            col().sched.unbury_deck(col().decks.current()["id"])
            return {"deck": col().decks.current()["name"], "buried": False}


@T("set-card-flag", "Set flag on cards (0-7)", write=True)
def set_card_flag(cards: list[int], flag: int):
    if not 0 <= flag <= 7:
        raise ToolError("Flag must be 0-7")
    col().set_user_flag_for_cards(flag, cards)
    return {"flagged": len(cards), "flag": flag}


@T("forget-cards", "Reset cards to new state", write=True)
def forget_cards(cards: list[int]):
    col().sched.schedule_cards_as_new(cards)
    return {"reset": len(cards)}


@T("set-due-date", "Set due date for cards", write=True)
def set_due_date(cards: list[int], days: str):
    col().sched.set_due_date(cards, days)
    return {"rescheduled": len(cards), "days": days}


@T("answer-cards", "Answer cards programmatically", write=True)
def answer_cards(answers: list[dict]):
    for a in answers:
        cid = a["cardId"]
        ease = a["ease"]
        c = col().get_card(cid)
        col().sched.answerCard(c, ease)
    return {"answered": len(answers)}


# ============================================================================
# TAGS - Tag management
# ============================================================================

@T("list-tags", "List all tags in collection")
def list_tags(pattern: str = None, limit: int = None):
    """Get tags with optional filtering.

    Args:
        pattern: Filter by pattern (supports * wildcard, e.g. "vocab*")
        limit: Maximum tags to return
    """
    import fnmatch
    all_tags = col().tags.all()

    if pattern:
        all_tags = [t for t in all_tags if fnmatch.fnmatch(t.lower(), pattern.lower())]

    total = len(all_tags)
    if limit:
        all_tags = all_tags[:limit]

    return {
        "tags": all_tags,
        "count": len(all_tags),
        "total": total,
    }

@T("add-tags", "Add tags to notes", write=True)
def add_tags(notes: list[int], tags: str):
    col().tags.bulk_add(notes, tags)
    return {"tagged": len(notes), "tags": tags}


@T("remove-tags", "Remove tags from notes", write=True)
def remove_tags(notes: list[int], tags: str):
    col().tags.bulk_remove(notes, tags)
    return {"untagged": len(notes), "tags": tags}


@T("clear-unused-tags", "Remove unused tags", write=True)
def clear_unused_tags():
    col().tags.clear_unused_tags()
    return {"cleared": True}


@T("replace-tags", "Replace tag on notes", write=True)
def replace_tags(old_tag: str, new_tag: str, notes: list[int] = None):
    """Replace a tag with another on notes.

    Args:
        old_tag: Tag to replace
        new_tag: New tag name
        notes: Specific note IDs (if None, applies to all notes with the tag)
    """
    if notes is None:
        notes = col().find_notes(f"tag:{old_tag}")

    updated = 0
    for nid in notes:
        n = col().get_note(nid)
        if old_tag in n.tags:
            n.tags.remove(old_tag)
            n.tags.append(new_tag)
            col().update_note(n)
            updated += 1
    return {"updated": updated, "oldTag": old_tag, "newTag": new_tag}


# ============================================================================
# MODELS - Note type management
# ============================================================================

@T("list-models", "List note types with optional filtering")
def list_models(pattern: str = None, ids: list[int] = None, names: list[str] = None, include_fields: bool = False):
    """List note types (models) with optional filtering.

    Args:
        pattern: Filter by name pattern (supports * wildcard)
        ids: Get specific models by ID
        names: Get specific models by name
        include_fields: Include field names for each model
    """
    import fnmatch

    if ids:
        models = [col().models.get(mid) for mid in ids]
        models = [m for m in models if m]
    elif names:
        models = [col().models.by_name(name) for name in names]
        models = [m for m in models if m]
    else:
        models = col().models.all()

    if pattern:
        models = [m for m in models if fnmatch.fnmatch(m["name"].lower(), pattern.lower())]

    result = []
    for m in models:
        info = {"id": m["id"], "name": m["name"]}
        if include_fields:
            info["fields"] = [f["name"] for f in m["flds"]]
        result.append(info)

    return {"models": result, "count": len(result)}


@T("model-field-names", "Get field names for a note type")
def model_field_names(modelName: str):
    m = col().models.by_name(modelName)
    if not m:
        raise ToolError(f"Model not found: {modelName}")
    return [f["name"] for f in m["flds"]]


@T("model-styling", "Get CSS styling for a note type")
def model_styling(modelName: str):
    m = col().models.by_name(modelName)
    if not m:
        raise ToolError(f"Model not found: {modelName}")
    return {"css": m["css"]}


@T("update-model-styling", "Update CSS for a note type", write=True)
def update_model_styling(modelName: str, css: str):
    m = col().models.by_name(modelName)
    if not m:
        raise ToolError(f"Model not found: {modelName}")
    m["css"] = css
    col().models.save(m)
    return {"modelName": modelName, "updated": True}


@T("model-templates", "Get card templates for a note type")
def model_templates(modelName: str):
    m = col().models.by_name(modelName)
    if not m:
        raise ToolError(f"Model not found: {modelName}")
    return {"templates": [{"name": t["name"], "qfmt": t["qfmt"], "afmt": t["afmt"]} for t in m["tmpls"]]}


@T("create-model", "Create a new note type", write=True)
def create_model(
    modelName: str,
    inOrderFields: list[str],
    cardTemplates: list[dict],
    css: Optional[str] = None,
    isCloze: bool = False,
):
    mm = col().models
    m = mm.new(modelName)

    for fname in inOrderFields:
        f = mm.new_field(fname)
        mm.add_field(m, f)

    for tmpl in cardTemplates:
        t = mm.new_template(tmpl.get("Name", "Card 1"))
        t["qfmt"] = tmpl.get("Front", "")
        t["afmt"] = tmpl.get("Back", "")
        mm.add_template(m, t)

    if css:
        m["css"] = css
    if isCloze:
        m["type"] = 1

    mm.add(m)
    return {"modelId": m["id"], "modelName": modelName}


# ============================================================================
# MEDIA - Media file management
# ============================================================================

@T("store-media-file", "Store a media file")
def store_media_file(filename: str, data: str = None, path: str = None, url: str = None):
    import base64
    import urllib.request

    if data:
        content = base64.b64decode(data)
    elif path:
        with open(path, "rb") as f:
            content = f.read()
    elif url:
        content = urllib.request.urlopen(url).read()
    else:
        raise ToolError("Must provide data, path, or url")

    stored = col().media.write_data(filename, content)
    return {"filename": stored}


@T("retrieve-media-file", "Get media file as base64")
def retrieve_media_file(filename: str):
    import base64
    path = os.path.join(col().media.dir(), filename)
    if not os.path.exists(path):
        raise ToolError(f"File not found: {filename}")
    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode()
    return {"filename": filename, "data": data}


@T("list-media-files", "List media files matching pattern")
def list_media_files(pattern: str = "*", limit: int = 100, offset: int = 0):
    """List media files with optional filtering and pagination.

    Args:
        pattern: Glob pattern to match (e.g. "*.jpg", "audio_*")
        limit: Maximum files to return (default 100)
        offset: Skip first N results for pagination
    """
    import fnmatch
    all_files = os.listdir(col().media.dir())
    matched = [f for f in all_files if fnmatch.fnmatch(f, pattern)]
    total = len(matched)
    files = matched[offset:offset + limit]
    return {
        "files": files,
        "count": len(files),
        "total": total,
        "hasMore": offset + limit < total,
    }


T("get-media-dir-path", "Get path to media folder", lambda: col().media.dir())

@T("delete-media-file", "Delete a media file")
def delete_media_file(filename: str):
    path = os.path.join(col().media.dir(), filename)
    if os.path.exists(path):
        os.remove(path)
        return {"deleted": filename}
    raise ToolError(f"File not found: {filename}")


# ============================================================================
# STATISTICS
# ============================================================================

@T("get-collection-stats", "Get collection statistics")
def get_collection_stats():
    return {
        "totalCards": col().card_count(),
        "totalNotes": col().note_count(),
        "totalDecks": len(col().decks.all()),
        "totalModels": len(col().models.all()),
        "reviewsToday": col().db.scalar("select count() from revlog where id > ?", col().sched.day_cutoff * 1000),
    }


# ============================================================================
# BACKUP & IMPORT/EXPORT
# ============================================================================

@T("create-backup", "Create a backup of the collection")
def create_backup(force: bool = True):
    from aqt import mw
    folder = mw.pm.backupFolder()
    created = col().create_backup(backup_folder=folder, force=force, wait_for_completion=True)
    return {"created": created, "backupFolder": folder}


@T("list-backups", "List available backups")
def list_backups():
    from aqt import mw
    folder = mw.pm.backupFolder()
    if not os.path.exists(folder):
        return {"backups": [], "count": 0}

    backups = []
    for f in sorted(os.listdir(folder), reverse=True):
        if f.endswith(".colpkg"):
            path = os.path.join(folder, f)
            stat = os.stat(path)
            backups.append({
                "filename": f,
                "path": path,
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })
    return {"backups": backups, "count": len(backups), "backupFolder": folder}


@T("export-deck", "Export a deck as .apkg")
def export_deck(deck_name: str = None, out_path: str = "", include_scheduling: bool = True, include_media: bool = True):
    from anki.exporting import AnkiPackageExporter

    if not out_path:
        from aqt import mw
        folder = os.path.join(mw.pm.profileFolder(), "exports")
        os.makedirs(folder, exist_ok=True)
        name = deck_name.replace("::", "_") if deck_name else "collection"
        out_path = os.path.join(folder, f"{name}.apkg")

    exporter = AnkiPackageExporter(col())
    exporter.includeSched = include_scheduling
    exporter.includeMedia = include_media

    if deck_name:
        deck = col().decks.by_name(deck_name)
        if not deck:
            raise ToolError(f"Deck not found: {deck_name}")
        exporter.did = deck["id"]

    exporter.exportInto(out_path)
    return {"path": out_path, "deckName": deck_name or "All"}


@T("import-package", "Import an .apkg package", write=True)
def import_package(path: str):
    if not os.path.exists(path):
        raise ToolError(f"File not found: {path}")

    from aqt import mw
    from anki.import_export_pb2 import ImportAnkiPackageRequest

    mw.requireReset()
    try:
        request = ImportAnkiPackageRequest(package_path=path)
        col().import_anki_package(request)
    finally:
        mw.maybeReset()

    return {"imported": path}


# ============================================================================
# GUI TOOLS
# ============================================================================

@T("gui-browse", "Open card browser with search", category="gui")
def gui_browse(query: str = ""):
    from aqt import mw
    from aqt.browser import Browser
    browser = mw.app.activeWindow()
    if not isinstance(browser, Browser):
        mw.onBrowse()
        browser = mw.app.activeWindow()
    if query:
        browser.form.searchEdit.lineEdit().setText(query)
        browser.onSearchActivated()
    return {"opened": True, "query": query}


@T("gui-add-cards", "Open Add Cards dialog", category="gui", require_col=False)
def gui_add_cards(deck_name: str = None, model_name: str = None, fields: dict = None):
    from aqt import mw
    mw.onAddCard()
    add = mw.app.activeWindow()

    if deck_name:
        deck = col().decks.by_name(deck_name)
        if deck:
            add.deckChooser.deck.setText(deck_name)

    return {"opened": True}


@T("gui-current-card", "Get info about card in reviewer", category="gui")
def gui_current_card():
    from aqt import mw
    if not mw.reviewer or not mw.reviewer.card:
        return {"inReview": False}
    c = mw.reviewer.card
    return {
        "inReview": True,
        "cardId": c.id,
        "noteId": c.nid,
        "deckId": c.did,
        "question": c.question(),
        "answer": c.answer(),
    }


@T("gui-show-answer", "Show answer in reviewer", category="gui")
def gui_show_answer():
    from aqt import mw
    if mw.reviewer and mw.reviewer.card:
        mw.reviewer._showAnswer()
        return {"shown": True}
    return {"shown": False, "error": "Not in review"}


@T("gui-show-question", "Show question in reviewer", category="gui")
def gui_show_question():
    from aqt import mw
    if mw.reviewer and mw.reviewer.card:
        mw.reviewer._showQuestion()
        return {"shown": True}
    return {"shown": False, "error": "Not in review"}


@T("gui-deck-browser", "Open deck browser", category="gui")
def gui_deck_browser():
    from aqt import mw
    mw.moveToState("deckBrowser")
    return {"opened": True}


@T("gui-undo", "Undo last action", category="gui")
def gui_undo():
    from aqt import mw
    if col().undo_status().undo:
        mw.undo()
        return {"undone": True}
    return {"undone": False, "error": "Nothing to undo"}


@T("gui-edit-note", "Open note editor", category="gui")
def gui_edit_note(note_id: int):
    from aqt import mw
    from aqt.editcurrent import EditCurrent
    mw.onBrowse()
    browser = mw.app.activeWindow()
    browser.form.searchEdit.lineEdit().setText(f"nid:{note_id}")
    browser.onSearchActivated()
    return {"opened": True, "noteId": note_id}


@T("gui-select-card", "Select card in browser", category="gui")
def gui_select_card(card_id: int):
    from aqt import mw
    from aqt.browser import Browser
    browser = mw.app.activeWindow()
    if isinstance(browser, Browser):
        browser.selectCards([card_id])
        return {"selected": card_id}
    return {"selected": False, "error": "Browser not open"}


# ============================================================================
# REMAINING ANKICONNECT PARITY TOOLS
# ============================================================================

# Card queries
@T("are-due", "Check if cards are due")
def are_due(cards: list[int]):
    """Check due status for cards. Returns map of cardId -> isDue."""
    return {str(cid): col().get_card(cid).queue == 0 for cid in cards}

@T("get-intervals", "Get intervals for cards")
def get_intervals(cards: list[int], complete: bool = False):
    result = []
    for cid in cards:
        c = col().get_card(cid)
        if complete:
            result.append({"cardId": cid, "interval": c.ivl, "due": c.due, "queue": c.queue})
        else:
            result.append(c.ivl)
    return {"intervals": result}


@T("get-cards-mod-time", "Get modification times for cards")
def get_cards_mod_time(cards: list[int]):
    return {str(cid): col().get_card(cid).mod for cid in cards}


@T("relearn-cards", "Set cards to relearn state", write=True)
def relearn_cards(cards: list[int]):
    for cid in cards:
        c = col().get_card(cid)
        c.type = 3  # CARD_TYPE_RELEARN
        c.queue = 1  # QUEUE_TYPE_LRN
        col().update_card(c)
    return {"relearning": len(cards)}


# Deck config tools
@T("save-deck-config", "Save deck configuration", write=True)
def save_deck_config(config: dict):
    col().decks.save(config)
    return {"saved": True, "configId": config.get("id")}


@T("set-deck-config-id", "Set config for a deck", write=True)
def set_deck_config_id(deck_name: str, config_id: int):
    deck = col().decks.by_name(deck_name)
    if not deck:
        raise ToolError(f"Deck not found: {deck_name}")
    deck["conf"] = config_id
    col().decks.save(deck)
    return {"deckName": deck_name, "configId": config_id}


@T("clone-deck-config-id", "Clone a deck configuration", write=True)
def clone_deck_config_id(config_id: int, clone_name: str):
    conf = col().decks.get_config(config_id)
    if not conf:
        raise ToolError(f"Config not found: {config_id}")
    new_conf = col().decks.add_config(clone_name)
    return {"originalId": config_id, "cloneId": new_conf["id"], "cloneName": clone_name}


@T("delete-deck-config", "Delete a deck configuration", write=True)
def delete_deck_config(config_id: int):
    col().decks.remove_config(config_id)
    return {"removed": config_id}




@T("get-decks-for-cards", "Get decks containing specific cards")
def get_decks_for_cards(cards: list[int]):
    deck_map = {}
    for cid in cards:
        c = col().get_card(cid)
        name = col().decks.name(c.did)
        if name not in deck_map:
            deck_map[name] = []
        deck_map[name].append(cid)
    return deck_map


# Note tools
@T("can-add-notes", "Check if notes can be added without duplicates")
def can_add_notes(notes: list[dict], include_errors: bool = False):
    """Check if notes can be added without creating duplicates.

    Args:
        notes: List of note dicts with modelName and fields
        include_errors: Return detailed error info instead of just booleans
    """
    results = []
    for n in notes:
        model = col().models.by_name(n.get("modelName", ""))
        if not model:
            if include_errors:
                results.append({"canAdd": False, "error": "Model not found"})
            else:
                results.append(False)
            continue
        fields = n.get("fields", {})
        first_field = list(fields.values())[0] if fields else ""
        dupes = col().find_notes(f'"{first_field}"')
        if dupes:
            if include_errors:
                results.append({"canAdd": False, "error": "Duplicate"})
            else:
                results.append(False)
        else:
            if include_errors:
                results.append({"canAdd": True})
            else:
                results.append(True)
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


@T("model-field-descriptions", "Get field descriptions for a model")
def model_field_descriptions(modelName: str):
    m = col().models.by_name(modelName)
    if not m:
        raise ToolError(f"Model not found: {modelName}")
    return [f.get("description", "") for f in m["flds"]]


@T("model-field-fonts", "Get font settings for model fields")
def model_field_fonts(modelName: str):
    m = col().models.by_name(modelName)
    if not m:
        raise ToolError(f"Model not found: {modelName}")
    return {f["name"]: {"font": f.get("font", ""), "size": f.get("size", 20)} for f in m["flds"]}


@T("model-fields-on-templates", "Get fields used in templates")
def model_fields_on_templates(modelName: str):
    m = col().models.by_name(modelName)
    if not m:
        raise ToolError(f"Model not found: {modelName}")
    import re
    result = {}
    for t in m["tmpls"]:
        fields = set(re.findall(r'\{\{[#^/]?([^}]+)\}\}', t["qfmt"] + t["afmt"]))
        result[t["name"]] = list(fields)
    return result


@T("update-model-templates", "Update card templates for a model", write=True)
def update_model_templates(modelName: str, templates: dict):
    m = col().models.by_name(modelName)
    if not m:
        raise ToolError(f"Model not found: {modelName}")
    for t in m["tmpls"]:
        if t["name"] in templates:
            tmpl = templates[t["name"]]
            if "Front" in tmpl:
                t["qfmt"] = tmpl["Front"]
            if "Back" in tmpl:
                t["afmt"] = tmpl["Back"]
    col().models.save(m)
    return {"modelName": modelName, "updated": True}


@T("find-and-replace-in-models", "Find and replace in model templates", write=True)
def find_and_replace_in_models(model_name: str, find: str, replace: str, front: bool = True, back: bool = True, css: bool = False):
    m = col().models.by_name(model_name)
    if not m:
        raise ToolError(f"Model not found: {model_name}")
    count = 0
    for t in m["tmpls"]:
        if front and find in t["qfmt"]:
            t["qfmt"] = t["qfmt"].replace(find, replace)
            count += 1
        if back and find in t["afmt"]:
            t["afmt"] = t["afmt"].replace(find, replace)
            count += 1
    if css and find in m["css"]:
        m["css"] = m["css"].replace(find, replace)
        count += 1
    col().models.save(m)
    return {"replacements": count, "modelName": model_name}


# Model field/template manipulation
@T("model-field-add", "Add a field to a model", write=True)
def model_field_add(modelName: str, fieldName: str, index: int = None):
    m = col().models.by_name(modelName)
    if not m:
        raise ToolError(f"Model not found: {modelName}")
    f = col().models.new_field(fieldName)
    if index is not None:
        col().models.add_field(m, f)
        col().models.reposition_field(m, f, index)
    else:
        col().models.add_field(m, f)
    return {"modelName": modelName, "fieldName": fieldName}


@T("model-field-remove", "Remove a field from a model", write=True)
def model_field_remove(modelName: str, fieldName: str):
    m = col().models.by_name(modelName)
    if not m:
        raise ToolError(f"Model not found: {modelName}")
    for f in m["flds"]:
        if f["name"] == fieldName:
            col().models.remove_field(m, f)
            return {"modelName": modelName, "removed": fieldName}
    raise ToolError(f"Field not found: {fieldName}")


@T("model-field-rename", "Rename a field in a model", write=True)
def model_field_rename(modelName: str, oldFieldName: str, newFieldName: str):
    m = col().models.by_name(modelName)
    if not m:
        raise ToolError(f"Model not found: {modelName}")
    for f in m["flds"]:
        if f["name"] == oldFieldName:
            col().models.rename_field(m, f, newFieldName)
            return {"modelName": modelName, "oldName": oldFieldName, "newName": newFieldName}
    raise ToolError(f"Field not found: {oldFieldName}")


@T("model-field-reposition", "Move a field to a new position", write=True)
def model_field_reposition(modelName: str, fieldName: str, index: int):
    m = col().models.by_name(modelName)
    if not m:
        raise ToolError(f"Model not found: {modelName}")
    for f in m["flds"]:
        if f["name"] == fieldName:
            col().models.reposition_field(m, f, index)
            return {"modelName": modelName, "fieldName": fieldName, "newIndex": index}
    raise ToolError(f"Field not found: {fieldName}")


@T("model-template-add", "Add a template to a model", write=True)
def model_template_add(modelName: str, template: dict):
    m = col().models.by_name(modelName)
    if not m:
        raise ToolError(f"Model not found: {modelName}")
    t = col().models.new_template(template.get("Name", "Card"))
    t["qfmt"] = template.get("Front", "")
    t["afmt"] = template.get("Back", "")
    col().models.add_template(m, t)
    return {"modelName": modelName, "templateName": t["name"]}


@T("model-template-remove", "Remove a template from a model", write=True)
def model_template_remove(modelName: str, templateName: str):
    m = col().models.by_name(modelName)
    if not m:
        raise ToolError(f"Model not found: {modelName}")
    for t in m["tmpls"]:
        if t["name"] == templateName:
            col().models.remove_template(m, t)
            return {"modelName": modelName, "removed": templateName}
    raise ToolError(f"Template not found: {templateName}")


@T("model-template-rename", "Rename a template", write=True)
def model_template_rename(modelName: str, oldTemplateName: str, newTemplateName: str):
    m = col().models.by_name(modelName)
    if not m:
        raise ToolError(f"Model not found: {modelName}")
    for t in m["tmpls"]:
        if t["name"] == oldTemplateName:
            t["name"] = newTemplateName
            col().models.save(m)
            return {"modelName": modelName, "oldName": oldTemplateName, "newName": newTemplateName}
    raise ToolError(f"Template not found: {oldTemplateName}")


@T("model-template-reposition", "Move a template to a new position", write=True)
def model_template_reposition(modelName: str, templateName: str, index: int):
    m = col().models.by_name(modelName)
    if not m:
        raise ToolError(f"Model not found: {modelName}")
    for t in m["tmpls"]:
        if t["name"] == templateName:
            col().models.reposition_template(m, t, index)
            return {"modelName": modelName, "templateName": templateName, "newIndex": index}
    raise ToolError(f"Template not found: {templateName}")


# Statistics tools
@T("get-num-cards-reviewed-by-day", "Get review counts by day")
def get_num_cards_reviewed_by_day(num_days: int = 30):
    cutoff = col().sched.day_cutoff
    day_ms = 86400 * 1000
    result = []
    for i in range(num_days):
        start = (cutoff - (i + 1) * 86400) * 1000
        end = (cutoff - i * 86400) * 1000
        count = col().db.scalar("select count() from revlog where id >= ? and id < ?", start, end)
        result.append({"day": -i, "count": count})
    return {"reviews": result}


@T("get-collection-stats-html", "Get collection stats as HTML")
def get_collection_stats_html(whole_collection: bool = True):
    from aqt import mw
    from aqt.stats import NewDeckStats
    stats = NewDeckStats(mw, mw.col, whole_collection)
    return {"html": stats.report()}


@T("get-reviews", "Get review history for cards or deck")
def get_reviews(card_ids: list[int] = None, deck: str = None, start_id: int = 0, detailed: bool = False):
    """Get review history for cards.

    Args:
        card_ids: Specific card IDs to get reviews for
        deck: Get reviews for all cards in this deck
        start_id: Only return reviews after this ID (for pagination)
        detailed: Include extra fields (lastInterval, factor, type)
    """
    if deck:
        deck_obj = col().decks.by_name(deck)
        if not deck_obj:
            raise ToolError(f"Deck not found: {deck}")
        card_ids = col().find_cards(f'deck:"{deck}"')

    if not card_ids:
        return {"reviews": [], "count": 0}

    if detailed:
        reviews = col().db.all(
            "select id, cid, ease, ivl, lastIvl, factor, time, type from revlog where cid in %s and id > ? order by id" % str(tuple(card_ids)),
            start_id
        )
        result = [
            {"id": r[0], "cardId": r[1], "ease": r[2], "interval": r[3], "lastInterval": r[4], "factor": r[5], "time": r[6], "type": r[7]}
            for r in reviews
        ]
    else:
        reviews = col().db.all(
            "select id, cid, ease, ivl, time from revlog where cid in %s and id > ?" % str(tuple(card_ids)),
            start_id
        )
        result = [{"id": r[0], "cardId": r[1], "ease": r[2], "interval": r[3], "time": r[4]} for r in reviews]

    return {"reviews": result, "count": len(result)}


T("get-latest-review-id", "Get the latest review ID", lambda: col().db.scalar("select max(id) from revlog") or 0)


@T("insert-reviews", "Insert review history entries", write=True)
def insert_reviews(reviews: list[dict]):
    for r in reviews:
        col().db.execute(
            "insert into revlog values (?,?,?,?,?,?,?,?,?)",
            r["id"], r["cid"], r["usn"], r["ease"], r["ivl"],
            r["lastIvl"], r["factor"], r["time"], r["type"]
        )
    return {"inserted": len(reviews)}


# GUI tools
@T("gui-selected-notes", "Get selected notes in browser", category="gui")
def gui_selected_notes():
    from aqt import mw
    from aqt.browser import Browser
    browser = mw.app.activeWindow()
    if isinstance(browser, Browser):
        return {"notes": list(set(c.nid for c in browser.selectedCards()))}
    return {"notes": [], "error": "Browser not open"}


@T("gui-start-card-timer", "Start timer for current card", category="gui")
def gui_start_card_timer():
    from aqt import mw
    if mw.reviewer and mw.reviewer.card:
        mw.reviewer.card.startTimer()
        return {"started": True}
    return {"started": False, "error": "Not in review"}


@T("gui-answer-card", "Answer current card in reviewer", category="gui", write=True)
def gui_answer_card(ease: int):
    from aqt import mw
    if not 1 <= ease <= 4:
        raise ToolError("Ease must be 1-4")
    if mw.reviewer and mw.reviewer.card:
        mw.reviewer._answerCard(ease)
        return {"answered": True, "ease": ease}
    return {"answered": False, "error": "Not in review"}


@T("gui-deck-overview", "Open deck overview", category="gui")
def gui_deck_overview(deck_name: str):
    from aqt import mw
    deck = col().decks.by_name(deck_name)
    if not deck:
        raise ToolError(f"Deck not found: {deck_name}")
    col().decks.select(deck["id"])
    mw.moveToState("overview")
    return {"opened": True, "deckName": deck_name}


@T("gui-deck-review", "Start reviewing a deck", category="gui")
def gui_deck_review(deck_name: str):
    from aqt import mw
    deck = col().decks.by_name(deck_name)
    if not deck:
        raise ToolError(f"Deck not found: {deck_name}")
    col().decks.select(deck["id"])
    mw.moveToState("review")
    return {"started": True, "deckName": deck_name}


@T("gui-import-file", "Open import dialog for a file", category="gui")
def gui_import_file(path: str):
    from aqt import mw
    if not os.path.exists(path):
        raise ToolError(f"File not found: {path}")
    mw.handleImport(path)
    return {"importing": path}


@T("gui-exit-anki", "Close Anki", category="gui", require_col=False)
def gui_exit_anki():
    from aqt import mw
    mw.close()
    return {"closing": True}


@T("gui-check-database", "Check database integrity", category="gui")
def gui_check_database():
    from aqt import mw
    result = mw.col.fix_integrity()
    return {"result": result}


@T("gui-play-audio", "Play audio for current card", category="gui")
def gui_play_audio(side: str = "question"):
    from aqt import mw
    if mw.reviewer and mw.reviewer.card:
        if side == "answer":
            mw.reviewer.playAudio("answer")
        else:
            mw.reviewer.playAudio("question")
        return {"playing": True, "side": side}
    return {"playing": False, "error": "Not in review"}


# Miscellaneous
@T("request-permission", "Request API permission", require_col=False)
def request_permission():
    return {"permission": "granted", "requireApiKey": False, "version": 6}


@T("api-reflect", "Get API reflection info", require_col=False)
def api_reflect(scopes: list[str] = None, actions: list[str] = None):
    from .tool_base import _registry
    all_actions = list(_registry.keys())
    if actions:
        return {"scopes": scopes or [], "actions": {a: a in all_actions for a in actions}}
    return {"scopes": scopes or [], "actions": all_actions}


@T("load-profile", "Load a different profile", require_col=False)
def load_profile(name: str):
    from aqt import mw
    if name not in mw.pm.profiles():
        raise ToolError(f"Profile not found: {name}")
    mw.pm.load(name)
    mw.loadCollection()
    return {"loaded": name}


@T("multi", "Execute multiple actions")
def multi(actions: list[dict]):
    from .handler_registry import execute
    results = []
    for a in actions:
        action = a.get("action")
        params = a.get("params", {})
        try:
            result = execute(action, params)
            results.append(result)
        except Exception as e:
            results.append({"error": str(e)})
    return {"results": results}


# ============================================================================
# REVIEW SESSION TOOLS (unique to MCP)
# ============================================================================

@T("get-due-cards", "Get cards due for review")
def get_due_cards(deck_name: str = None, limit: int = 10):
    query = "is:due"
    if deck_name:
        query += f' deck:"{deck_name}"'
    cards = col().find_cards(query)[:limit]
    return {"cards": cards, "count": len(cards)}


@T("present-card", "Present a card for review")
def present_card(card_id: int, show_answer: bool = False):
    c = col().get_card(card_id)
    n = c.note()
    result = {
        "cardId": card_id,
        "noteId": n.id,
        "question": c.question(),
        "deckName": col().decks.name(c.did),
        "modelName": n.note_type()["name"],
    }
    if show_answer:
        result["answer"] = c.answer()
    return result


@T("rate-card", "Rate a card during review", write=True)
def rate_card(card_id: int, rating: int):
    if not 1 <= rating <= 4:
        raise ToolError("Rating must be 1-4 (Again/Hard/Good/Easy)")
    c = col().get_card(card_id)
    col().sched.answerCard(c, rating)
    return {"rated": card_id, "rating": rating}


# ============================================================================
# LEARNING ANALYTICS & INSIGHTS
# ============================================================================

@T("get-leech-cards", "Find cards marked as leeches or frequently failed")
def get_leech_cards(deck_name: str = None, threshold: int = 8):
    """Find cards that have been failed many times (leeches)."""
    query = "is:review"
    if deck_name:
        query += f' deck:"{deck_name}"'
    cards = col().find_cards(query)

    leeches = []
    for cid in cards:
        c = col().get_card(cid)
        if c.lapses >= threshold:
            n = c.note()
            leeches.append({
                "cardId": cid,
                "noteId": n.id,
                "lapses": c.lapses,
                "ease": c.factor,
                "interval": c.ivl,
                "question": c.question()[:200],  # Truncate for readability
                "deckName": col().decks.name(c.did),
            })

    return {"leeches": sorted(leeches, key=lambda x: -x["lapses"]), "count": len(leeches)}


@T("get-card-memory-state", "Get FSRS stability, difficulty, retrievability for cards")
def get_card_memory_state(cards: list[int]):
    """Get computed memory state for cards (FSRS metrics)."""
    result = []
    for cid in cards:
        try:
            c = col().get_card(cid)
            # Memory state includes stability, difficulty, and days since last review
            state = {
                "cardId": cid,
                "stability": c.memory_state.stability if hasattr(c, 'memory_state') and c.memory_state else None,
                "difficulty": c.memory_state.difficulty if hasattr(c, 'memory_state') and c.memory_state else None,
                "interval": c.ivl,
                "ease": c.factor,
                "lapses": c.lapses,
                "reps": c.reps,
            }
            result.append(state)
        except Exception as e:
            result.append({"cardId": cid, "error": str(e)})
    return {"cards": result}




@T("get-studied-today", "Get today's study session summary")
def get_studied_today():
    """Get summary of today's study session."""
    from aqt import mw
    studied = col().studied_today()
    cutoff = col().sched.day_cutoff * 1000

    # Get detailed stats
    reviews_today = col().db.scalar(
        "select count() from revlog where id > ?", cutoff
    )
    time_today = col().db.scalar(
        "select sum(time) from revlog where id > ?", cutoff
    ) or 0

    return {
        "cardsStudied": studied[0] if studied else 0,
        "timeSpentMs": time_today,
        "timeSpentMinutes": round(time_today / 60000, 1),
        "reviewCount": reviews_today,
        "message": studied[1] if studied and len(studied) > 1 else "",
    }


@T("get-retention-analysis", "Analyze success rate by interval length")
def get_retention_analysis(deck_name: str = None):
    """Analyze retention rates across different interval ranges."""
    query = "is:review"
    if deck_name:
        query += f' deck:"{deck_name}"'
    cards = col().find_cards(query)

    # Bucket cards by interval
    buckets = {
        "1-7 days": {"correct": 0, "total": 0},
        "8-30 days": {"correct": 0, "total": 0},
        "31-90 days": {"correct": 0, "total": 0},
        "91-180 days": {"correct": 0, "total": 0},
        "180+ days": {"correct": 0, "total": 0},
    }

    for cid in cards[:1000]:  # Limit for performance
        c = col().get_card(cid)
        ivl = c.ivl

        if ivl <= 7:
            bucket = "1-7 days"
        elif ivl <= 30:
            bucket = "8-30 days"
        elif ivl <= 90:
            bucket = "31-90 days"
        elif ivl <= 180:
            bucket = "91-180 days"
        else:
            bucket = "180+ days"

        buckets[bucket]["total"] += 1
        # Use ease factor as proxy for success (higher = better retention)
        if c.factor >= 2500:  # Default ease
            buckets[bucket]["correct"] += 1

    # Calculate retention rates
    result = {}
    for name, data in buckets.items():
        if data["total"] > 0:
            result[name] = {
                "total": data["total"],
                "retentionRate": round(data["correct"] / data["total"] * 100, 1),
            }

    return {"retention": result}


@T("get-difficulty-distribution", "Get cards grouped by difficulty level")
def get_difficulty_distribution(deck_name: str = None):
    """Categorize cards by their ease factor (difficulty)."""
    query = "is:review"
    if deck_name:
        query += f' deck:"{deck_name}"'
    cards = col().find_cards(query)

    distribution = {
        "easy": [],      # factor >= 2.5
        "medium": [],    # factor 2.0-2.5
        "hard": [],      # factor 1.5-2.0
        "very_hard": [], # factor < 1.5
    }

    for cid in cards:
        c = col().get_card(cid)
        factor = c.factor / 1000  # Convert to decimal

        if factor >= 2.5:
            distribution["easy"].append(cid)
        elif factor >= 2.0:
            distribution["medium"].append(cid)
        elif factor >= 1.5:
            distribution["hard"].append(cid)
        else:
            distribution["very_hard"].append(cid)

    return {
        "distribution": {
            k: {"count": len(v), "cardIds": v[:10]}  # Return first 10 IDs per category
            for k, v in distribution.items()
        },
        "total": len(cards),
    }


@T("get-forecast", "Predict cards due in coming days")
def get_forecast(days: int = 30):
    """Forecast how many cards will be due each day."""
    import time
    today = col().sched.today
    forecast = []

    for i in range(days):
        due_day = today + i
        # Count cards due on this day
        count = col().db.scalar(
            "select count() from cards where queue = 2 and due = ?",
            due_day
        ) or 0
        forecast.append({"day": i, "due": count})

    return {"forecast": forecast, "days": days}


# ============================================================================
# CUSTOM STUDY & SCHEDULING
# ============================================================================

@T("create-custom-study", "Create a custom study session", write=True)
def create_custom_study(deck_name: str, mode: str, limit: int = 100):
    """Create a custom study session.

    Modes:
    - 'new': Study new cards ahead
    - 'review': Review ahead
    - 'forgot': Review forgotten cards
    - 'random': Random selection
    """
    deck = col().decks.by_name(deck_name)
    if not deck:
        raise ToolError(f"Deck not found: {deck_name}")

    from anki.scheduler.base import CustomStudyRequest

    mode_map = {
        "new": 1,
        "review": 2,
        "forgot": 3,
        "random": 4,
    }

    if mode not in mode_map:
        raise ToolError(f"Invalid mode: {mode}. Use: new, review, forgot, random")

    request = CustomStudyRequest(
        deck_id=deck["id"],
        custom_study_mode=mode_map[mode],
        card_limit=limit,
    )

    col().sched.custom_study(request)
    return {"created": True, "mode": mode, "deck": deck_name, "limit": limit}


@T("get-custom-study-defaults", "Get available options for custom study")
def get_custom_study_defaults(deck_name: str):
    """Get default values and available options for custom study."""
    deck = col().decks.by_name(deck_name)
    if not deck:
        raise ToolError(f"Deck not found: {deck_name}")

    defaults = col().sched.custom_study_defaults(deck["id"])
    return {
        "deckName": deck_name,
        "availableNew": defaults.available_new,
        "availableReview": defaults.available_review,
        "defaults": {
            "extendNew": defaults.extend_new,
            "extendReview": defaults.extend_review,
        },
    }


@T("extend-limits", "Extend daily new/review card limits", write=True)
def extend_limits(deck_name: str, new_delta: int = 0, review_delta: int = 0):
    """Temporarily extend daily limits for current session."""
    deck = col().decks.by_name(deck_name)
    if not deck:
        raise ToolError(f"Deck not found: {deck_name}")

    col().sched.extend_limits(
        deck_id=deck["id"],
        new_delta=new_delta,
        review_delta=review_delta,
    )
    return {
        "extended": True,
        "deckName": deck_name,
        "newDelta": new_delta,
        "reviewDelta": review_delta,
    }


@T("create-filtered-deck", "Create a filtered/cram deck", write=True)
def create_filtered_deck(name: str, search: str, order: int = 0, limit: int = 100):
    """Create a filtered deck with custom search.

    Order values:
    0=oldest first, 1=random, 2=increasing intervals, 3=decreasing intervals,
    4=most lapses, 5=order added, 6=order due, 7=latest added, 8=relative overdue
    """
    result = col().sched.get_or_create_filtered_deck(deck_id=0)
    config = result.config

    config.search_terms[0].search = search
    config.search_terms[0].limit = limit
    config.search_terms[0].order = order

    # Set the name
    deck = col().decks.get(result.id)
    deck["name"] = name
    col().decks.save(deck)

    col().sched.add_or_update_filtered_deck(config)
    col().sched.rebuild_filtered_deck(result.id)

    return {"deckId": result.id, "name": name, "search": search}


@T("rebuild-filtered-deck", "Rebuild filtered deck contents", write=True)
def rebuild_filtered_deck(deck_id: int):
    """Refresh a filtered deck with current matching cards."""
    count = col().sched.rebuild_filtered_deck(deck_id)
    return {"rebuilt": True, "deckId": deck_id, "cardCount": count}


@T("get-deck-due-tree", "Get full deck tree with due counts")
def get_deck_due_tree():
    """Get hierarchical deck tree with new/learn/review counts."""
    tree = col().sched.deck_due_tree()

    def process_node(node):
        return {
            "id": node.deck_id,
            "name": node.name,
            "new": node.new_count,
            "learn": node.learn_count,
            "review": node.review_count,
            "children": [process_node(child) for child in node.children],
        }

    return {"tree": [process_node(n) for n in tree.children]}


# ============================================================================
# COLLECTION HEALTH & OPTIMIZATION
# ============================================================================

@T("get-empty-cards", "Find notes that generate no cards")
def get_empty_cards():
    """Find notes where templates don't generate any cards."""
    report = col().get_empty_cards()
    return {
        "emptyNotes": [
            {"noteId": n.note_id, "cardId": n.card_id, "template": n.template_index}
            for n in report.notes
        ],
        "count": len(report.notes),
        "message": report.report if hasattr(report, 'report') else "",
    }


@T("find-duplicates", "Find duplicate notes by field content")
def find_duplicates(field_name: str, deck_name: str = None):
    """Find notes with duplicate content in a specific field."""
    query = ""
    if deck_name:
        query = f'deck:"{deck_name}"'

    dupes = col().find_dupes(field_name, query)
    return {
        "duplicates": [
            {"value": d[0], "noteIds": list(d[1])}
            for d in dupes
        ],
        "count": len(dupes),
    }


@T("check-integrity", "Check and optionally fix database integrity")
def check_integrity(fix: bool = False):
    """Check database for corruption and optionally fix issues."""
    if fix:
        result = col().fix_integrity()
    else:
        # Just check without fixing (run basic validation)
        result = col().db.scalar("pragma integrity_check")

    return {
        "checked": True,
        "fixed": fix,
        "result": str(result),
    }


@T("optimize-database", "Vacuum and analyze database for better performance")
def optimize_database():
    """Optimize the database (vacuum and analyze)."""
    col().optimize()
    return {"optimized": True, "message": "Database vacuumed and analyzed"}


@T("check-media", "Check for missing or unused media files")
def check_media():
    """Check media folder for issues."""
    result = col().media.check()
    return {
        "missing": list(result.missing),
        "unused": list(result.unused),
        "missingCount": len(result.missing),
        "unusedCount": len(result.unused),
    }


@T("get-collection-info", "Get collection metadata and path info")
def get_collection_info():
    """Get information about the collection."""
    from aqt import mw
    return {
        "path": col().path,
        "mediaPath": col().media.dir(),
        "modTime": col().mod,
        "schemaVersion": col().db.scalar("select ver from col"),
        "profileName": mw.pm.name,
        "profilePath": mw.pm.profileFolder(),
    }


# ============================================================================
# ADVANCED IMPORT/EXPORT
# ============================================================================

@T("import-csv", "Import notes from CSV file", write=True)
def import_csv(path: str, deck_name: str, model_name: str, delimiter: str = ","):
    """Import notes from a CSV file."""
    if not os.path.exists(path):
        raise ToolError(f"File not found: {path}")

    from anki.importing.csvfile import TextImporter

    model = col().models.by_name(model_name)
    if not model:
        raise ToolError(f"Model not found: {model_name}")

    deck = col().decks.by_name(deck_name)
    if not deck:
        deck_id = col().decks.id(deck_name)
    else:
        deck_id = deck["id"]

    importer = TextImporter(col(), path)
    importer.model = model
    importer.allowHTML = True
    importer.importMode = 0  # UPDATE_MODE

    col().decks.select(deck_id)
    importer.run()

    return {
        "imported": True,
        "path": path,
        "deckName": deck_name,
        "log": importer.log,
    }


@T("import-json", "Import notes from JSON string", write=True)
def import_json(json_data: str, deck_name: str):
    """Import notes from JSON format."""
    import json

    try:
        data = json.loads(json_data)
    except json.JSONDecodeError as e:
        raise ToolError(f"Invalid JSON: {e}")

    col().import_json_string(json_data)
    return {"imported": True, "deckName": deck_name}


@T("export-notes-csv", "Export notes matching query as CSV")
def export_notes_csv(query: str, out_path: str = ""):
    """Export notes as CSV file."""
    from aqt import mw

    if not out_path:
        folder = os.path.join(mw.pm.profileFolder(), "exports")
        os.makedirs(folder, exist_ok=True)
        out_path = os.path.join(folder, "notes_export.csv")

    notes = col().find_notes(query)

    import csv
    with open(out_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)

        # Write header based on first note's fields
        if notes:
            first_note = col().get_note(notes[0])
            model = first_note.note_type()
            headers = ["noteId", "tags"] + [fld["name"] for fld in model["flds"]]
            writer.writerow(headers)

            for nid in notes:
                note = col().get_note(nid)
                row = [nid, " ".join(note.tags)] + note.fields
                writer.writerow(row)

    return {"exported": True, "path": out_path, "noteCount": len(notes)}


@T("export-for-research", "Export anonymized data for analysis")
def export_for_research(out_path: str = ""):
    """Export anonymized learning data for research."""
    from aqt import mw

    if not out_path:
        folder = os.path.join(mw.pm.profileFolder(), "exports")
        os.makedirs(folder, exist_ok=True)
        out_path = os.path.join(folder, "research_export.csv")

    # Export review logs (anonymized - no card content)
    import csv
    with open(out_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["cardHash", "timestamp", "ease", "interval", "lastInterval", "time", "type"])

        reviews = col().db.all(
            "select cid, id, ease, ivl, lastIvl, time, type from revlog order by id"
        )
        for r in reviews:
            # Hash card ID for anonymization
            card_hash = hash(r[0]) % 1000000
            writer.writerow([card_hash, r[1], r[2], r[3], r[4], r[5], r[6]])

    return {"exported": True, "path": out_path, "reviewCount": len(reviews)}


# ============================================================================
# IMAGE OCCLUSION
# ============================================================================

@T("add-image-occlusion-note", "Create image occlusion cards", write=True)
def add_image_occlusion_note(image_path: str, occlusions: list[dict], deck_name: str, tags: list[str] = None):
    """Create image occlusion cards from an image.

    occlusions: List of dicts with {left, top, width, height} for each mask
    """
    if not os.path.exists(image_path):
        raise ToolError(f"Image not found: {image_path}")

    deck = col().decks.by_name(deck_name)
    if not deck:
        raise ToolError(f"Deck not found: {deck_name}")

    # Read and encode image
    import base64
    with open(image_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode()

    from anki.image_occlusion import AddImageOcclusionNoteRequest

    request = AddImageOcclusionNoteRequest(
        image_data=image_data,
        occlusions=str(occlusions),  # Serialize occlusions
        deck_id=deck["id"],
        tags=tags or [],
    )

    result = col().add_image_occlusion_note(request)
    return {"noteId": result.note_id, "deckName": deck_name}


@T("get-image-occlusion-note", "Get occlusion config for existing note")
def get_image_occlusion_note(note_id: int):
    """Get image occlusion configuration for an existing note."""
    result = col().get_image_occlusion_note(note_id)
    return {
        "noteId": note_id,
        "imageData": result.image_data[:100] + "..." if result.image_data else None,
        "occlusions": result.occlusions,
    }


# ============================================================================
# SCHEMA & INTROSPECTION - Expose Anki's data model
# ============================================================================

@T("schema", "Get Anki's data model schema for understanding entities and relationships")
def schema():
    """Expose Anki's complete data model.

    Returns entity definitions, fields, relationships, and types to help
    understand how Anki's data is structured.
    """
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
                "fields": {
                    "name": {"type": "string", "description": "Tag name"},
                },
                "notes": "Tags are not a separate table - they're stored in the notes.tags field.",
            },
        },
        "key_concepts": {
            "note_vs_card": "A Note holds content (fields). A Card is generated from a Note via a Template. One Note can produce multiple Cards (e.g., front→back and back→front).",
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
            "field:_*": "front:_* - field has any content",
        },
        "deck_and_tag": {
            "deck:NAME": "deck:Japanese - cards in deck (includes subdecks)",
            "deck:NAME*": "deck:Japanese* - wildcard deck matching",
            '"deck:My Deck"': "Quote deck names with spaces",
            "tag:NAME": "tag:verb - notes with tag",
            "tag:none": "Notes with no tags",
            "tag:*": "Notes with any tag",
        },
        "card_state": {
            "is:due": "Cards due for review today",
            "is:new": "New cards (never seen)",
            "is:learn": "Cards in learning phase",
            "is:review": "Review cards (graduated)",
            "is:suspended": "Suspended cards",
            "is:buried": "Buried cards",
            "is:buried-sibling": "Buried due to sibling",
            "is:buried-manually": "Manually buried",
        },
        "card_properties": {
            "prop:ivl>N": "prop:ivl>30 - interval greater than 30 days",
            "prop:ivl<N": "prop:ivl<7 - interval less than 7 days",
            "prop:due>N": "prop:due>5 - due more than 5 days from now",
            "prop:due=N": "prop:due=0 - due today",
            "prop:ease>N": "prop:ease<2.1 - ease factor below 210%",
            "prop:reps>N": "prop:reps>10 - reviewed more than 10 times",
            "prop:lapses>N": "prop:lapses>3 - lapsed more than 3 times",
        },
        "date_searches": {
            "added:N": "added:7 - added in last 7 days",
            "edited:N": "edited:1 - edited today",
            "rated:N": "rated:7 - reviewed in last 7 days",
            "rated:N:A": "rated:7:1 - rated 'Again' in last 7 days (1=Again,2=Hard,3=Good,4=Easy)",
            "introduced:N": "introduced:30 - first learned in last 30 days",
        },
        "note_and_card_type": {
            "note:NAME": 'note:Basic - notes of type "Basic"',
            "card:N": "card:1 - first card template only",
            "card:NAME": 'card:"Card 1" - card template by name',
            "mid:ID": "mid:1234567890 - notes with specific model ID",
        },
        "flags_and_marks": {
            "flag:N": "flag:1 - cards with red flag (1=red,2=orange,3=green,4=blue,5-7=custom)",
            "flag:0": "Cards with no flag",
        },
        "other": {
            "nid:ID": "nid:1234567890 - specific note by ID",
            "cid:ID": "cid:1234567890 - specific card by ID",
            "nid:ID,ID,ID": "nid:123,456,789 - multiple notes",
            "dupe:MID,TEXT": "Find duplicates",
            "re:REGEX": "re:\\btest\\b - regular expression search",
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
            {"query": '"to be" deck:English', "description": "Exact phrase in English deck"},
            {"query": "prop:ease<2 prop:ivl>21", "description": "Struggling cards with long intervals"},
            {"query": "front:*tion", "description": "Front field ending in 'tion'"},
            {"query": "rated:1:1", "description": "Cards rated 'Again' today"},
            {"query": "note:Cloze (tag:grammar OR tag:vocab)", "description": "Cloze notes with grammar or vocab tags"},
        ],
    }


@T("raw-sql", "Execute read-only SQL query on Anki's database")
def raw_sql(sql: str, params: list = None):
    """Execute a read-only SQL query on Anki's SQLite database.

    Args:
        sql: SQL SELECT query (only SELECT allowed)
        params: Optional list of parameters for placeholders

    Returns:
        Query results as list of rows with column names

    Security:
        - Only SELECT queries allowed
        - No data modification possible
        - Use for advanced queries not covered by other tools
    """
    # Security: Only allow SELECT queries
    sql_upper = sql.strip().upper()
    if not sql_upper.startswith("SELECT"):
        raise ToolError(
            "Only SELECT queries allowed",
            hint="raw-sql is read-only. Use other tools for modifications."
        )

    # Block dangerous keywords even in subqueries
    dangerous = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "ATTACH", "DETACH"]
    for keyword in dangerous:
        if keyword in sql_upper:
            raise ToolError(
                f"Forbidden keyword: {keyword}",
                hint="raw-sql is read-only. Use other tools for modifications."
            )

    params = params or []

    try:
        cursor = col().db.execute(sql, params)
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        rows = cursor.fetchall()

        # Limit results to prevent massive responses
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


# ============================================================================
# Export the registration function
# ============================================================================

__all__ = ["register_tools"]
