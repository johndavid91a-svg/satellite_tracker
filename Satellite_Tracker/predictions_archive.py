"""
Immutable per-day prediction archive.

Every successful run of `forecast_15day.run()` snapshots the freshly-computed
forecast into:

    Satellite_Tracker/predictions_archive/<YYYY-MM-DD>/forecast.json
    Satellite_Tracker/predictions_archive/<YYYY-MM-DD>/MANIFEST.json

These are NEVER overwritten on subsequent same-day runs (the first archive
of the day wins — that's what we'll evaluate accuracy against).

Why this is separate from `backups/`:
  - `backups/` is rolling state for disaster recovery (rotated to last 30).
  - `predictions_archive/` is the historical record of what we PREDICTED on
    each day, kept intact so the dashboard can show
    "predicted-on-day-X vs actual-on-day-Y" accuracy over time.

Retention: keep last 90 archives (rolling).
"""

from __future__ import annotations
import datetime
import json
import os
import shutil

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
ARCHIVE_DIR = os.path.join(BASE_DIR, "predictions_archive")
FORECAST    = os.path.join(BASE_DIR, "forecast_15day.json")
KEEP_LAST   = 90


def archive_current_forecast() -> str | None:
    """
    Copy the current forecast_15day.json into predictions_archive/<today>/.
    No-op (returns None) if today's archive already exists — we keep the
    FIRST snapshot of each day so the comparison baseline is stable.
    """
    if not os.path.isfile(FORECAST):
        print("[ARCHIVE] no forecast_15day.json — nothing to archive")
        return None

    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    today = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    dest_dir = os.path.join(ARCHIVE_DIR, today)
    dest_file = os.path.join(dest_dir, "forecast.json")
    if os.path.isfile(dest_file):
        print(f"[ARCHIVE] {today} already archived — leaving as-is")
        return dest_file

    os.makedirs(dest_dir, exist_ok=True)
    shutil.copy2(FORECAST, dest_file)

    # Manifest records when this archive was made
    manifest = {
        "archived_at_utc": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "run_date":        today,
        "source":          os.path.basename(FORECAST),
    }
    with open(os.path.join(dest_dir, "MANIFEST.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"[ARCHIVE] {today} -> {dest_file}")
    _rotate(KEEP_LAST)
    return dest_file


def _list_archived_dates() -> list[str]:
    if not os.path.isdir(ARCHIVE_DIR):
        return []
    out = []
    for name in os.listdir(ARCHIVE_DIR):
        if not os.path.isdir(os.path.join(ARCHIVE_DIR, name)):
            continue
        try:
            datetime.datetime.strptime(name, "%Y-%m-%d")
        except ValueError:
            continue
        out.append(name)
    return sorted(out)


def _rotate(keep: int) -> None:
    dates = _list_archived_dates()
    if len(dates) <= keep:
        return
    for name in dates[: len(dates) - keep]:
        try:
            shutil.rmtree(os.path.join(ARCHIVE_DIR, name))
            print(f"[ARCHIVE] rotated out: {name}")
        except OSError as e:
            print(f"[ARCHIVE] rotate error {name}: {e}")


def load_archive(date_str: str) -> dict | None:
    """Return the archived forecast made on the given UTC date, or None."""
    path = os.path.join(ARCHIVE_DIR, date_str, "forecast.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def list_archive_dates() -> list[str]:
    """Public wrapper around the private lister."""
    return _list_archived_dates()


if __name__ == "__main__":
    p = archive_current_forecast()
    print(f"\nArchived dates ({len(list_archive_dates())}):")
    for d in list_archive_dates():
        print(f"  - {d}")
