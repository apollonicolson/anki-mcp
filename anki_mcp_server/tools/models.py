"""Note type (model) management tools."""
from typing import Optional
from .base import T, ToolError, col
import re


@T("list-models", "List note types with optional filtering")
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


def model_field_remove(modelName: str, fieldName: str):
    m = col().models.by_name(modelName)
    if not m:
        raise ToolError(f"Model not found: {modelName}")
    for f in m["flds"]:
        if f["name"] == fieldName:
            col().models.remove_field(m, f)
            return {"modelName": modelName, "removed": fieldName}
    raise ToolError(f"Field not found: {fieldName}")


def model_field_rename(modelName: str, oldFieldName: str, newFieldName: str):
    m = col().models.by_name(modelName)
    if not m:
        raise ToolError(f"Model not found: {modelName}")
    for f in m["flds"]:
        if f["name"] == oldFieldName:
            col().models.rename_field(m, f, newFieldName)
            return {"modelName": modelName, "oldName": oldFieldName, "newName": newFieldName}
    raise ToolError(f"Field not found: {oldFieldName}")


def model_field_reposition(modelName: str, fieldName: str, index: int):
    m = col().models.by_name(modelName)
    if not m:
        raise ToolError(f"Model not found: {modelName}")
    for f in m["flds"]:
        if f["name"] == fieldName:
            col().models.reposition_field(m, f, index)
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
    return {"modelName": modelName, "templateName": t["name"]}


def model_template_remove(modelName: str, templateName: str):
    m = col().models.by_name(modelName)
    if not m:
        raise ToolError(f"Model not found: {modelName}")
    for t in m["tmpls"]:
        if t["name"] == templateName:
            col().models.remove_template(m, t)
            return {"modelName": modelName, "removed": templateName}
    raise ToolError(f"Template not found: {templateName}")


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


def model_template_reposition(modelName: str, templateName: str, index: int):
    m = col().models.by_name(modelName)
    if not m:
        raise ToolError(f"Model not found: {modelName}")
    for t in m["tmpls"]:
        if t["name"] == templateName:
            col().models.reposition_template(m, t, index)
            return {"modelName": modelName, "templateName": templateName, "newIndex": index}
    raise ToolError(f"Template not found: {templateName}")
