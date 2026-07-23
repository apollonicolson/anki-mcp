"""Card management tools."""
from .base import T, ToolError, col


def find_cards(query: str, limit: int = 100, offset: int = 0):
    """Search for cards with pagination."""
    all_cards = col().find_cards(query)
    total = len(all_cards)
    cards = all_cards[offset:offset + limit]
    return {"cardIds": cards, "count": len(cards), "total": total, "hasMore": offset + limit < total, "offset": offset, "limit": limit}








def set_ease_factors(cards: list[int], easeFactors: list[int]):
    if len(cards) != len(easeFactors):
        raise ToolError("cards and easeFactors must have same length")
    for cid, factor in zip(cards, easeFactors):
        c = col().get_card(cid)
        c.factor = factor
        col().update_card(c)
    return {"updated": len(cards)}


def set_cards_suspended(cards: list[int], suspended: bool = True):
    if suspended:
        col().sched.suspend_cards(cards)
    else:
        col().sched.unsuspend_cards(cards)
    return {"cards": len(cards), "suspended": suspended}




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


def set_card_flag(cards: list[int], flag: int):
    if not 0 <= flag <= 7:
        raise ToolError("Flag must be 0-7")
    col().set_user_flag_for_cards(flag, cards)
    return {"flagged": len(cards), "flag": flag}


def forget_cards(cards: list[int]):
    col().sched.schedule_cards_as_new(cards)
    return {"reset": len(cards)}


def set_due_date(cards: list[int], days: str):
    col().sched.set_due_date(cards, days)
    return {"rescheduled": len(cards), "days": days}


@T("reposition-new", "Set the new-card queue order for cards", write=True)
def reposition_new(query: str = None, cards: list[int] = None, starting_from: int = 1,
                   step_size: int = 1, randomize: bool = False,
                   shift_existing: bool = False, order_by_note_id: bool = True):
    """Give new cards an explicit queue position.

    add_note takes its position from the deck config, and a collection set to
    random insertion scatters a lesson sequence. Sequenced material (a book worked
    chapter by chapter) needs position to follow source order, so it is set here
    rather than left to the config.

    order_by_note_id sorts ascending before assigning, which matches insertion
    order for notes added in one batch.
    """
    if not query and not cards:
        raise ToolError("Name the cards: pass query or cards")
    ids = [int(c) for c in cards] if cards else col().find_cards(query)
    if not ids:
        return {"repositioned": 0, "note": "no cards matched"}
    if order_by_note_id:
        ids = sorted(ids, key=lambda cid: (col().get_card(cid).nid, cid))

    changes = col().sched.reposition_new_cards(
        card_ids=ids, starting_from=int(starting_from), step_size=int(step_size),
        randomize=bool(randomize), shift_existing=bool(shift_existing),
    )
    return {"repositioned": getattr(changes, "count", len(ids)),
            "cards": len(ids), "starting_from": starting_from,
            "step_size": step_size, "randomize": randomize,
            "shift_existing": shift_existing}


def answer_cards(answers: list[dict]):
    for a in answers:
        c = col().get_card(a["cardId"])
        col().sched.answerCard(c, a["ease"])
    return {"answered": len(answers)}








@T("relearn-cards", "Set cards to relearn state", write=True)
def relearn_cards(cards: list[int]):
    for cid in cards:
        c = col().get_card(cid)
        c.type = 3
        c.queue = 1
        col().update_card(c)
    return {"relearning": len(cards)}
