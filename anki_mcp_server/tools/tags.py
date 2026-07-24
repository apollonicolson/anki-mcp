"""Tag management tools."""
from .base import T, ToolError, col


def list_tags(pattern: str = None, limit: int = None):
    """Get tags with optional filtering."""
    import fnmatch
    all_tags = col().tags.all()

    if pattern:
        all_tags = [t for t in all_tags if fnmatch.fnmatch(t.lower(), pattern.lower())]

    total = len(all_tags)
    if limit:
        all_tags = all_tags[:limit]

    return {"tags": all_tags, "count": len(all_tags), "total": total}


def add_tags(notes: list[int], tags: str):
    col().tags.bulk_add(notes, tags)
    return {"tagged": len(notes), "tags": tags}


def remove_tags(notes: list[int], tags: str):
    col().tags.bulk_remove(notes, tags)
    return {"untagged": len(notes), "tags": tags}


@T("apply-tags-file", "Bulk-add tags from a {tag: [note_ids]} JSON file", write=True)
def apply_tags_file(path: str, dry_run: bool = True):
    """Add each tag to its listed notes, reading the plan from a file.

    A reconstructed tag plan is thousands of (note, tag) pairs; inlining the id
    lists in the tool call is what import-notes-file avoids, for the same reason.
    One bulk_add per tag, so N tags cost N passes regardless of note count.
    """
    import json
    import os

    from . import _journal

    if not os.path.isfile(path):
        raise ToolError(f"No such file: {path}")
    doc = json.load(open(path, encoding="utf-8"))
    plan = doc.get("tag_to_notes", doc)
    if not isinstance(plan, dict):
        raise ToolError('File must be {"tag_to_notes": {tag: [ids]}} or {tag: [ids]}')

    clean = {}
    all_ids = set()
    for tag, ids in plan.items():
        ids = [int(i) for i in ids]
        clean[tag] = ids
        all_ids.update(ids)

    summary = {
        "tags": len(clean),
        "notes_touched": len(all_ids),
        "pairs": sum(len(v) for v in clean.values()),
        "per_tag": {t: len(v) for t, v in sorted(clean.items())},
    }
    if dry_run:
        summary["dry_run"] = True
        summary["hint"] = "re-run with dry_run=false to apply"
        return summary

    _journal.declare_targets(col(), sorted(all_ids))
    for tag, ids in clean.items():
        if ids:
            col().tags.bulk_add(ids, tag)
    summary["dry_run"] = False
    summary["applied"] = True
    return summary


@T("clear-unused-tags", "Remove unused tags", write=True)
def clear_unused_tags():
    col().tags.clear_unused_tags()
    return {"cleared": True}


@T("replace-tags", "Replace tag on notes", write=True)
def replace_tags(old_tag: str, new_tag: str, notes: list[int] = None):
    """Replace a tag with another on notes."""
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
