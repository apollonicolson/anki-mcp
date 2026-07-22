"""Tag management tools."""
from .base import T, col


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
