"""
Rolling backup of Pakistan-airspace tracker state.

Before each scan we snapshot:
  - satellite_history.json
  - anomalies.json
  - forecast_15day.json (when present)
  - documents/                  (whole directory)

Into:
  Satellite_Tracker/backups/<YYYY-MM-DD>/

Retention: keep the 30 most recent date-named subdirectories.
"""

from __future__ import annotations
import datetime
import json
import os
import shutil
from typing import Iterable

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKUPS_DIR = os.path.join(BASE_DIR, "backups")

# Files / dirs we snapshot. Missing entries are skipped (cold-start safe).
SOURCE_FILES = [
    os.path.join(BASE_DIR, "satellite_history.json"),
    os.path.join(BASE_DIR, "anomalies.json"),
    os.path.join(BASE_DIR, "forecast_15day.json"),
    os.path.join(BASE_DIR, "tle_cache_celestrak.json"),
    # Schedule-change artefacts — the latest diff plus the rolling 15-day
    # history. Backed up so the "what changed each day" record survives a
    # disk loss and can be restored from any snapshot.
    os.path.join(BASE_DIR, "forecast_changes.json"),
    os.path.join(BASE_DIR, "forecast_changes_history.json"),
    os.path.join(BASE_DIR, "accuracy_track_record.json"),
]
SOURCE_DIRS = [
    os.path.join(BASE_DIR, "documents"),
]

KEEP_LAST = 30
DATE_FMT = "%Y-%m-%d"


def _safe_date_dir_name() -> str:
    # ISO date only — never any user input, never any path separator.
    return datetime.datetime.utcnow().strftime(DATE_FMT)


def snapshot() -> str:
    """
    Create a snapshot directory for today (UTC). Idempotent within a single
    day: re-running overwrites the same date directory.
    Returns the absolute path to the snapshot directory.
    """
    os.makedirs(BACKUPS_DIR, exist_ok=True)
    name = _safe_date_dir_name()
    dest = os.path.join(BACKUPS_DIR, name)
    os.makedirs(dest, exist_ok=True)

    manifest = {
        "snapshot_date_utc": name,
        "created_at": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "files": [],
        "dirs":  [],
        "skipped": [],
    }

    for src in SOURCE_FILES:
        if not os.path.isfile(src):
            manifest["skipped"].append(os.path.basename(src) + " (missing)")
            continue
        target = os.path.join(dest, os.path.basename(src))
        try:
            shutil.copy2(src, target)
            manifest["files"].append({
                "name": os.path.basename(src),
                "size_bytes": os.path.getsize(target),
            })
        except OSError as e:
            manifest["skipped"].append(f"{os.path.basename(src)} (copy error: {e})")

    for src in SOURCE_DIRS:
        if not os.path.isdir(src):
            manifest["skipped"].append(os.path.basename(src) + "/ (missing)")
            continue
        target = os.path.join(dest, os.path.basename(src))
        if os.path.exists(target):
            shutil.rmtree(target)
        try:
            shutil.copytree(src, target)
            count = sum(len(files) for _, _, files in os.walk(target))
            manifest["dirs"].append({
                "name": os.path.basename(src),
                "file_count": count,
            })
        except OSError as e:
            manifest["skipped"].append(f"{os.path.basename(src)}/ (copy error: {e})")

    with open(os.path.join(dest, "MANIFEST.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"[BACKUP] snapshot -> {dest}")
    print(f"[BACKUP] files: {len(manifest['files'])}, "
          f"dirs: {len(manifest['dirs'])}, "
          f"skipped: {len(manifest['skipped'])}")
    _rotate(KEEP_LAST)
    return dest


def _list_snapshots() -> list[str]:
    if not os.path.isdir(BACKUPS_DIR):
        return []
    entries = []
    for name in os.listdir(BACKUPS_DIR):
        full = os.path.join(BACKUPS_DIR, name)
        if not os.path.isdir(full):
            continue
        # Only consider strictly date-named directories — avoid wiping
        # any unrelated folder a user dropped in here.
        try:
            datetime.datetime.strptime(name, DATE_FMT)
        except ValueError:
            continue
        entries.append(name)
    return sorted(entries)


def _rotate(keep_last: int) -> None:
    snaps = _list_snapshots()
    if len(snaps) <= keep_last:
        return
    to_remove = snaps[: len(snaps) - keep_last]
    for name in to_remove:
        path = os.path.join(BACKUPS_DIR, name)
        try:
            shutil.rmtree(path)
            print(f"[BACKUP] rotated out: {name}")
        except OSError as e:
            print(f"[BACKUP] rotate failed for {name}: {e}")


def list_snapshots() -> list[dict]:
    """Return metadata for every retained snapshot — used by the dashboard."""
    out = []
    for name in _list_snapshots():
        manifest_path = os.path.join(BACKUPS_DIR, name, "MANIFEST.json")
        meta = {"date": name}
        if os.path.isfile(manifest_path):
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    meta.update(json.load(f))
            except (OSError, json.JSONDecodeError):
                pass
        out.append(meta)
    return out


if __name__ == "__main__":
    snapshot()
    print(f"\nRetained snapshots ({len(list_snapshots())}):")
    for s in list_snapshots():
        n_files = len(s.get("files", []))
        n_dirs = len(s.get("dirs", []))
        print(f"  - {s['date']}: {n_files} files, {n_dirs} dirs")
