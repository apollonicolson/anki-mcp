"""Unified CLI/Datalog-style Anki tool.

This is the preferred high-level interface for agents. It keeps Anki's native
browser query syntax, then adds a small EDN-like predicate layer for the cases
that are painful to express with Anki search alone.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from html import unescape
import re
from typing import Any

from .base import T, ToolError, col, mw


_TAG_RE = re.compile(r"<[^>]+>")
_IMG_RE = re.compile(r"<img\b[^>]*>", re.I)
_BR_RE = re.compile(r"<br\s*/?>", re.I)
_SPACE_RE = re.compile(r"\s+")
_NON_TEXT_RE = re.compile(r"[^a-z0-9_+\-*/=<>^()., :;?\[\]{}|]+")

_SYMBOLS = {
    "−": "-",
    "–": "-",
    "—": "-",
    "×": "x",
    "∙": "x",
    "⋅": "x",
    "÷": "/",
    "²": "^2",
    "³": "^3",
    "≤": "<=",
    "≥": ">=",
    "√": "sqrt",
}


def _strip(value: Any) -> str:
    text = "" if value is None else str(value)
    text = unescape(text)
    text = _IMG_RE.sub(" [image] ", text)
    text = _BR_RE.sub(" ", text)
    text = _TAG_RE.sub(" ", text)
    text = text.replace("\xa0", " ")
    return _SPACE_RE.sub(" ", text).strip()


def _norm(value: Any) -> str:
    text = _strip(value).lower()
    for src, dst in _SYMBOLS.items():
        text = text.replace(src, dst)
    text = _NON_TEXT_RE.sub(" ", text)
    return _SPACE_RE.sub(" ", text).strip()


def _fields(note) -> dict[str, str]:
    model = note.note_type()
    return {field["name"]: note.fields[i] for i, field in enumerate(model["flds"])}


def _cards(note, rendered: bool = False) -> list[dict[str, Any]]:
    rows = []
    for card in note.cards():
        row = {
            "id": card.id,
            "deck": col().decks.name(card.did),
            "deckId": card.did,
            "ord": card.ord,
            "queue": card.queue,
            "type": card.type,
            "due": card.due,
            "interval": card.ivl,
            "factor": card.factor,
            "reps": card.reps,
            "lapses": card.lapses,
        }
        if rendered:
            question = card.question()
            answer = card.answer()
            row.update(
                {
                    "question": question,
                    "answer": answer,
                    "questionText": _strip(question),
                    "answerText": _strip(answer),
                }
            )
        rows.append(row)
    return rows


def _note(note_id: int, rendered: bool = False) -> dict[str, Any]:
    note = col().get_note(note_id)
    model = note.note_type()
    return {
        "id": note_id,
        "model": model["name"],
        "modelId": model["id"],
        "tags": list(note.tags),
        "fields": _fields(note),
        "cards": _cards(note, rendered=rendered),
    }


def _card(card_id: int, rendered: bool = False) -> dict[str, Any]:
    card = col().get_card(card_id)
    note = card.note()
    row = {
        "id": card_id,
        "noteId": note.id,
        "deck": col().decks.name(card.did),
        "deckId": card.did,
        "model": note.note_type()["name"],
        "queue": card.queue,
        "type": card.type,
        "due": card.due,
        "interval": card.ivl,
        "factor": card.factor,
        "reps": card.reps,
        "lapses": card.lapses,
    }
    if rendered:
        question = card.question()
        answer = card.answer()
        row.update(
            {
                "question": question,
                "answer": answer,
                "questionText": _strip(question),
                "answerText": _strip(answer),
            }
        )
    return row


def _first_field(fields: dict[str, str], names: list[str]) -> str:
    for name in names:
        if fields.get(name):
            return fields[name]
    for value in fields.values():
        if value:
            return value
    return ""


def _matches_where_note(note_row: dict[str, Any], where: Any) -> bool:
    if where in (None, [], {}):
        return True
    if isinstance(where, str):
        text = _norm(" ".join(note_row["fields"].values()))
        return _norm(where) in text
    if not isinstance(where, list) or not where:
        return True

    op = where[0]
    args = where[1:]
    if op == "and":
        return all(_matches_where_note(note_row, arg) for arg in args)
    if op == "or":
        return any(_matches_where_note(note_row, arg) for arg in args)
    if op == "not":
        return not _matches_where_note(note_row, args[0])
    if op in ("tag", "tag="):
        return args[0] in note_row["tags"]
    if op in ("model", "model="):
        return note_row["model"] == args[0]
    if op in ("field/exists", "field-exists"):
        return bool(_strip(note_row["fields"].get(args[0], "")))
    if op in ("field/blank", "field-blank"):
        return not _strip(note_row["fields"].get(args[0], ""))
    if op in ("field/matches", "field-matches"):
        return _norm(args[1]) in _norm(note_row["fields"].get(args[0], ""))
    if op in ("rendered/blank", "rendered-blank"):
        return any(not _strip(card.get("questionText", "")) or "front of this card is blank" in _strip(card.get("questionText", "")).lower()
                   for card in note_row["cards"])
    if op in ("card/reviewed?", "reviewed?"):
        return any(card["reps"] > 0 for card in note_row["cards"])
    if op in ("card/suspended?", "suspended?"):
        return any(card["queue"] == -1 for card in note_row["cards"])
    return True


def _project_note(note_row: dict[str, Any], select: list[Any] | None) -> dict[str, Any]:
    if not select:
        return note_row

    out: dict[str, Any] = {}
    for item in select:
        if item in ("note/id", "id"):
            out["id"] = note_row["id"]
        elif item in ("model/name", "model"):
            out["model"] = note_row["model"]
        elif item == "tags":
            out["tags"] = note_row["tags"]
        elif item == "fields":
            out["fields"] = note_row["fields"]
        elif item == "cards":
            out["cards"] = note_row["cards"]
        elif item in ("deck/name", "deck"):
            out["decks"] = sorted({card["deck"] for card in note_row["cards"]})
        elif isinstance(item, list) and item and item[0] == "field":
            out[item[1]] = note_row["fields"].get(item[1], "")
    return out


def _query_notes(request: dict[str, Any]) -> dict[str, Any]:
    query = request.get("query", "")
    limit = int(request.get("limit", 100))
    offset = int(request.get("offset", 0))
    rendered = bool(request.get("rendered") or "rendered" in request.get("include", []))
    where = request.get("where")
    select = request.get("select")

    ids = col().find_notes(query)
    rows = []
    matched_total = len(ids)
    scanned = len(ids)

    if where:
        matched = []
        for note_id in ids:
            row = _note(note_id, rendered=rendered or where)
            if _matches_where_note(row, where):
                matched.append(row)
        matched_total = len(matched)
        page_rows = matched[offset : offset + limit]
        rows = [_project_note(row, select) for row in page_rows]
    else:
        page = ids[offset : offset + limit]
        for note_id in page:
            row = _note(note_id, rendered=rendered)
            rows.append(_project_note(row, select))

    return {
        "query": query,
        "from": "notes",
        "rows": rows,
        "count": len(rows),
        "total": matched_total,
        "baseTotal": len(ids),
        "scanned": scanned,
        "offset": offset,
        "limit": limit,
        "hasMore": offset + limit < matched_total,
    }


def _query_cards(request: dict[str, Any]) -> dict[str, Any]:
    query = request.get("query", "")
    limit = int(request.get("limit", 100))
    offset = int(request.get("offset", 0))
    rendered = bool(request.get("rendered") or "rendered" in request.get("include", []))
    ids = col().find_cards(query)
    page = ids[offset : offset + limit]
    return {
        "query": query,
        "from": "cards",
        "rows": [_card(card_id, rendered=rendered) for card_id in page],
        "count": len(page),
        "total": len(ids),
        "offset": offset,
        "limit": limit,
        "hasMore": offset + limit < len(ids),
    }


def _inspect(request: dict[str, Any]) -> dict[str, Any]:
    kind = request.get("type", "note")
    ids = request.get("ids") or []
    rendered = bool(request.get("rendered") or "rendered" in request.get("include", []))
    if kind == "note":
        return {"type": kind, "rows": [_note(int(note_id), rendered=rendered) for note_id in ids]}
    if kind == "card":
        return {"type": kind, "rows": [_card(int(card_id), rendered=rendered) for card_id in ids]}
    if kind == "model":
        rows = []
        for name in ids:
            model = col().models.by_name(str(name))
            if model:
                rows.append(
                    {
                        "id": model["id"],
                        "name": model["name"],
                        "fields": [field["name"] for field in model["flds"]],
                        "templates": [{"name": tmpl["name"], "qfmt": tmpl["qfmt"], "afmt": tmpl["afmt"]} for tmpl in model["tmpls"]],
                        "css": model.get("css", ""),
                    }
                )
        return {"type": kind, "rows": rows}
    if kind == "deck":
        rows = []
        for name in ids:
            deck = col().decks.by_name(str(name))
            if deck:
                rows.append(deck)
        return {"type": kind, "rows": rows}
    raise ToolError(f"Unknown inspect type: {kind}")


def _inventory(query: str, limit: int) -> dict[str, Any]:
    note_ids = col().find_notes(query)[:limit]
    deck_counts: Counter[str] = Counter()
    model_counts: Counter[str] = Counter()
    tag_counts: Counter[str] = Counter()
    field_presence: dict[str, Counter[str]] = defaultdict(Counter)
    blank_cards = 0
    card_count = 0

    for note_id in note_ids:
        row = _note(note_id, rendered=True)
        model_counts[row["model"]] += 1
        tag_counts.update(row["tags"])
        for name, value in row["fields"].items():
            field_presence[name]["present" if _strip(value) else "blank"] += 1
        for card in row["cards"]:
            card_count += 1
            deck_counts[card["deck"]] += 1
            if not _strip(card.get("questionText", "")) or "front of this card is blank" in _strip(card.get("questionText", "")).lower():
                blank_cards += 1

    return {
        "analysis": "inventory",
        "query": query,
        "noteCount": len(note_ids),
        "cardCount": card_count,
        "deckCounts": dict(deck_counts.most_common()),
        "modelCounts": dict(model_counts.most_common()),
        "topTags": dict(tag_counts.most_common(100)),
        "fieldPresence": {name: dict(counts) for name, counts in field_presence.items()},
        "blankRenderedCards": blank_cards,
        "truncated": len(col().find_notes(query)) > limit,
    }


def _blank_cards(query: str, limit: int, examples: int) -> dict[str, Any]:
    affected = []
    note_ids = col().find_notes(query)[:limit]
    for note_id in note_ids:
        row = _note(note_id, rendered=True)
        bad_cards = [
            card
            for card in row["cards"]
            if not _strip(card.get("questionText", "")) or "front of this card is blank" in _strip(card.get("questionText", "")).lower()
        ]
        if bad_cards:
            affected.append(
                {
                    "id": row["id"],
                    "model": row["model"],
                    "tags": row["tags"],
                    "populatedFields": {name: _strip(value) for name, value in row["fields"].items() if _strip(value)},
                    "badCards": bad_cards,
                }
            )
    return {
        "analysis": "blank-cards",
        "query": query,
        "scannedNotes": len(note_ids),
        "affectedNotes": len(affected),
        "examples": affected[:examples],
        "truncatedExamples": len(affected) > examples,
    }


def _duplicates(request: dict[str, Any]) -> dict[str, Any]:
    query = request.get("query", "")
    limit = int(request.get("limit", 50000))
    examples = int(request.get("examples", 25))
    prompt_fields = request.get("prompt_fields") or request.get("promptFields") or ["Front Text", "Front", "Question"]
    answer_fields = request.get("answer_fields") or request.get("answerFields") or ["Back Text", "Back", "Answer"]

    pair_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    prompt_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    note_ids = col().find_notes(query)[:limit]
    for note_id in note_ids:
        row = _note(note_id)
        prompt = _first_field(row["fields"], prompt_fields)
        answer = _first_field(row["fields"], answer_fields)
        item = {
            "id": row["id"],
            "model": row["model"],
            "tags": row["tags"],
            "prompt": _strip(prompt),
            "answer": _strip(answer),
            "cards": row["cards"],
            "answerNorm": _norm(answer),
        }
        prompt_norm = _norm(prompt)
        answer_norm = _norm(answer)
        if prompt_norm or answer_norm:
            pair_groups[f"{prompt_norm}\t{answer_norm}"].append(item)
        if prompt_norm:
            prompt_groups[prompt_norm].append(item)

    exact = [items for items in pair_groups.values() if len(items) > 1]
    same_prompt = [
        items
        for items in prompt_groups.values()
        if len(items) > 1 and len({item["answerNorm"] for item in items}) > 1
    ]
    exact.sort(key=len, reverse=True)
    same_prompt.sort(key=len, reverse=True)

    def sample(items: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "size": len(items),
            "prompt": items[0]["prompt"],
            "answer": items[0]["answer"],
            "notes": [{k: v for k, v in item.items() if k != "answerNorm"} for item in items[:5]],
        }

    return {
        "analysis": "duplicates",
        "query": query,
        "scannedNotes": len(note_ids),
        "exactPromptAnswerDuplicateClusters": len(exact),
        "exactPromptAnswerDuplicateNotes": sum(len(items) for items in exact),
        "samePromptDifferentAnswerClusters": len(same_prompt),
        "samePromptDifferentAnswerNotes": sum(len(items) for items in same_prompt),
        "exactExamples": [sample(items) for items in exact[:examples]],
        "samePromptDifferentAnswerExamples": [sample(items) for items in same_prompt[:examples]],
        "truncated": len(col().find_notes(query)) > limit,
    }


# analysis name -> (module, function). Each was its own tool; they differ only in
# which question they ask, which is what `analysis` now names.
ANALYSES = {
    "collection-stats": ("stats", "get_collection_stats"),
    "collection-stats-html": ("stats", "get_collection_stats_html"),
    "reviews": ("stats", "get_reviews"),
    "reviewed-by-day": ("stats", "get_num_cards_reviewed_by_day"),
    "empty-cards": ("stats", "get_empty_cards"),
    "integrity": ("stats", "check_integrity"),
    "deck-stats": ("decks", "get_deck_stats"),
    "deck-due-tree": ("decks", "get_deck_due_tree"),
    "due-cards": ("review", "get_due_cards"),
    "leeches": ("review", "get_leech_cards"),
    "memory-state": ("review", "get_card_memory_state"),
    "studied-today": ("review", "get_studied_today"),
    "retention": ("review", "get_retention_analysis"),
    "difficulty": ("review", "get_difficulty_distribution"),
    "forecast": ("review", "get_forecast"),
    "blank-cards-rich": ("analysis", "analyze_blank_cards"),
    "duplicates-rich": ("analysis", "analyze_duplicates_rich"),
    "inventory-rich": ("analysis", "deck_inventory_rich"),
}


def _analyze(request: dict[str, Any]) -> dict[str, Any]:
    import importlib

    analysis = request.get("analysis", "inventory")
    query = request.get("query", "")
    limit = int(request.get("limit", 50000))
    examples = int(request.get("examples", 25))

    if analysis == "inventory":
        return _inventory(query, limit)
    if analysis in ("blank-cards", "blank_cards"):
        return _blank_cards(query, limit, examples)
    if analysis == "duplicates":
        return _duplicates(request)

    if analysis in ANALYSES:
        module_name, func_name = ANALYSES[analysis]
        module = importlib.import_module(f".{module_name}", __package__)
        func = getattr(module, func_name)
        # Pass through only what the target actually accepts, so one flat request
        # shape serves analyses with quite different signatures.
        import inspect

        accepted = inspect.signature(func).parameters
        args = {k: v for k, v in request.items()
                if k in accepted and k not in ("cmd", "analysis")}
        return func(**args)

    raise ToolError(f"Unknown analysis: {analysis}",
                    hint=f"one of {sorted(set(ANALYSES) | {'inventory', 'blank-cards', 'duplicates'})}")


def _resolve_target_ids(target: dict[str, Any], entity: str) -> list[int]:
    if "ids" in target:
        return [int(x) for x in target["ids"]]
    query = target.get("query", "")
    where = target.get("where")
    if entity == "notes":
        ids = col().find_notes(query)
        if not where:
            return ids
        return [note_id for note_id in ids if _matches_where_note(_note(note_id, rendered=True), where)]
    if entity == "cards":
        return col().find_cards(query)
    raise ToolError(f"Unknown target entity: {entity}")


SET_ATTRS = ("flag", "suspended", "buried", "due", "ease", "deck", "notetype")
TRANSACT_OPS = ("set", "tag", "field", "delete", "forget", "answer")


def _card_ids(ids: list, entity: str) -> list:
    if entity == "cards":
        return ids
    return [card.id for note_id in ids for card in col().get_note(note_id).cards()]


def _apply_set(request: dict[str, Any], ids: list, entity: str) -> dict[str, Any]:
    """One op, one attribute enum - this is where five set-* tools collapse."""
    from . import cards as _cards
    from . import decks as _decks
    from . import notes as _notes

    attr = request.get("attr")
    value = request.get("value")
    if attr not in SET_ATTRS:
        raise ToolError(f"Unknown attr: {attr}", hint=f"one of {SET_ATTRS}")

    if attr == "deck":
        return _decks.change_deck(_card_ids(ids, entity), str(value))
    if attr == "notetype":
        return {"changed": [_notes.update_note_model(n, str(value)) for n in ids]}
    if attr == "flag":
        return _cards.set_card_flag(_card_ids(ids, entity), int(value))
    if attr == "suspended":
        return _cards.set_cards_suspended(_card_ids(ids, entity), bool(value))
    if attr == "buried":
        return _cards.set_cards_buried(_card_ids(ids, entity), bool(value))
    if attr == "due":
        return _cards.set_due_date(_card_ids(ids, entity), str(value))
    return _cards.set_ease_factors(_card_ids(ids, entity),
                                   [int(value)] * len(_card_ids(ids, entity)))


# from:"models" detail -> function. Each was its own get-shaped tool asking one
# question about a notetype definition.
MODEL_DETAILS = {
    "fields": ("models", "model_field_names"),
    "field-descriptions": ("models", "model_field_descriptions"),
    "field-fonts": ("models", "model_field_fonts"),
    "fields-on-templates": ("models", "model_fields_on_templates"),
    "styling": ("models", "model_styling"),
    "templates": ("models", "model_templates"),
}

EXPORT_FORMATS = {
    "apkg": ("backup", "export_deck"),
    "csv": ("backup", "export_notes_csv"),
    "research": ("backup", "export_for_research"),
    "rich": ("analysis", "export_notes_rich"),
}

DECK_CONFIG_OPS = {
    "get": ("decks", "get_deck_config"),
    "save": ("decks", "save_deck_config"),
    "set": ("decks", "set_deck_config_id"),
    "clone": ("decks", "clone_deck_config_id"),
    "delete": ("decks", "delete_deck_config"),
    "custom-study-defaults": ("review", "get_custom_study_defaults"),
    "custom-study": ("review", "create_custom_study"),
}


def _call(table: dict, key: str, request: dict[str, Any], what: str):
    """Dispatch to a delegated function, passing only the args it accepts."""
    import importlib
    import inspect

    if key not in table:
        raise ToolError(f"Unknown {what}: {key}", hint=f"one of {sorted(table)}")
    module_name, func_name = table[key]
    func = getattr(importlib.import_module(f".{module_name}", __package__), func_name)
    accepted = inspect.signature(func).parameters
    args = {k: v for k, v in request.items() if k in accepted}
    return func(**args)


ALTER_OPS = {
    "field-add": ("models", "model_field_add"),
    "field-remove": ("models", "model_field_remove"),
    "field-rename": ("models", "model_field_rename"),
    "field-reposition": ("models", "model_field_reposition"),
    "template-add": ("models", "model_template_add"),
    "template-remove": ("models", "model_template_remove"),
    "template-rename": ("models", "model_template_rename"),
    "template-reposition": ("models", "model_template_reposition"),
    "templates-set": ("models", "update_model_templates"),
    "styling-set": ("models", "update_model_styling"),
    "create": ("models", "create_model"),
    "deck-config-save": ("decks", "save_deck_config"),
    "deck-config-set": ("decks", "set_deck_config_id"),
    "deck-config-clone": ("decks", "clone_deck_config_id"),
    "deck-config-delete": ("decks", "delete_deck_config"),
}


def _alter(request: dict[str, Any]) -> dict[str, Any]:
    """Schema plane. Separate verb from transact because these force a full upload.

    Not journal-revertible: the datom model covers notes and cards, not notetype
    definitions. A snapshot is taken first so the change is always recoverable.
    """
    import importlib

    op = request.get("op")
    if op not in ALTER_OPS:
        raise ToolError(f"Unknown alter op: {op}", hint=f"one of {sorted(ALTER_OPS)}")

    args = {k: v for k, v in request.items() if k not in ("cmd", "op", "dry_run", "snapshot")}
    if request.get("dry_run", True):
        return {"cmd": "alter", "op": op, "args": args, "dry_run": True,
                "warning": "schema changes force a full AnkiWeb re-upload",
                "hint": "re-run with dry_run=false; a snapshot is taken automatically"}

    from . import _journal
    from .history import snapshot_create

    snapshot = snapshot_create(label=f"pre-alter-{op}")

    # Capture the notetype definitions before the change. Definition-only ops can
    # then be reverted from the journal; structural ones still need the snapshot.
    names = [args.get(k) for k in ("modelName", "model_name", "name") if args.get(k)]
    _journal.declare_schema(col(), names, op)

    module_name, func_name = ALTER_OPS[op]
    module = importlib.import_module(f".{module_name}", __package__)
    result = getattr(module, func_name)(**args)
    return {"cmd": "alter", "op": op, "dry_run": False, "snapshot": snapshot["snapshot"],
            "result": result,
            "revertible": op in _journal.DEFINITION_ONLY_OPS,
            "note": ("revertible from the journal" if op in _journal.DEFINITION_ONLY_OPS
                     else "structural: recover via snapshot-restore")}


def _transact(request: dict[str, Any]) -> dict[str, Any]:
    op = request.get("op")
    target = request.get("target") or {}
    entity = target.get("entity", "notes")
    dry_run = request.get("dry_run", True)
    if op not in TRANSACT_OPS:
        raise ToolError(f"Unknown mutation op: {op}", hint=f"one of {TRANSACT_OPS}")
    ids = _resolve_target_ids(target, entity)
    limit = request.get("limit")
    if limit is not None:
        ids = ids[: int(limit)]

    plan = {"cmd": "transact", "op": op, "entity": entity, "count": len(ids), "ids": ids[:100], "dry_run": dry_run}
    if dry_run:
        return plan

    # Declare resolved targets before mutating so the journal records an exact
    # pre-image. These ids come from a search, so no argument inspection can find them.
    if entity == "notes":
        from . import _journal
        _journal.declare_targets(col(), ids)

    from . import cards as _cards
    from . import notes as _notes

    window = mw()
    window.requireReset()
    try:
        if op == "set":
            return {**plan, "attr": request.get("attr"), "value": request.get("value"),
                    "result": _apply_set(request, ids, entity)}

        if op == "tag":
            if entity != "notes":
                raise ToolError("tag targets notes", hint='use target.entity="notes"')
            add = request.get("add") or []
            remove = request.get("remove") or []
            if not add and not remove:
                raise ToolError("tag requires add and/or remove")
            if add:
                col().tags.bulk_add(ids, " ".join(add))
            if remove:
                col().tags.bulk_remove(ids, " ".join(remove))
            return {**plan, "added": add, "removed": remove}

        if op == "field":
            if entity != "notes":
                raise ToolError("field targets notes")
            assignments = request.get("set") or {}
            if not assignments:
                raise ToolError("field requires set: {FieldName: value}")
            for note_id in ids:
                note = col().get_note(note_id)
                names = [f["name"] for f in note.note_type()["flds"]]
                for name, value in assignments.items():
                    if name not in names:
                        raise ToolError(f"No field {name!r} on note {note_id}",
                                        hint=f"fields are {names}")
                    note.fields[names.index(name)] = str(value)
                col().update_note(note)
            return {**plan, "fields_set": list(assignments)}

        if op == "delete":
            if entity != "notes":
                raise ToolError("delete targets notes; Anki deletes notes, not cards")
            return {**plan, "result": _notes.delete_notes(ids, confirmDeletion=True)}

        if op == "forget":
            return {**plan, "result": _cards.forget_cards(_card_ids(ids, entity))}

        # answer
        ease = int(request.get("ease", 3))
        return {**plan, "result": _cards.answer_cards(
            [{"cardId": c, "ease": ease} for c in _card_ids(ids, entity)])}
    finally:
        window.maybeReset()


@T("anki", "Unified CLI/Datalog-style Anki tool for query, inspect, analyze, and dry-run-first mutation",
   write=True)
def anki(request: dict[str, Any]) -> dict[str, Any]:
    """Run a high-level Anki command.

    Examples:
      {"cmd":"query","from":"notes","query":"deck:\"4 MATH\"","select":["id","model","fields"]}
      {"cmd":"analyze","analysis":"duplicates","query":"deck:\"4 MATH\""}
      {"cmd":"mutate","op":"tag","target":{"entity":"notes","query":"tag:duplicate"},"add_tags":["dedupe::candidate"]}
    """
    from . import _journal
    from . import timetravel as _tt

    cmd = request.get("cmd", "query")
    as_of = request.get("as_of")

    # Everything except mutate is a read; say so, so the log stays a log of facts.
    if cmd not in ("transact", "alter"):
        _journal.mark_read()

    if cmd in ("query", "search"):
        source = request.get("from", "notes")
        if as_of:
            # Time travel is a parameter, not a separate tool family.
            sql = request.get("sql") or _as_of_sql(request, source)
            return _tt.snapshot_query(as_of, sql, request.get("params"),
                                      int(request.get("limit", 200)))
        if source == "notes":
            return _query_notes(request)
        if source == "cards":
            return _query_cards(request)
        if source == "journal":
            return {"entries": _journal.read_entries(
                col().path, limit=int(request.get("limit", 20)), tool=request.get("tool"))}
        if source == "snapshots":
            from .history import snapshot_list
            return snapshot_list(limit=int(request.get("limit", 50)))
        if source == "decks":
            from .decks import list_decks
            return list_decks(pattern=request.get("pattern"),
                              limit=int(request.get("limit", 100)),
                              include_stats=bool(request.get("include_stats")))
        if source == "models":
            detail = request.get("detail")
            if detail:
                return _call(MODEL_DETAILS, detail, request, "model detail")
            from .models import list_models
            return list_models(pattern=request.get("pattern"),
                               limit=int(request.get("limit", 100)),
                               include_fields=bool(request.get("include_fields")))
        if source == "deck-config":
            return _call(DECK_CONFIG_OPS, request.get("op", "get"), request, "deck-config op")
        if source == "tags":
            from .tags import list_tags
            return list_tags(pattern=request.get("pattern"), limit=request.get("limit"))
        if source == "collection":
            from .timetravel import collection_info
            return collection_info()
        raise ToolError(
            f"Unknown query source: {source}",
            hint="notes, cards, decks, models, tags, collection, journal, snapshots",
        )
    if cmd == "inspect":
        return _inspect(request)
    if cmd == "analyze":
        return _analyze(request)
    if cmd == "diff":
        return _tt.snapshot_diff(request["a"], request["b"],
                                 entity=request.get("entity", "notes"),
                                 limit=int(request.get("limit", 200)),
                                 include_values=bool(request.get("include_values")))
    if cmd == "as-of":
        return _tt.snapshot_as_of(int(request["id"]), as_of or request["snapshot"])
    if cmd == "history":
        return {"note_id": request["id"],
                "facts": _journal.history(col().path, int(request["id"]),
                                          int(request.get("limit", 200)))}
    if cmd == "blame":
        return {"note_id": request["id"],
                "blame": _journal.blame(col().path, int(request["id"]))}
    if cmd == "speculate":
        from .speculate import speculate
        return speculate(request.get("from", "now"), request.get("ops") or [],
                         request.get("label", "spec"))
    if cmd == "export":
        return _call(EXPORT_FORMATS, request.get("format", "csv"), request, "export format")
    if cmd == "transact":
        return _transact(request)
    if cmd == "alter":
        return _alter(request)
    raise ToolError(
        f"Unknown cmd: {cmd}",
        hint=("query, inspect, analyze, diff, as-of, history, blame, "
              "speculate, transact, alter, export"),
    )


def _as_of_sql(request: dict[str, Any], source: str) -> str:
    """Default projection for an as-of query when no explicit sql is given."""
    if source not in ("notes", "cards"):
        raise ToolError(f"as_of queries support notes and cards, not {source}")
    columns = "id, mid, mod, usn, tags, flds" if source == "notes" else "id, nid, did, ord, due, queue, type, ivl"
    return f"SELECT {columns} FROM {source}"
