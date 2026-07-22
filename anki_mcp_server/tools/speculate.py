"""Speculative transactions - Datomic's d/with for an Anki collection.

A snapshot opens as a fully independent Collection: real backend, real card
generation, real business logic. Applying operations to that copy yields an
alternate database *value* you can query and diff. Dry-run reports intent; this
produces a result.

Run OUT OF PROCESS, deliberately. Speculating inside Anki's process works, but a
schema-modifying op there calls mod_schema(), which reaches the GUI and warns the
user that a full re-upload is required - a warning about the live collection that
is false, because only the copy changed. A subprocess also means a crash during
speculation cannot take Anki down, and no second Rust backend lives in Anki's heap.

Measured: opening a 145k-note snapshot as a Collection takes ~2 ms.
"""
import json
import os
import subprocess
import sys
import time

from .base import T, ToolError
from .history import _reflink, _snap_root, snapshot_create

OPS = ("tag", "untag", "retype")
TIMEOUT_SECONDS = 900

# Driver executed by Anki's bundled interpreter, never by the host python.
_DRIVER = r'''
import json, sys
from anki.collection import Collection

payload = json.loads(sys.argv[1])
col = Collection(payload["path"])
applied = []
try:
    for op in payload["ops"]:
        kind = op.get("op")
        ids = [int(i) for i in op.get("ids") or []]
        if not ids and op.get("query"):
            ids = col.find_notes(op["query"])
        if not ids:
            applied.append({"op": kind, "matched": 0, "note": "no notes matched"})
            continue
        if kind == "tag":
            col.tags.bulk_add(ids, " ".join(op.get("tags", [])))
            applied.append({"op": kind, "matched": len(ids), "tags": op.get("tags", [])})
        elif kind == "untag":
            col.tags.bulk_remove(ids, " ".join(op.get("tags", [])))
            applied.append({"op": kind, "matched": len(ids), "tags": op.get("tags", [])})
        elif kind == "retype":
            target = col.models.by_name(op.get("to") or "")
            if target is None:
                raise ValueError("retype requires a valid 'to' notetype: %r" % op.get("to"))
            source = col.models.get(col.models.get_single_notetype_of_notes(ids))
            if len(source["flds"]) != len(target["flds"]):
                raise ValueError(
                    "field count differs: %s has %d, %s has %d"
                    % (source["name"], len(source["flds"]), target["name"], len(target["flds"])))
            fmap = {f["ord"]: f["ord"] for f in source["flds"]}
            cmap = {t["ord"]: t["ord"] for t in source["tmpls"][:len(target["tmpls"])]}
            col.models.change(source, ids, target, fmap, cmap)
            applied.append({"op": kind, "matched": len(ids),
                            "from": source["name"], "to": target["name"]})
        else:
            raise ValueError("unknown speculative op: %r" % kind)
    result = {"ok": True, "applied": applied,
              "notes": col.note_count(), "cards": col.card_count()}
except Exception as e:
    result = {"ok": False, "error": "%s: %s" % (type(e).__name__, e), "applied": applied}
finally:
    col.close()
print("---RESULT---" + json.dumps(result))
'''


def _anki_runtime() -> tuple:
    """(interpreter, app_packages) for Anki's bundled Python.

    Derived from the installed anki package, never from sys.executable - inside
    Anki that is the launcher binary, and running it would start a second Anki.
    """
    import anki

    # anki.__file__ is None in the bundled build, so locate the package directory
    # via its search path, falling back to scanning sys.path.
    app_packages = None
    for candidate in list(getattr(anki, "__path__", []) or []):
        if os.path.isdir(candidate):
            app_packages = os.path.dirname(candidate)
            break
    if app_packages is None:
        for entry in sys.path:
            if entry and os.path.isdir(os.path.join(entry, "anki")):
                app_packages = entry
                break
    if app_packages is None:
        raise ToolError("could not locate Anki's app_packages directory")

    bin_dir = os.path.join(os.path.dirname(app_packages), "python", "bin")
    if os.path.isdir(bin_dir):
        candidates = sorted(
            (f for f in os.listdir(bin_dir) if f.startswith("python3.") and "-config" not in f),
            reverse=True,
        )
        for name in candidates:
            path = os.path.join(bin_dir, name)
            if os.access(path, os.X_OK):
                return path, app_packages
    raise ToolError(
        "Anki's bundled interpreter not found",
        hint=f"looked in {bin_dir}; speculation needs it to run out of process",
    )


def _fork(base: str, label: str) -> tuple:
    """Reflink a base snapshot into a new speculative value; return (name, base)."""
    if base in ("now", "live"):
        base = snapshot_create(label="specbase")["snapshot"]
    src = os.path.join(_snap_root(), base, "collection.anki2")
    if not os.path.isfile(src):
        raise ToolError(f"No such snapshot: {base}", hint="Use snapshot-list")

    safe = "".join(c for c in label if c.isalnum() or c in "-_")[:32] or "spec"
    name = time.strftime("spec-%Y%m%d-%H%M%S-") + safe
    dest = os.path.join(_snap_root(), name)
    os.makedirs(dest, exist_ok=True)
    _reflink(src, os.path.join(dest, "collection.anki2"))
    return name, base


def speculate(base: str = "now", ops: list = None, label: str = "spec"):
    """Produce an alternate collection value without touching the live collection.

    The result name feeds straight into anki {cmd:"diff"} or {cmd:"query", as_of:}.
    Schema-modifying ops (retype) are safe here: only the copy is marked for full
    upload, which is exactly what you want to inspect before committing.
    """
    if not ops:
        raise ToolError("speculate requires a non-empty ops list",
                        hint=f"ops are {OPS}, each with ids or query")
    for op in ops:
        if op.get("op") not in OPS:
            raise ToolError(f"Unknown speculative op: {op.get('op')}", hint=f"one of {OPS}")

    name, resolved_base = _fork(base, label)
    path = os.path.join(_snap_root(), name, "collection.anki2")
    interpreter, app_packages = _anki_runtime()

    env = dict(os.environ, PYTHONPATH=app_packages)
    started = time.time()
    proc = subprocess.run(
        [interpreter, "-c", _DRIVER, json.dumps({"path": path, "ops": ops})],
        capture_output=True, text=True, env=env, timeout=TIMEOUT_SECONDS,
    )
    marker = proc.stdout.rfind("---RESULT---")
    if proc.returncode != 0 or marker < 0:
        raise ToolError(
            f"speculation subprocess failed ({proc.returncode})",
            hint=(proc.stderr or proc.stdout)[-400:],
            discarded_value=name,
        )
    result = json.loads(proc.stdout[marker + len("---RESULT---"):])
    if not result.get("ok"):
        raise ToolError(f"speculation failed: {result.get('error')}", discarded_value=name)

    return {
        "value": name,
        "base": resolved_base,
        "applied": result["applied"],
        "notes": result["notes"],
        "cards": result["cards"],
        "duration_ms": round((time.time() - started) * 1000, 1),
        "isolation": "subprocess",
        "next": [f'anki {{"cmd":"diff","a":"{resolved_base}","b":"{name}"}}',
                 f'anki {{"cmd":"query","as_of":"{name}","sql":"SELECT ..."}}'],
        "note": "speculative value only; the live collection was never opened",
    }
