"""Backup and import/export tools."""
import os
from datetime import datetime
from .base import T, ToolError, col


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
    from aqt import mw

    if not out_path:
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


@T("import-csv", "Import notes from CSV file", write=True)
def import_csv(path: str, deck_name: str, model_name: str, delimiter: str = ","):
    if not os.path.exists(path):
        raise ToolError(f"File not found: {path}")

    from anki.importing.csvfile import TextImporter

    model = col().models.by_name(model_name)
    if not model:
        raise ToolError(f"Model not found: {model_name}")

    deck = col().decks.by_name(deck_name)
    deck_id = deck["id"] if deck else col().decks.id(deck_name)

    importer = TextImporter(col(), path)
    importer.model = model
    importer.allowHTML = True
    importer.importMode = 0

    col().decks.select(deck_id)
    importer.run()

    return {"imported": True, "path": path, "deckName": deck_name, "log": importer.log}


@T("import-json", "Import notes from JSON string", write=True)
def import_json(json_data: str, deck_name: str):
    import json

    try:
        json.loads(json_data)
    except json.JSONDecodeError as e:
        raise ToolError(f"Invalid JSON: {e}")

    col().import_json_string(json_data)
    return {"imported": True, "deckName": deck_name}


@T("export-notes-csv", "Export notes matching query as CSV")
def export_notes_csv(query: str, out_path: str = ""):
    from aqt import mw
    import csv

    if not out_path:
        folder = os.path.join(mw.pm.profileFolder(), "exports")
        os.makedirs(folder, exist_ok=True)
        out_path = os.path.join(folder, "notes_export.csv")

    notes = col().find_notes(query)

    with open(out_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)

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
    from aqt import mw
    import csv

    if not out_path:
        folder = os.path.join(mw.pm.profileFolder(), "exports")
        os.makedirs(folder, exist_ok=True)
        out_path = os.path.join(folder, "research_export.csv")

    reviews = col().db.all("select cid, id, ease, ivl, lastIvl, time, type from revlog order by id")

    with open(out_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["cardHash", "timestamp", "ease", "interval", "lastInterval", "time", "type"])

        for r in reviews:
            card_hash = hash(r[0]) % 1000000
            writer.writerow([card_hash, r[1], r[2], r[3], r[4], r[5], r[6]])

    return {"exported": True, "path": out_path, "reviewCount": len(reviews)}
