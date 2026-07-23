"""FSRS enablement and parameter optimisation.

SM-2 has no model of forgetting over elapsed time: a card with a 14-day interval
last seen 647 days ago is simply presented, and failing it applies the same 20%
ease penalty as any lapse. That penalises a calendar gap as though it were card
difficulty, permanently. FSRS derives retrievability from elapsed time, so the
same gap is modelled rather than punished - which is why enabling it is the
first move on a long-dormant collection.
"""
from .base import T, ToolError, col


def _pb():
    from anki import deck_config_pb2

    return deck_config_pb2


@T("fsrs-status", "Whether FSRS is on, and how much history is available to train it")
def fsrs_status():
    reviewed = col().db.scalar("select count() from cards where reps > 0") or 0
    with_state = col().db.scalar(
        "select count() from cards where reps > 0 and data like '%\"s\"%'"
    ) or 0
    revlog = col().db.scalar("select count() from revlog") or 0
    # Reviews of type 0-3 are the ones FSRS trains on; manual reschedules (4/5)
    # carry no grade and are ignored.
    trainable = col().db.scalar("select count() from revlog where ease between 1 and 4") or 0

    presets = []
    for row in col().db.all("select id, name from deck_config"):
        presets.append({"id": row[0], "name": row[1]})

    return {
        "fsrs_enabled": with_state > 0,
        "cards_reviewed": reviewed,
        "cards_with_memory_state": with_state,
        "revlog_entries": revlog,
        "trainable_reviews": trainable,
        "presets": len(presets),
        "note": "FSRS needs roughly 1000 reviews to fit useful parameters",
    }


@T("fsrs-enable", "Enable FSRS and optimise parameters from review history", write=True)
def fsrs_enable(optimise: bool = True, reschedule: bool = False,
                health_check: bool = False, dry_run: bool = True):
    """Turn FSRS on across every preset, optionally fitting params from revlog.

    reschedule rewrites the due dates of existing cards from the new memory
    states. It is off by default: enabling FSRS and re-dating 3,000 cards in one
    step makes it impossible to tell which change caused what.
    """
    pb = _pb()
    trainable = col().db.scalar("select count() from revlog where ease between 1 and 4") or 0

    current = col().decks.get_deck_configs_for_update(col().decks.selected())
    configs = [entry.config for entry in current.all_config]

    if dry_run:
        return {
            "dry_run": True,
            "presets": [c.name for c in configs],
            "trainable_reviews": trainable,
            "would_set": {"fsrs": True, "optimise_all_presets": optimise,
                          "reschedule": reschedule, "health_check": health_check},
            "hint": "re-run with dry_run=false to apply",
            "warning": ("fewer than 1000 trainable reviews; parameters will be weak"
                        if trainable < 1000 else None),
        }

    mode = (pb.UPDATE_DECK_CONFIGS_MODE_COMPUTE_ALL_PARAMS if optimise
            else pb.UPDATE_DECK_CONFIGS_MODE_NORMAL)
    request = pb.UpdateDeckConfigsRequest(
        target_deck_id=col().decks.selected(),
        configs=configs,
        mode=mode,
        fsrs=True,
        fsrs_reschedule=bool(reschedule),
        fsrs_health_check=bool(health_check),
    )
    col().decks.update_deck_configs(request)

    after = col().db.scalar(
        "select count() from cards where reps > 0 and data like '%\"s\"%'"
    ) or 0
    return {
        "dry_run": False,
        "fsrs": True,
        "optimised": optimise,
        "rescheduled": reschedule,
        "presets_updated": len(configs),
        "trainable_reviews": trainable,
        "cards_with_memory_state": after,
    }
