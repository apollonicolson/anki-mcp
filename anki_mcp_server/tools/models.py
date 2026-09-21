"""Note type (model) management tools."""
from typing import Optional
from .base import T, ToolError, col
import re


def list_models(
    pattern: str = None,
    ids: list[int] = None,
    names: list[str] = None,
    include_fields: bool = False,
    limit: int = 100,
    offset: int = 0,
):
    """List note types (models) with optional filtering and pagination."""
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

    total = len(models)
    models = models[offset:offset + limit]

    result = []
    for m in models:
        info = {"id": m["id"], "name": m["name"]}
        if include_fields:
            info["fields"] = [f["name"] for f in m["flds"]]
        result.append(info)

    meta = {"models": result, "total": total}
    if offset + limit < total:
        meta["hasMore"] = True
    return meta


def model_field_names(modelName: str):
    m = col().models.by_name(modelName)
    if not m:
        raise ToolError(f"Model not found: {modelName}")
    return [f["name"] for f in m["flds"]]


def model_styling(modelName: str):
    m = col().models.by_name(modelName)
    if not m:
        raise ToolError(f"Model not found: {modelName}")
    return {"css": m["css"]}


def update_model_styling(modelName: str, css: str):
    m = col().models.by_name(modelName)
    if not m:
        raise ToolError(f"Model not found: {modelName}")
    m["css"] = css
    col().models.save(m)
    return {"modelName": modelName, "updated": True}


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


def model_field_descriptions(modelName: str):
    m = col().models.by_name(modelName)
    if not m:
        raise ToolError(f"Model not found: {modelName}")
    return [f.get("description", "") for f in m["flds"]]


def model_field_fonts(modelName: str):
    m = col().models.by_name(modelName)
    if not m:
        raise ToolError(f"Model not found: {modelName}")
    return {f["name"]: {"font": f.get("font", ""), "size": f.get("size", 20)} for f in m["flds"]}


def model_fields_on_templates(modelName: str):
    m = col().models.by_name(modelName)
    if not m:
        raise ToolError(f"Model not found: {modelName}")
    result = {}
    for t in m["tmpls"]:
        fields = set(re.findall(r'\{\{[#^/]?([^}]+)\}\}', t["qfmt"] + t["afmt"]))
        result[t["name"]] = list(fields)
    return result


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


def _save_verified(m, landed, what: str):
    """Persist a model dict and confirm the change reached the collection.

    Anki's deprecation of addField -> add_field split one call into two: the
    legacy addField/remField/renameField/addTemplate all ran the mutation AND
    self.update(notetype); the snake_case replacements only mutate the dict.
    A mechanical rename therefore drops the write silently and still returns
    success. The re-read is what makes that failure observable.
    """
    col().models.save(m)
    fresh = col().models.by_name(m["name"])
    if not fresh or not landed(fresh):
        raise ToolError(f"{what} did not persist")
    return fresh


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
    _save_verified(m, lambda mm: any(x["name"] == fieldName for x in mm["flds"]),
                   f"field-add {modelName}.{fieldName}")
    return {"modelName": modelName, "fieldName": fieldName}


def model_field_remove(modelName: str, fieldName: str):
    m = col().models.by_name(modelName)
    if not m:
        raise ToolError(f"Model not found: {modelName}")
    for f in m["flds"]:
        if f["name"] == fieldName:
            col().models.remove_field(m, f)
            _save_verified(m, lambda mm: all(x["name"] != fieldName for x in mm["flds"]),
                           f"field-remove {modelName}.{fieldName}")
            return {"modelName": modelName, "removed": fieldName}
    raise ToolError(f"Field not found: {fieldName}")


def model_field_rename(modelName: str, oldFieldName: str, newFieldName: str):
    m = col().models.by_name(modelName)
    if not m:
        raise ToolError(f"Model not found: {modelName}")
    for f in m["flds"]:
        if f["name"] == oldFieldName:
            col().models.rename_field(m, f, newFieldName)
            _save_verified(m, lambda mm: any(x["name"] == newFieldName for x in mm["flds"]),
                           f"field-rename {modelName}.{oldFieldName}")
            return {"modelName": modelName, "oldName": oldFieldName, "newName": newFieldName}
    raise ToolError(f"Field not found: {oldFieldName}")


def model_field_reposition(modelName: str, fieldName: str, index: int):
    m = col().models.by_name(modelName)
    if not m:
        raise ToolError(f"Model not found: {modelName}")
    for f in m["flds"]:
        if f["name"] == fieldName:
            col().models.reposition_field(m, f, index)
            _save_verified(m, lambda mm: [x["name"] for x in mm["flds"]].index(fieldName) == index,
                           f"field-reposition {modelName}.{fieldName}")
            return {"modelName": modelName, "fieldName": fieldName, "newIndex": index}
    raise ToolError(f"Field not found: {fieldName}")


def model_template_add(modelName: str, template: dict):
    m = col().models.by_name(modelName)
    if not m:
        raise ToolError(f"Model not found: {modelName}")
    t = col().models.new_template(template.get("Name", "Card"))
    t["qfmt"] = template.get("Front", "")
    t["afmt"] = template.get("Back", "")
    col().models.add_template(m, t)
    _save_verified(m, lambda mm: any(x["name"] == t["name"] for x in mm["tmpls"]),
                   f"template-add {modelName}.{t['name']}")
    return {"modelName": modelName, "templateName": t["name"]}


def model_template_remove(modelName: str, templateName: str):
    m = col().models.by_name(modelName)
    if not m:
        raise ToolError(f"Model not found: {modelName}")
    for t in m["tmpls"]:
        if t["name"] == templateName:
            col().models.remove_template(m, t)
            _save_verified(m, lambda mm: all(x["name"] != templateName for x in mm["tmpls"]),
                           f"template-remove {modelName}.{templateName}")
            return {"modelName": modelName, "removed": templateName}
    raise ToolError(f"Template not found: {templateName}")


def model_template_rename(modelName: str, oldTemplateName: str, newTemplateName: str):
    m = col().models.by_name(modelName)
    if not m:
        raise ToolError(f"Model not found: {modelName}")
    for t in m["tmpls"]:
        if t["name"] == oldTemplateName:
            t["name"] = newTemplateName
            _save_verified(m, lambda mm: any(x["name"] == newTemplateName for x in mm["tmpls"]),
                           f"template-rename {modelName}.{oldTemplateName}")
            return {"modelName": modelName, "oldName": oldTemplateName, "newName": newTemplateName}
    raise ToolError(f"Template not found: {oldTemplateName}")


def model_template_reposition(modelName: str, templateName: str, index: int):
    m = col().models.by_name(modelName)
    if not m:
        raise ToolError(f"Model not found: {modelName}")
    for t in m["tmpls"]:
        if t["name"] == templateName:
            col().models.reposition_template(m, t, index)
            _save_verified(m, lambda mm: [x["name"] for x in mm["tmpls"]].index(templateName) == index,
                           f"template-reposition {modelName}.{templateName}")
            return {"modelName": modelName, "templateName": templateName, "newIndex": index}
    raise ToolError(f"Template not found: {templateName}")


def model_delete(modelName: str, force: bool = False):
    """Remove a notetype. Refuses while it still holds notes unless forced.

    Anki's remove_notetype deletes the notetype AND every note using it, with no
    per-note trace in the journal. The guard is the difference between deleting
    an empty leftover and deleting a deck's worth of work.
    """
    m = col().models.by_name(modelName)
    if not m:
        raise ToolError(f"Model not found: {modelName}")
    mid = m["id"]
    n_notes = col().models.use_count(m)
    if n_notes and not force:
        raise ToolError(
            f"{modelName} still holds {n_notes} note(s); deleting it deletes them too",
            hint="move them with alter op=notetype-change first, or pass force=true",
        )
    col().models.remove(mid)
    if col().models.by_name(modelName):
        raise ToolError(f"notetype-delete {modelName} did not persist")
    return {"modelName": modelName, "modelId": mid, "notesDeleted": n_notes}


def model_rename(modelName: str, newName: str):
    m = col().models.by_name(modelName)
    if not m:
        raise ToolError(f"Model not found: {modelName}")
    if col().models.by_name(newName):
        raise ToolError(f"A model named {newName} already exists")
    m["name"] = newName
    _save_verified(m, lambda mm: mm["name"] == newName, f"notetype-rename {modelName}")
    return {"oldName": modelName, "newName": newName}


def model_change_notetype(fromModel: str, toModel: str, query: str = None,
                          ids: list[int] = None):
    """Repoint notes onto another notetype, preserving their cards and scheduling.

    This is what Browse > Notes > Change Note Type does. Export-and-reimport is
    NOT equivalent: it mints new cards and discards the review history. Field and
    template mapping uses the backend's defaults, which match on name and fall
    back to position.
    """
    old = col().models.by_name(fromModel)
    new = col().models.by_name(toModel)
    if not old:
        raise ToolError(f"Model not found: {fromModel}")
    if not new:
        raise ToolError(f"Model not found: {toModel}")

    note_ids = [int(n) for n in (ids or [])]
    if query:
        note_ids.extend(int(n) for n in col().find_notes(query))
    if not note_ids:
        note_ids = [int(n) for n in col().models.nids(old["id"])]
    note_ids = sorted(set(note_ids))
    if not note_ids:
        raise ToolError(f"No notes to move from {fromModel}")

    stray = [n for n in note_ids if col().get_note(n).mid != old["id"]]
    if stray:
        raise ToolError(
            f"{len(stray)} of {len(note_ids)} target notes are not {fromModel}",
            hint="narrow the query, or pass ids explicitly",
        )

    info = col().models.change_notetype_info(
        old_notetype_id=old["id"], new_notetype_id=new["id"]
    )
    req = info.input
    req.note_ids.extend(note_ids)
    col().models.change_notetype_of_notes(req)

    moved = [n for n in note_ids if col().get_note(n).mid == new["id"]]
    if len(moved) != len(note_ids):
        raise ToolError(f"notetype-change moved {len(moved)} of {len(note_ids)} notes")
    return {
        "fromModel": fromModel,
        "toModel": toModel,
        "notesMoved": len(moved),
        "fieldMap": list(req.new_fields),
        "templateMap": list(req.new_templates),
    }
