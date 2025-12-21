"""Review and scheduling tools."""
from .base import T, ToolError, col


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


@T("get-leech-cards", "Find cards marked as leeches or frequently failed")
def get_leech_cards(deck_name: str = None, threshold: int = 8):
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
                "cardId": cid, "noteId": n.id, "lapses": c.lapses,
                "ease": c.factor, "interval": c.ivl,
                "question": c.question()[:200],
                "deckName": col().decks.name(c.did),
            })

    return {"leeches": sorted(leeches, key=lambda x: -x["lapses"]), "count": len(leeches)}


@T("get-card-memory-state", "Get FSRS stability, difficulty, retrievability for cards")
def get_card_memory_state(cards: list[int]):
    result = []
    for cid in cards:
        try:
            c = col().get_card(cid)
            state = {
                "cardId": cid,
                "stability": c.memory_state.stability if hasattr(c, 'memory_state') and c.memory_state else None,
                "difficulty": c.memory_state.difficulty if hasattr(c, 'memory_state') and c.memory_state else None,
                "interval": c.ivl, "ease": c.factor, "lapses": c.lapses, "reps": c.reps,
            }
            result.append(state)
        except Exception as e:
            result.append({"cardId": cid, "error": str(e)})
    return {"cards": result}


@T("get-studied-today", "Get today's study session summary")
def get_studied_today():
    studied = col().studied_today()
    cutoff = col().sched.day_cutoff * 1000

    reviews_today = col().db.scalar("select count() from revlog where id > ?", cutoff)
    time_today = col().db.scalar("select sum(time) from revlog where id > ?", cutoff) or 0

    return {
        "cardsStudied": studied[0] if studied else 0,
        "timeSpentMs": time_today,
        "timeSpentMinutes": round(time_today / 60000, 1),
        "reviewCount": reviews_today,
        "message": studied[1] if studied and len(studied) > 1 else "",
    }


@T("get-retention-analysis", "Analyze success rate by interval length")
def get_retention_analysis(deck_name: str = None):
    query = "is:review"
    if deck_name:
        query += f' deck:"{deck_name}"'
    cards = col().find_cards(query)

    buckets = {
        "1-7 days": {"correct": 0, "total": 0},
        "8-30 days": {"correct": 0, "total": 0},
        "31-90 days": {"correct": 0, "total": 0},
        "91-180 days": {"correct": 0, "total": 0},
        "180+ days": {"correct": 0, "total": 0},
    }

    for cid in cards[:1000]:
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
        if c.factor >= 2500:
            buckets[bucket]["correct"] += 1

    result = {}
    for name, data in buckets.items():
        if data["total"] > 0:
            result[name] = {"total": data["total"], "retentionRate": round(data["correct"] / data["total"] * 100, 1)}

    return {"retention": result}


@T("get-difficulty-distribution", "Get cards grouped by difficulty level")
def get_difficulty_distribution(deck_name: str = None):
    query = "is:review"
    if deck_name:
        query += f' deck:"{deck_name}"'
    cards = col().find_cards(query)

    distribution = {"easy": [], "medium": [], "hard": [], "very_hard": []}

    for cid in cards:
        c = col().get_card(cid)
        factor = c.factor / 1000

        if factor >= 2.5:
            distribution["easy"].append(cid)
        elif factor >= 2.0:
            distribution["medium"].append(cid)
        elif factor >= 1.5:
            distribution["hard"].append(cid)
        else:
            distribution["very_hard"].append(cid)

    return {
        "distribution": {k: {"count": len(v), "cardIds": v[:10]} for k, v in distribution.items()},
        "total": len(cards),
    }


@T("get-forecast", "Predict cards due in coming days")
def get_forecast(days: int = 30):
    today = col().sched.today
    forecast = []

    for i in range(days):
        due_day = today + i
        count = col().db.scalar("select count() from cards where queue = 2 and due = ?", due_day) or 0
        forecast.append({"day": i, "due": count})

    return {"forecast": forecast, "days": days}


@T("create-custom-study", "Create a custom study session", write=True)
def create_custom_study(deck_name: str, mode: str, limit: int = 100):
    deck = col().decks.by_name(deck_name)
    if not deck:
        raise ToolError(f"Deck not found: {deck_name}")

    from anki.scheduler.base import CustomStudyRequest

    mode_map = {"new": 1, "review": 2, "forgot": 3, "random": 4}
    if mode not in mode_map:
        raise ToolError(f"Invalid mode: {mode}. Use: new, review, forgot, random")

    request = CustomStudyRequest(deck_id=deck["id"], custom_study_mode=mode_map[mode], card_limit=limit)
    col().sched.custom_study(request)
    return {"created": True, "mode": mode, "deck": deck_name, "limit": limit}


@T("get-custom-study-defaults", "Get available options for custom study")
def get_custom_study_defaults(deck_name: str):
    deck = col().decks.by_name(deck_name)
    if not deck:
        raise ToolError(f"Deck not found: {deck_name}")

    defaults = col().sched.custom_study_defaults(deck["id"])
    return {
        "deckName": deck_name,
        "availableNew": defaults.available_new,
        "availableReview": defaults.available_review,
        "defaults": {"extendNew": defaults.extend_new, "extendReview": defaults.extend_review},
    }


@T("extend-limits", "Extend daily new/review card limits", write=True)
def extend_limits(deck_name: str, new_delta: int = 0, review_delta: int = 0):
    deck = col().decks.by_name(deck_name)
    if not deck:
        raise ToolError(f"Deck not found: {deck_name}")

    col().sched.extend_limits(deck_id=deck["id"], new_delta=new_delta, review_delta=review_delta)
    return {"extended": True, "deckName": deck_name, "newDelta": new_delta, "reviewDelta": review_delta}


@T("create-filtered-deck", "Create a filtered/cram deck", write=True)
def create_filtered_deck(name: str, search: str, order: int = 0, limit: int = 100):
    result = col().sched.get_or_create_filtered_deck(deck_id=0)
    config = result.config

    config.search_terms[0].search = search
    config.search_terms[0].limit = limit
    config.search_terms[0].order = order

    deck = col().decks.get(result.id)
    deck["name"] = name
    col().decks.save(deck)

    col().sched.add_or_update_filtered_deck(config)
    col().sched.rebuild_filtered_deck(result.id)

    return {"deckId": result.id, "name": name, "search": search}


@T("rebuild-filtered-deck", "Rebuild filtered deck contents", write=True)
def rebuild_filtered_deck(deck_id: int):
    count = col().sched.rebuild_filtered_deck(deck_id)
    return {"rebuilt": True, "deckId": deck_id, "cardCount": count}
