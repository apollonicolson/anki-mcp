"""Higher-level collection analysis tools.

These tools intentionally stay read-only. They join note, card, deck, model,
field, rendered-card, and scheduling data so agents do not need to stitch large
Anki queries together by hand.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from html import unescape
import re
from typing import Any

from .base import T, col


_TAG_RE = re.compile(r"<[^>]+>")
_IMG_RE = re.compile(r"<img\b[^>]*>", re.I)
_BR_RE = re.compile(r"<br\s*/?>", re.I)
_SPACE_RE = re.compile(r"\s+")
_NON_TEXT_RE = re.compile(r"[^a-z0-9_+\-*/=<>^()., :;?\[\]{}|]+")

_SYMBOL_REPLACEMENTS = {
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


def _strip_html(value: Any) -> str:
    text = "" if value is None else str(value)
    text = unescape(text)
    text = _IMG_RE.sub(" [image] ", text)
    text = _BR_RE.sub(" ", text)
    text = _TAG_RE.sub(" ", text)
    text = text.replace("\xa0", " ")
    return _SPACE_RE.sub(" ", text).strip()


def _norm(value: Any) -> str:
    text = _strip_html(value).lower()
    for src, dst in _SYMBOL_REPLACEMENTS.items():
        text = text.replace(src, dst)
    text = _NON_TEXT_RE.sub(" ", text)
    return _SPACE_RE.sub(" ", text).strip()


def _field_map(note) -> dict[str, str]:
    model = note.note_type()
    return {field["name"]: note.fields[i] for i, field in enumerate(model["flds"])}


def _first_field(fields: dict[str, str], preferred: list[str] | None) -> str:
    if preferred:
        for name in preferred:
            value = fields.get(name)
            if value:
                return value
    for value in fields.values():
        if value:
            return value
    return ""


def _card_summary(card, include_rendered: bool = False) -> dict[str, Any]:
    item = {
        "cardId": card.id,
        "deckId": card.did,
        "deckName": col().decks.name(card.did),
        "ord": card.ord,
        "due": card.due,
        "type": card.type,
        "queue": card.queue,
        "interval": card.ivl,
        "factor": card.factor,
        "reps": card.reps,
        "lapses": card.lapses,
    }
    if include_rendered:
        question = card.question()
        answer = card.answer()
        item.update(
            {
                "question": question,
                "answer": answer,
                "questionText": _strip_html(question),
                "answerText": _strip_html(answer),
            }
        )
    return item


def _note_summary(note_id: int, include_rendered: bool = False) -> dict[str, Any]:
    note = col().get_note(note_id)
    model = note.note_type()
    fields = _field_map(note)
    cards = [_card_summary(card, include_rendered=include_rendered) for card in note.cards()]
    return {
        "noteId": note_id,
        "modelName": model["name"],
        "modelId": model["id"],
        "tags": note.tags,
        "fields": fields,
        "cards": cards,
    }


def _matching_note_ids(query: str, limit: int, offset: int) -> tuple[list[int], int, bool]:
    ids = col().find_notes(query)
    total = len(ids)
    page = ids[offset : offset + limit]
    return page, total, offset + limit < total


@T("export-notes-rich", "Export notes with fields plus card deck/scheduling/rendering metadata")
def export_notes_rich(
    query: str,
    limit: int = 100,
    offset: int = 0,
    include_rendered: bool = False,
):
    """Return note data joined with card metadata.

    Args:
        query: Anki browser query, e.g. deck:"4 MATH".
        limit: Max notes to return.
        offset: Pagination offset.
        include_rendered: Include rendered question/answer HTML and plain text.
    """
    note_ids, total, has_more = _matching_note_ids(query, limit, offset)
    notes = []
    for note_id in note_ids:
        try:
            notes.append(_note_summary(note_id, include_rendered=include_rendered))
        except Exception as exc:
            notes.append({"noteId": note_id, "error": str(exc)})
    return {
        "query": query,
        "notes": notes,
        "count": len(notes),
        "total": total,
        "offset": offset,
        "limit": limit,
        "hasMore": has_more,
    }


@T("deck-inventory-rich", "Summarize decks/models/fields/cards for notes matching an Anki query")
def deck_inventory_rich(query: str, limit: int = 50000):
    """Return aggregate inventory for a deck or arbitrary Anki query."""
    note_ids = col().find_notes(query)[:limit]
    deck_counts: Counter[str] = Counter()
    model_counts: Counter[str] = Counter()
    tag_counts: Counter[str] = Counter()
    field_presence: dict[str, Counter[str]] = defaultdict(Counter)
    card_state_counts: Counter[str] = Counter()
    blank_rendered_cards = 0
    card_count = 0

    for note_id in note_ids:
        note = col().get_note(note_id)
        model_name = note.note_type()["name"]
        model_counts[model_name] += 1
        for tag in note.tags:
            tag_counts[tag] += 1
        fields = _field_map(note)
        for field_name, value in fields.items():
            field_presence[field_name]["present" if _strip_html(value) else "blank"] += 1
        for card in note.cards():
            card_count += 1
            deck_counts[col().decks.name(card.did)] += 1
            card_state_counts[str(card.queue)] += 1
            if not _strip_html(card.question()):
                blank_rendered_cards += 1

    return {
        "query": query,
        "noteCount": len(note_ids),
        "cardCount": card_count,
        "deckCounts": dict(deck_counts.most_common()),
        "modelCounts": dict(model_counts.most_common()),
        "topTags": dict(tag_counts.most_common(100)),
        "fieldPresence": {name: dict(counts) for name, counts in field_presence.items()},
        "cardQueueCounts": dict(card_state_counts.most_common()),
        "blankRenderedCards": blank_rendered_cards,
        "truncated": len(col().find_notes(query)) > limit,
        "limit": limit,
    }


@T("analyze-blank-cards", "Find notes whose cards render blank or error-like prompts")
def analyze_blank_cards(query: str, limit: int = 1000, examples: int = 25):
    """Detect rendered blank-card problems and show populated note fields."""
    note_ids = col().find_notes(query)[:limit]
    affected = []
    total_cards = 0
    for note_id in note_ids:
        note = col().get_note(note_id)
        fields = _field_map(note)
        populated = {name: _strip_html(value) for name, value in fields.items() if _strip_html(value)}
        bad_cards = []
        for card in note.cards():
            total_cards += 1
            question_text = _strip_html(card.question())
            if not question_text or "front of this card is blank" in question_text.lower():
                bad_cards.append(
                    {
                        "cardId": card.id,
                        "deckName": col().decks.name(card.did),
                        "questionText": question_text,
                        "queue": card.queue,
                        "reps": card.reps,
                    }
                )
        if bad_cards:
            affected.append(
                {
                    "noteId": note_id,
                    "modelName": note.note_type()["name"],
                    "tags": note.tags,
                    "populatedFields": populated,
                    "badCards": bad_cards,
                }
            )
    return {
        "query": query,
        "scannedNotes": len(note_ids),
        "scannedCards": total_cards,
        "affectedNotes": len(affected),
        "examples": affected[:examples],
        "truncated": len(affected) > examples,
    }


@T("analyze-duplicates-rich", "Cluster exact and progressive duplicate note candidates")
def analyze_duplicates_rich(
    query: str,
    prompt_fields: list[str] | None = None,
    answer_fields: list[str] | None = None,
    limit: int = 50000,
    max_clusters: int = 50,
    examples_per_cluster: int = 5,
):
    """Analyze exact and same-prompt duplicate candidates.

    Args:
        prompt_fields: Preferred fields for prompt text. Defaults to Front Text, Front, Question.
        answer_fields: Preferred fields for answer text. Defaults to Back Text, Back, Answer.
    """
    prompt_fields = prompt_fields or ["Front Text", "Front", "Question"]
    answer_fields = answer_fields or ["Back Text", "Back", "Answer"]
    note_ids = col().find_notes(query)[:limit]
    pair_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    prompt_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for note_id in note_ids:
        note = col().get_note(note_id)
        fields = _field_map(note)
        prompt = _first_field(fields, prompt_fields)
        answer = _first_field(fields, answer_fields)
        prompt_text = _strip_html(prompt)
        answer_text = _strip_html(answer)
        prompt_norm = _norm(prompt)
        answer_norm = _norm(answer)
        item = {
            "noteId": note_id,
            "modelName": note.note_type()["name"],
            "tags": note.tags,
            "prompt": prompt_text,
            "answer": answer_text,
            "cards": [_card_summary(card) for card in note.cards()],
        }
        if prompt_norm or answer_norm:
            pair_groups[f"{prompt_norm}\t{answer_norm}"].append(item)
        if prompt_norm:
            prompt_groups[prompt_norm].append({**item, "answerNorm": answer_norm})

    exact_clusters = [items for items in pair_groups.values() if len(items) > 1]
    same_prompt_clusters = [
        items
        for items in prompt_groups.values()
        if len(items) > 1 and len({item["answerNorm"] for item in items}) > 1
    ]

    def summarize(items: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "size": len(items),
            "prompt": items[0]["prompt"],
            "answer": items[0]["answer"],
            "notes": [
                {k: v for k, v in item.items() if k != "answerNorm"}
                for item in items[:examples_per_cluster]
            ],
        }

    exact_clusters.sort(key=len, reverse=True)
    same_prompt_clusters.sort(key=len, reverse=True)
    return {
        "query": query,
        "scannedNotes": len(note_ids),
        "exactPromptAnswerDuplicateClusters": len(exact_clusters),
        "exactPromptAnswerDuplicateNotes": sum(len(items) for items in exact_clusters),
        "samePromptDifferentAnswerClusters": len(same_prompt_clusters),
        "samePromptDifferentAnswerNotes": sum(len(items) for items in same_prompt_clusters),
        "exactExamples": [summarize(items) for items in exact_clusters[:max_clusters]],
        "samePromptDifferentAnswerExamples": [
            summarize(items) for items in same_prompt_clusters[:max_clusters]
        ],
        "truncated": len(col().find_notes(query)) > limit,
        "limit": limit,
    }
