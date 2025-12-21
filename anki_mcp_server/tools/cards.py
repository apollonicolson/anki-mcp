"""Card management tools."""
from .base import T, ToolError, col


@T("find-cards", "Search for cards using Anki query syntax")
def find_cards(query: str, limit: int = 100, offset: int = 0):
    """Search for cards with pagination."""
    all_cards = col().find_cards(query)
    total = len(all_cards)
    cards = all_cards[offset:offset + limit]
    return {"cardIds": cards, "count": len(cards), "total": total, "hasMore": offset + limit < total, "offset": offset, "limit": limit}


@T("get-cards-info", "Get detailed info about cards")
def get_cards_info(cards: list[int]):
    result = []
    for cid in cards:
        try:
            c = col().get_card(cid)
            n = c.note()
            result.append({
                "cardId": cid, "noteId": n.id, "deckId": c.did,
                "deckName": col().decks.name(c.did), "modelName": n.note_type()["name"],
                "question": c.question(), "answer": c.answer(),
                "due": c.due, "type": c.type, "queue": c.queue,
                "interval": c.ivl, "factor": c.factor, "reps": c.reps, "lapses": c.lapses,
            })
        except:
            result.append({"cardId": cid, "error": "Not found"})
    return {"cards": result}


@T("get-notes-for-cards", "Get note IDs for cards")
def get_notes_for_cards(cards: list[int]):
    mapping = {str(cid): col().get_card(cid).nid for cid in cards}
    unique_notes = list(set(mapping.values()))
    return {"mapping": mapping, "uniqueNoteIds": unique_notes, "cardCount": len(cards), "noteCount": len(unique_notes)}


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
    if suspended:
        col().sched.suspend_cards(cards)
    else:
        col().sched.unsuspend_cards(cards)
    return {"cards": len(cards), "suspended": suspended}


@T("are-suspended", "Check if cards are suspended")
def are_suspended(cards: list[int]):
    return {str(cid): col().get_card(cid).queue == -1 for cid in cards}


@T("set-cards-buried", "Set buried state for cards", write=True)
def set_cards_buried(cards: list[int] = None, buried: bool = True):
    if buried:
        if not cards:
            raise ToolError("cards required when burying")
        col().sched.bury_cards(cards)
        return {"cards": len(cards), "buried": True}
    if cards:
        col().sched.unbury_cards(cards)
        return {"cards": len(cards), "buried": False}
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
        c = col().get_card(a["cardId"])
        col().sched.answerCard(c, a["ease"])
    return {"answered": len(answers)}


@T("are-due", "Check if cards are due")
def are_due(cards: list[int]):
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
        c.type = 3
        c.queue = 1
        col().update_card(c)
    return {"relearning": len(cards)}
