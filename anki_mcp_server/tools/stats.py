"""Statistics and collection info tools."""
import os
from datetime import datetime
from .base import T, ToolError, col


def get_collection_stats():
    return {
        "totalCards": col().card_count(),
        "totalNotes": col().note_count(),
        "totalDecks": len(col().decks.all()),
        "totalModels": len(col().models.all()),
        "reviewsToday": col().db.scalar("select count() from revlog where id > ?", col().sched.day_cutoff * 1000),
    }


def get_num_cards_reviewed_by_day(num_days: int = 30):
    cutoff = col().sched.day_cutoff
    result = []
    for i in range(num_days):
        start = (cutoff - (i + 1) * 86400) * 1000
        end = (cutoff - i * 86400) * 1000
        count = col().db.scalar("select count() from revlog where id >= ? and id < ?", start, end)
        result.append({"day": -i, "count": count})
    return {"reviews": result}


def get_collection_stats_html(whole_collection: bool = True):
    from aqt import mw
    from aqt.stats import NewDeckStats
    stats = NewDeckStats(mw, mw.col, whole_collection)
    return {"html": stats.report()}


def get_reviews(card_ids: list[int] = None, deck: str = None, start_id: int = 0, detailed: bool = False):
    if deck:
        deck_obj = col().decks.by_name(deck)
        if not deck_obj:
            raise ToolError(f"Deck not found: {deck}")
        card_ids = col().find_cards(f'deck:"{deck}"')

    if not card_ids:
        return {"reviews": [], "count": 0}

    if detailed:
        reviews = col().db.all(
            "select id, cid, ease, ivl, lastIvl, factor, time, type from revlog where cid in %s and id > ? order by id" % str(tuple(card_ids)),
            start_id
        )
        result = [{"id": r[0], "cardId": r[1], "ease": r[2], "interval": r[3], "lastInterval": r[4], "factor": r[5], "time": r[6], "type": r[7]} for r in reviews]
    else:
        reviews = col().db.all(
            "select id, cid, ease, ivl, time from revlog where cid in %s and id > ?" % str(tuple(card_ids)),
            start_id
        )
        result = [{"id": r[0], "cardId": r[1], "ease": r[2], "interval": r[3], "time": r[4]} for r in reviews]

    return {"reviews": result, "count": len(result)}


T("get-latest-review-id", "Get the latest review ID", lambda: col().db.scalar("select max(id) from revlog") or 0)


@T("insert-reviews", "Insert review history entries", write=True)
def insert_reviews(reviews: list[dict]):
    for r in reviews:
        col().db.execute(
            "insert into revlog values (?,?,?,?,?,?,?,?,?)",
            r["id"], r["cid"], r["usn"], r["ease"], r["ivl"],
            r["lastIvl"], r["factor"], r["time"], r["type"]
        )
    return {"inserted": len(reviews)}


def get_collection_info():
    from aqt import mw
    return {
        "path": col().path,
        "mediaPath": col().media.dir(),
        "modTime": col().mod,
        "schemaVersion": col().db.scalar("select ver from col"),
        "profileName": mw.pm.name,
        "profilePath": mw.pm.profileFolder(),
    }


def get_empty_cards():
    report = col().get_empty_cards()
    return {
        "emptyNotes": [{"noteId": n.note_id, "cardId": n.card_id, "template": n.template_index} for n in report.notes],
        "count": len(report.notes),
        "message": report.report if hasattr(report, 'report') else "",
    }


def find_duplicates(field_name: str, deck_name: str = None):
    query = f'deck:"{deck_name}"' if deck_name else ""
    dupes = col().find_dupes(field_name, query)
    return {"duplicates": [{"value": d[0], "noteIds": list(d[1])} for d in dupes], "count": len(dupes)}


def check_integrity(fix: bool = False):
    if fix:
        result = col().fix_integrity()
    else:
        result = col().db.scalar("pragma integrity_check")
    return {"checked": True, "fixed": fix, "result": str(result)}


@T("optimize-database", "Vacuum and analyze database for better performance")
def optimize_database():
    col().optimize()
    return {"optimized": True, "message": "Database vacuumed and analyzed"}
