"""History tools - copy-on-write snapshots and the write journal.

Snapshots use `cp --reflink=auto`: on a CoW filesystem (btrfs/XFS/bcachefs) this is
near-instant and near-free; elsewhere it degrades to a full copy. The collection is
copied together with its -wal sidecar, so SQLite can recover a consistent state.

Two restore paths:
  snapshot-restore      in-process, mirroring Anki's own full-sync download path
                        (close_for_full_sync -> replace file -> reopen). Collection
                        only, no media.
  snapshot-restore-plan a script to run with Anki closed. Use for media restores or
                        when the collection will not open at all.
"""
import os
import shutil
import subprocess
import time

from . import _journal
from .base import T, ToolError, col, mw

SNAP_DIRNAME = "mcp-snapshots"

# Two families share the directory and must never be confused: snap-* are
# recovery points, spec-* are disposable speculative values. Sorting by name puts
# spec after snap, so an undiscriminating "newest" picks a throwaway.
SNAPSHOT_PREFIX = "snap-"
SPECULATIVE_PREFIX = "spec-"


def _profile_dir() -> str:
    return os.path.dirname(col().path)


def _snap_root() -> str:
    root = os.path.join(_profile_dir(), SNAP_DIRNAME)
    os.makedirs(root, exist_ok=True)
    return root


def _reflink(src: str, dst: str) -> None:
    """CoW copy where supported, full copy otherwise."""
    result = subprocess.run(
        ["cp", "-a", "--reflink=auto", src, dst],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise ToolError(f"copy failed: {result.stderr.strip()}", hint=f"{src} -> {dst}")


def _snapshot_dirs(prefix: str = SNAPSHOT_PREFIX) -> list:
    """Snapshot directory names of one family, newest first."""
    root = _snap_root()
    return sorted(
        (d for d in os.listdir(root)
         if d.startswith(prefix) and os.path.isdir(os.path.join(root, d))),
        reverse=True,
    )


def _tree_bytes(path: str) -> int:
    if os.path.isfile(path):
        return os.path.getsize(path)
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return total


@T("snapshot-create", "Copy-on-write snapshot of the collection (optionally media)")
def snapshot_create(label: str = None, include_media: bool = False):
    """Snapshot collection.anki2 (+ -wal) into <profile>/mcp-snapshots/."""
    collection = col()
    if hasattr(collection, "save"):
        try:
            collection.save()  # flush pending changes before copying
        except Exception:
            pass

    # Fold the WAL into the main file. Without this a snapshot is (db + wal) and
    # reading it read-only recreates -shm *inside the snapshot*, so the snapshot
    # mutates when queried; worse, copying the db alone silently yields stale rows.
    checkpoint = None
    try:
        checkpoint = collection.db.all("PRAGMA wal_checkpoint(TRUNCATE)")
    except Exception as e:
        checkpoint = f"unavailable: {e}"

    safe_label = "".join(c for c in (label or "") if c.isalnum() or c in "-_")[:40]
    name = time.strftime("snap-%Y%m%d-%H%M%S") + (f"-{safe_label}" if safe_label else "")
    dest = os.path.join(_snap_root(), name)
    if os.path.exists(dest):
        raise ToolError(f"Snapshot already exists: {name}")
    os.makedirs(dest)

    started = time.time()
    copied = []
    src_db = collection.path
    # -shm is derived state, never copied. -wal only if the checkpoint left data in it.
    for suffix in ("", "-wal"):
        src = src_db + suffix
        if os.path.exists(src) and os.path.getsize(src) > (0 if suffix else -1):
            _reflink(src, os.path.join(dest, os.path.basename(src)))
            copied.append(os.path.basename(src))

    media_src = os.path.join(_profile_dir(), "collection.media")
    if include_media and os.path.isdir(media_src):
        _reflink(media_src, os.path.join(dest, "collection.media"))
        copied.append("collection.media")

    return {
        "snapshot": name,
        "path": dest,
        "files": copied,
        "apparent_bytes": _tree_bytes(dest),
        "duration_ms": round((time.time() - started) * 1000, 1),
        "wal_checkpoint": checkpoint,
        "wal_bytes_after": os.path.getsize(src_db + "-wal") if os.path.exists(src_db + "-wal") else 0,
        "self_contained": copied == ["collection.anki2"],
        "note": "apparent size; on a CoW filesystem the extents are shared with the live collection",
    }


@T("snapshot-list", "List collection snapshots, newest first")
def snapshot_list(limit: int = 50):
    root = _snap_root()
    entries = []
    for name in sorted(os.listdir(root), reverse=True)[:limit]:
        path = os.path.join(root, name)
        if not os.path.isdir(path):
            continue
        entries.append({
            "snapshot": name,
            "path": path,
            "created": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(os.path.getmtime(path))),
            "apparent_bytes": _tree_bytes(path),
            "has_media": os.path.isdir(os.path.join(path, "collection.media")),
        })
    return {"snapshots": entries, "count": len(entries), "root": root}


@T("snapshot-prune", "Delete all but the newest N snapshots", write=True)
def snapshot_prune(keep: int = 10, keep_speculative: int = 3, confirm: bool = False):
    if keep < 1:
        raise ToolError("keep must be >= 1")
    root = _snap_root()
    snaps = _snapshot_dirs(SNAPSHOT_PREFIX)
    specs = _snapshot_dirs(SPECULATIVE_PREFIX)
    doomed = snaps[keep:] + specs[max(0, int(keep_speculative)):]
    kept = snaps[:keep] + specs[:max(0, int(keep_speculative))]
    if not confirm:
        return {"would_delete": doomed, "would_keep": kept, "confirm": False,
                "snapshots": len(snaps), "speculative": len(specs),
                "hint": "re-run with confirm=true to delete"}
    for name in doomed:
        shutil.rmtree(os.path.join(root, name))
    return {"deleted": doomed, "kept": kept, "confirm": True}


@T("snapshot-restore-plan", "Emit a script that restores a snapshot with Anki closed")
def snapshot_restore_plan(snapshot: str, include_media: bool = False):
    """Offline restore path: writes the exact script to run with Anki closed."""
    src = os.path.join(_snap_root(), snapshot)
    if not os.path.isdir(src):
        raise ToolError(f"No such snapshot: {snapshot}", hint="Use snapshot-list")

    db = os.path.join(src, "collection.anki2")
    if not os.path.isfile(db):
        raise ToolError(f"Snapshot has no collection.anki2: {snapshot}")

    profile = _profile_dir()
    stamp = time.strftime("%Y%m%d-%H%M%S")
    lines = [
        "#!/usr/bin/env bash",
        "# Generated by anki-mcp snapshot-restore-plan. Run with Anki CLOSED.",
        "set -euo pipefail",
        "",
        'if pgrep -x anki >/dev/null; then echo "Anki is running - close it first" >&2; exit 1; fi',
        "",
        f'PROFILE={profile!r}',
        f'SNAP={src!r}',
        f'PRE="$PROFILE/{SNAP_DIRNAME}/pre-restore-{stamp}"',
        "",
        '# 1. snapshot the CURRENT state before overwriting it',
        'mkdir -p "$PRE"',
        'cp -a --reflink=auto "$PROFILE/collection.anki2" "$PRE/" ',
        '[ -f "$PROFILE/collection.anki2-wal" ] && cp -a --reflink=auto "$PROFILE/collection.anki2-wal" "$PRE/" || true',
        "",
        '# 2. clear stale wal/shm so SQLite cannot replay them over the restored db',
        'rm -f "$PROFILE/collection.anki2-wal" "$PROFILE/collection.anki2-shm"',
        "",
        '# 3. restore',
        'cp -a --reflink=auto "$SNAP/collection.anki2" "$PROFILE/collection.anki2"',
        '[ -f "$SNAP/collection.anki2-wal" ] && cp -a --reflink=auto "$SNAP/collection.anki2-wal" "$PROFILE/" || true',
    ]
    if include_media:
        lines += [
            "",
            '# 4. restore media (only if the snapshot carries it)',
            'if [ -d "$SNAP/collection.media" ]; then',
            '  mv "$PROFILE/collection.media" "$PRE/collection.media"',
            '  cp -a --reflink=auto "$SNAP/collection.media" "$PROFILE/collection.media"',
            "fi",
        ]
    lines += ["", 'echo "restored $SNAP; previous state saved at $PRE"', ""]

    script_path = os.path.join(_snap_root(), f"restore-{snapshot}-{stamp}.sh")
    with open(script_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    os.chmod(script_path, 0o755)

    return {
        "snapshot": snapshot,
        "script": script_path,
        "run": f"bash {script_path}",
        "requires": "Anki must be closed",
        "safety": "the script snapshots current state before overwriting",
    }


@T("snapshot-restore", "Restore a snapshot in-process by closing and reopening the collection",
   write=True)
def snapshot_restore(snapshot: str, confirm: bool = False):
    """Swap a snapshot in while Anki stays running.

    Mirrors Anki's own full-sync download path: close_for_full_sync() -> replace the
    file -> reopen(after_full_sync=True). Media is out of scope here; use
    snapshot-restore-plan for a media restore with Anki closed.
    """
    src = os.path.join(_snap_root(), snapshot)
    src_db = os.path.join(src, "collection.anki2")
    if not os.path.isfile(src_db):
        raise ToolError(f"No collection.anki2 in snapshot: {snapshot}", hint="Use snapshot-list")

    collection = col()
    db_path = collection.path

    if not confirm:
        return {
            "snapshot": snapshot,
            "would_replace": db_path,
            "snapshot_bytes": os.path.getsize(src_db),
            "current_bytes": os.path.getsize(db_path),
            "confirm": False,
            "hint": "re-run with confirm=true; a pre-restore snapshot is taken automatically",
            "note": "media is not restored by this tool - use snapshot-restore-plan",
        }

    pre = snapshot_create(label="prerestore")

    collection.close_for_full_sync()
    swap_error = None
    try:
        for suffix in ("-wal", "-shm"):
            stale = db_path + suffix
            if os.path.exists(stale):
                os.remove(stale)
        _reflink(src_db, db_path)
        snap_wal = os.path.join(src, "collection.anki2-wal")
        if os.path.isfile(snap_wal):
            _reflink(snap_wal, db_path + "-wal")
    except Exception as e:
        swap_error = str(e)
    finally:
        collection.reopen(after_full_sync=True)
        try:
            mw().reset()
        except Exception:
            pass

    if swap_error:
        raise ToolError(
            f"Restore failed mid-swap: {swap_error}",
            hint=f"Collection reopened. Pre-restore snapshot: {pre['snapshot']}",
        )

    return {
        "restored": snapshot,
        "pre_restore_snapshot": pre["snapshot"],
        "collection": db_path,
        "notes_now": collection.db.scalar("SELECT count(*) FROM notes"),
        "confirm": True,
    }


@T("offsite-push", "Copy snapshots and the journal to another machine over rsync/ssh")
def offsite_push(destination: str, snapshots: int = 1, include_media: bool = False,
                 dry_run: bool = True):
    """Spatial durability. Snapshots share a disk with the live collection; sync
    mirrors state but keeps no history. Neither covers the other.

    rsync, not `btrfs send`: these snapshots are reflink copies inside a normal
    directory, not read-only subvolumes, so send/receive does not apply. Reflink
    sharing does not survive the transfer either - the destination pays full size.
    """
    # host:path for a remote, or an absolute path for an external disk / mount.
    if ":" not in destination and not os.path.isabs(destination):
        raise ToolError("destination must be host:path or an absolute local path",
                        hint="e.g. hbt-server:~/anki-history/ or /run/media/apollon/backup/anki/")

    profile = _profile_dir()
    # Reflink sharing does not survive the transfer, so every snapshot lands at
    # full size. Push the newest N as recovery points and rely on the journal for
    # history - it is the part that is small and irreplaceable.
    newest = _snapshot_dirs(SNAPSHOT_PREFIX)[:max(1, int(snapshots))]
    if not newest:
        raise ToolError("no snap-* recovery points to push", hint="run snapshot-create first")
    sources = [os.path.join(_snap_root(), d) for d in newest]
    sources.append(_journal.journal_dir(col().path))
    if include_media:
        sources.append(os.path.join(profile, "collection.media"))

    # No --delete: the destination accumulates history the source has pruned.
    cmd = ["rsync", "-a", "--partial"]
    if dry_run:
        cmd.append("--dry-run")
    cmd += ["--stats"] + sources + [destination]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if result.returncode != 0:
        raise ToolError(f"rsync failed ({result.returncode}): {result.stderr.strip()[:400]}",
                        hint="check ssh access to the destination host")

    stats = [line for line in result.stdout.splitlines()
             if line.startswith(("Number of files", "Total file size", "Total transferred"))]
    return {"destination": destination, "sources": sources, "dry_run": dry_run,
            "snapshots_pushed": len(newest), "stats": stats,
            "note": "reflink sharing is not preserved across the wire; each snapshot lands full size"}


@T("journal-tail", "Recent write-tool transactions, newest first")
def journal_tail(limit: int = 20, tool: str = None, include_pre_image: bool = False):
    entries = _journal.read_entries(col().path, limit=limit, tool=tool)
    if not include_pre_image:
        for entry in entries:
            pre = entry.get("pre_image") or {}
            entry["pre_image"] = {k: v for k, v in pre.items() if k != "notes"}
            entry["pre_image"]["notes_omitted"] = len((pre or {}).get("notes", []))
    return {"entries": entries, "count": len(entries),
            "journal_dir": _journal.journal_dir(col().path)}


@T("journal-revert", "Restore note fields and tags from a journal entry's pre-image", write=True)
def journal_revert(txid: str, confirm: bool = False):
    """Undo field/tag changes recorded for one transaction.

    Only reverts notes that still exist with a matching field count. Deletions and
    schema changes are out of scope - use snapshot-restore-plan for those.
    """
    matches = _journal.read_entries(col().path, limit=1, txid=str(txid))
    if not matches:
        raise ToolError(f"No journal entry with txid {txid}", hint="Use journal-tail")
    entry = matches[0]
    pre = entry.get("pre_image") or {}
    schema = entry.get("schema") or {}

    # Schema transactions carry a notetype pre-image instead of note rows.
    if schema:
        if not schema.get("revertible"):
            raise ToolError(
                f"Entry {txid} is a structural schema change ({schema.get('op')})",
                hint=f"{schema.get('reason')}; use snapshot-restore instead",
            )
        collection = col()
        if not confirm:
            return {"txid": txid, "tool": entry.get("tool"), "ts": entry.get("ts"),
                    "would_restore_notetypes": [m["name"] for m in schema.get("models", [])],
                    "confirm": False, "hint": "re-run with confirm=true to apply"}
        for model in schema.get("models", []):
            collection.models.update_dict(model)
        return {"txid": txid, "tool": entry.get("tool"),
                "notetypes_restored": [m["name"] for m in schema.get("models", [])],
                "confirm": True}

    if pre.get("mode") != "notes" or not pre.get("notes"):
        raise ToolError(
            f"Entry {txid} has no note pre-image (mode={pre.get('mode')})",
            hint="Not revertible from the journal; use snapshot-restore-plan",
        )

    plan, skipped, recreate = [], [], []
    collection = col()
    pre_note_ids = [r["id"] for r in pre.get("notes", [])]
    for row in pre["notes"]:
        try:
            note = collection.get_note(row["id"])
        except Exception:
            # Deleted. Content is recoverable; the original id and scheduling are
            # not - a recreated note gets new ids and new cards.
            recreate.append(row)
            continue
        old_fields = row["flds"].split("\x1f")
        if len(old_fields) != len(note.fields):
            skipped.append({"id": row["id"], "reason": "field count changed (notetype differs)"})
            continue
        if list(note.fields) == old_fields and " ".join(note.tags) == row["tags"].strip():
            continue
        plan.append((note, old_fields, row["tags"]))

    if not confirm:
        return {
            "txid": txid, "tool": entry.get("tool"), "ts": entry.get("ts"),
            "would_revert": len(plan), "would_restore_cards": len(pre.get("cards", [])),
            "would_recreate_deleted": len(recreate), "skipped": skipped, "confirm": False,
            "recreate_caveat": ("deleted notes come back with new ids and fresh scheduling; "
                                "snapshot-restore is the only exact recovery")
                               if recreate else None,
            "hint": "re-run with confirm=true to apply",
        }

    # Declare before applying, so a revert produces its own inverse datoms and is
    # itself revertible. Without this the log records that a revert happened but
    # not what it changed.
    _journal.declare_targets(collection, [note.id for note, _f, _t in plan] or pre_note_ids)

    for note, old_fields, old_tags in plan:
        note.fields = old_fields
        note.tags = old_tags.strip().split()
        collection.update_note(note)

    recreated = []
    for row in recreate:
        model = collection.models.get(row["mid"])
        if model is None:
            skipped.append({"id": row["id"], "reason": "notetype no longer exists"})
            continue
        note = collection.new_note(model)
        note.fields = row["flds"].split("\x1f")
        note.tags = row["tags"].strip().split()
        collection.add_note(note, collection.decks.selected())
        recreated.append({"old_id": row["id"], "new_id": note.id})

    # Card attributes: flag, suspend, bury, due, ease and deck live here, so a
    # note-only revert would silently leave them changed.
    cards_restored = 0
    for row in pre.get("cards", []):
        try:
            card = collection.get_card(row["id"])
        except Exception:
            skipped.append({"id": row["id"], "reason": "card no longer exists"})
            continue
        # Deck moves go through set_deck, not a did assignment: Anki keeps deck
        # membership consistent (original deck, filtered-deck state) there.
        moved = card.did != row["did"]
        if moved:
            collection.set_deck([card.id], row["did"])
            card = collection.get_card(row["id"])

        changed = False
        for attribute in ("type", "queue", "due", "ivl", "factor", "flags"):
            if getattr(card, attribute, None) != row[attribute]:
                setattr(card, attribute, row[attribute])
                changed = True
        if changed:
            collection.update_card(card)
        if changed or moved:
            cards_restored += 1

    return {"txid": txid, "tool": entry.get("tool"), "reverted": len(plan),
            "cards_restored": cards_restored, "recreated": recreated,
            "skipped": skipped, "confirm": True,
            "note": ("recreated notes have new ids and fresh scheduling"
                     if recreated else None)}
