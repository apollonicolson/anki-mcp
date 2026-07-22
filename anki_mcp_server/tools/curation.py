"""Curation tools - collection hygiene: notetype sprawl, mergeability."""
import hashlib

from .base import T, ToolError, col


def _field_sig(model):
    return [f["name"] for f in model["flds"]]


def _template_hash(model):
    """Stable hash over card generation shape: template names + both formats + css."""
    h = hashlib.sha1()
    for t in model["tmpls"]:
        h.update(f"\x1f{t['name']}\x1f{t['qfmt']}\x1f{t['afmt']}".encode())
    h.update(f"\x1e{model.get('css', '')}".encode())
    return h.hexdigest()[:12]


@T("notetype-audit", "Group notetypes by identical field signature to find merge candidates")
def notetype_audit(min_cluster: int = 2, pattern: str = None, members_limit: int = 25):
    """Report notetypes sharing a field signature, plus unused ones.

    A cluster with one distinct template_hash is a safe merge: same fields, same
    card generation. Multiple hashes means merging would change how cards render.
    """
    if min_cluster < 1:
        raise ToolError("min_cluster must be >= 1")

    note_counts = dict(col().db.all("SELECT mid, count(*) FROM notes GROUP BY mid"))

    clusters, unused = {}, []
    for entry in col().models.all_names_and_ids():
        if pattern and pattern.lower() not in entry.name.lower():
            continue
        model = col().models.get(entry.id)
        if model is None:
            continue

        n = note_counts.get(entry.id, 0)
        if n == 0:
            unused.append({"name": entry.name, "id": entry.id})

        sig = _field_sig(model)
        clusters.setdefault(tuple(sig), {"fields": sig, "members": []})["members"].append({
            "name": entry.name,
            "id": entry.id,
            "notes": n,
            "templates": len(model["tmpls"]),
            "template_hash": _template_hash(model),
        })

    out = []
    for cluster in clusters.values():
        members = sorted(cluster["members"], key=lambda m: -m["notes"])
        if len(members) < min_cluster:
            continue
        hashes = {m["template_hash"] for m in members}
        out.append({
            "fields": cluster["fields"],
            "notetypes": len(members),
            "notes": sum(m["notes"] for m in members),
            "identical_templates": len(hashes) == 1,
            "distinct_template_shapes": len(hashes),
            "largest": members[0]["name"],
            "members": members if members_limit <= 0 else members[:members_limit],
            "members_truncated": 0 if members_limit <= 0 else max(0, len(members) - members_limit),
        })

    out.sort(key=lambda c: (-c["notetypes"], -c["notes"]))
    return {
        "totals": {
            "notetypes": len(col().models.all_names_and_ids()),
            "notes": sum(note_counts.values()),
            "unused_notetypes": len(unused),
            "clusters": len(out),
            "notetypes_in_clusters": sum(c["notetypes"] for c in out),
        },
        "clusters": out,
        "unused": sorted(unused, key=lambda u: u["name"]),
    }
