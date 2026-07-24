"""Merge notes that describe the same fact, keeping the most complete content.

The DIVE decks were re-imported from Quizlet once per course year, so the same
term recurs across A0/A1/A2/C0/C1 with drift: capitalisation, trailing periods,
"#" for "number", and images present in some years but not others. Later years
sometimes extend the definition rather than restate it - for 67 terms the earlier
text is literally a prefix of the later one.

Merge rule, in two parts, because content and scheduling want different winners:

  content  - per field, the longest value in the group. Field-wise rather than
             note-wise, so a note holding only an image and a note holding only
             the long definition combine instead of one displacing the other.
  survivor - the note with review history if the group has one, else the note
             that already holds the most content. Deleting a studied note to
             keep a longer unstudied twin would discard real scheduling data.
"""
import re
from collections import defaultdict

from .base import T, ToolError, col

SEP = "\x1f"
TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")


def _key(value: str) -> str:
    """Comparison form of the first field: markup, case and punctuation removed."""
    text = TAG_RE.sub(" ", value or "").replace("&nbsp;", " ")
    text = re.sub(r"[^\w\s]", "", text.lower())
    return WS_RE.sub(" ", text).strip()


def _visible_len(value: str) -> int:
    """Length of the text a reader actually sees, so markup cannot win on bulk."""
    return len(WS_RE.sub(" ", TAG_RE.sub(" ", value or "")).strip())


def _richest(values: list[str]) -> str:
    """The most complete version of one field.

    An <img> is content even though it contributes no visible text, so a value
    carrying one outranks a bare value of equal prose length.
    """
    def score(v):
        return (_visible_len(v), 1 if "<img" in (v or "") else 0, len(v or ""))

    return max(values, key=score)


BODY_SIMILARITY = 0.6


def _body(fields: list[str], key_field: int) -> str:
    """Everything except the key field, normalised - the fact's actual content."""
    parts = [v for i, v in enumerate(fields) if i != key_field]
    text = TAG_RE.sub(" ", " ".join(parts)).replace("&nbsp;", " ")
    return WS_RE.sub(" ", re.sub(r"[^\w\s]", "", text.lower())).strip()


def _clusters(ids: list, rows: dict, key_field: int) -> list:
    """Partition a key group into clusters, each a set of one fact's versions.

    A shared key is not one fact: "quadratic equation" may have eight identical
    definitions plus one genuinely different one. Anchoring compatibility on the
    single richest note skipped the whole group whenever that richest note was the
    outlier - so the eight identical copies never merged. Clustering by mutual
    compatibility instead lets the eight collapse while the outlier stays its own
    note.

    Compatible means containment (a later year extending an earlier definition) or
    high similarity (cosmetic drift). An empty body (image-only) joins any cluster
    sharing its key, since it adds rather than contradicts. Returns a list of
    clusters; callers merge only those with 2+ members.
    """
    from difflib import SequenceMatcher

    bodies = {i: _body(rows[i]["fields"], key_field) for i in ids}

    def ok(a, b):
        x, y = bodies[a], bodies[b]
        if not x or not y:
            return True
        if x in y or y in x:
            return True
        return SequenceMatcher(None, x, y).ratio() >= BODY_SIMILARITY

    # Seed clusters richest-first, so each cluster's representative is its fullest
    # version; assign every note to the first cluster it matches, else open a new one.
    clusters: list[list] = []
    for i in sorted(ids, key=lambda i: -len(bodies[i])):
        for cluster in clusters:
            if ok(cluster[0], i):
                cluster.append(i)
                break
        else:
            clusters.append([i])
    return clusters


@T("merge-duplicates", "Merge same-key notes, keeping the most complete field values",
   write=True)
def merge_duplicates(query: str, key_field: int = 0, dry_run: bool = True,
                     limit: int = None):
    """Collapse notes sharing a normalised key_field into one note per key.

    Only merges within a single notetype: field indices are not comparable
    across notetypes, so a cross-notetype merge would scramble content.
    """
    if not query:
        raise ToolError("A query is required", hint='e.g. query="deck:\\"4 MATH::...\\""')

    note_ids = col().find_notes(query)
    if not note_ids:
        return {"groups": 0, "note": "query matched no notes"}

    rows = {}
    for nid in note_ids:
        note = col().get_note(nid)
        reps = max((c.reps for c in note.cards()), default=0)
        rows[nid] = {"mid": note.mid, "fields": list(note.fields), "reps": reps,
                     "tags": list(note.tags)}

    groups = defaultdict(list)
    for nid, row in rows.items():
        if key_field >= len(row["fields"]):
            continue
        k = _key(row["fields"][key_field])
        if k:
            groups[(row["mid"], k)].append(nid)

    plans, skipped = [], []
    for (mid, k), ids in sorted(groups.items(), key=lambda kv: kv[0][1]):
        if len(ids) < 2:
            continue
        # A matching key is not one fact. "A2" is Euclid's second axiom in one deck
        # and the Algebra 2 course label in another; "quadratic equation" has eight
        # identical definitions plus one different one. Cluster by mutual body
        # compatibility, then merge each cluster of 2+ on its own.
        any_merged = False
        for ids in _clusters(ids, rows, key_field):
            if len(ids) < 2:
                continue
            any_merged = True
            width = max(len(rows[i]["fields"]) for i in ids)
            merged = [
                _richest([rows[i]["fields"][f] if f < len(rows[i]["fields"]) else ""
                          for i in ids])
                for f in range(width)
            ]
            studied = [i for i in ids if rows[i]["reps"] > 0]
            if studied:
                # Most-reviewed note keeps its identity, and with it its cards.
                survivor = max(studied, key=lambda i: (rows[i]["reps"], i))
            else:
                survivor = max(ids, key=lambda i: sum(_visible_len(v)
                                                      for v in rows[i]["fields"]))
            losers = [i for i in ids if i != survivor]
            changed = merged != rows[survivor]["fields"][:len(merged)]
            # Union tags across the cluster: a position tag on a loser (the deck it
            # was drilled in) is data the survivor must inherit, or the merge loses
            # the very progression the tags encode.
            tag_union = sorted({t for i in ids for t in rows[i]["tags"]})
            plans.append({"key": k, "survivor": survivor, "delete": losers,
                          "merged": merged, "tags": tag_union,
                          "tags_added": sorted(set(tag_union) - set(rows[survivor]["tags"])),
                          "content_updated": changed,
                          "kept_studied": bool(studied),
                          "studied_lost": sum(1 for i in losers if rows[i]["reps"] > 0)})
        if not any_merged:
            skipped.append(k)

    if limit:
        plans = plans[: int(limit)]

    summary = {
        "groups": len(plans),
        "notes_before": sum(len(p["delete"]) + 1 for p in plans),
        "notes_after": len(plans),
        "to_delete": sum(len(p["delete"]) for p in plans),
        "survivors_rewritten": sum(1 for p in plans if p["content_updated"]),
        "groups_keeping_studied_note": sum(1 for p in plans if p["kept_studied"]),
        "studied_notes_deleted": sum(p["studied_lost"] for p in plans),
        "groups_skipped_incompatible": len(skipped),
        "skipped_keys": skipped[:15],
    }

    if dry_run:
        summary["dry_run"] = True
        summary["sample"] = [
            {"key": p["key"], "deletes": len(p["delete"]),
             "rewritten": p["content_updated"],
             "merged_preview": [_visible_len(v) for v in p["merged"]]}
            for p in plans[:12]
        ]
        summary["hint"] = "re-run with dry_run=false to apply"
        return summary

    from . import _journal

    touched = [p["survivor"] for p in plans] + [i for p in plans for i in p["delete"]]
    _journal.declare_targets(col(), touched)

    for plan in plans:
        note = col().get_note(plan["survivor"])
        merged = plan["merged"]
        for idx in range(min(len(note.fields), len(merged))):
            note.fields[idx] = merged[idx]
        note.tags = plan["tags"]              # union of the whole cluster's tags
        col().update_note(note)

    doomed = [i for p in plans for i in p["delete"]]
    if doomed:
        col().remove_notes(doomed)

    summary["dry_run"] = False
    summary["deleted"] = len(doomed)
    return summary
