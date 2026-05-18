"""
Daily entry point for ATLAS HiRes EO Pakistan surveillance.

Pipeline (in order):
  1. backup_manager.snapshot()         — preserve yesterday's state
  2. celestrak_tle.fetch_hires_eo_tles() — refresh TLE cache (24h TTL)
  3. forecast_15day.build_forecast()   — regenerate 15-day predictions
  4. forecast_diff.run()               — diff vs yesterday's snapshot
  5. predictions_archive.archive…     — append to historical record
  6. accuracy_tracker.build_record()   — recompute prediction accuracy
  7. forecast_15day.render_word()      — produce printable Word doc
  8. Indian_Targeting_Summary.write…   — plain-text targeting digest
  9. _refresh_latest_pointer()         — copy today's doc to *_LATEST.docx
 10. _apply_retention()                — purge docs older than RETAIN_DAYS

Schedule via Windows Task Scheduler (see "Install Daily Schedule.bat"):
    python C:\\...\\Satellite_Tracker\\run_daily.py
"""

from __future__ import annotations
import os
import sys
import shutil
import datetime
import traceback

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import backup_manager
import forecast_15day
import forecast_diff
import predictions_archive
import accuracy_tracker
import Indian_Targeting_Summary as targeting_summary

# Retain dated Word docs for this many days. Older ones are deleted by the
# retention pass at the end of run_daily. The *_LATEST.docx pointer is
# always kept (it's overwritten in place each day).
RETAIN_DAYS = 30
DOCS_DIR = os.path.join(_HERE, "documents")
LATEST_NAME = "Pakistan_15Day_Forecast_LATEST.docx"


def _refresh_latest_pointer() -> str | None:
    """Copy today's dated Pakistan_15Day_Forecast_<date>.docx to the
    canonical _LATEST.docx so operators / sidecars always have a stable
    filename to open. Returns the path of the latest doc, or None.
    """
    if not os.path.isdir(DOCS_DIR):
        return None
    dated = [f for f in os.listdir(DOCS_DIR)
             if f.startswith("Pakistan_15Day_Forecast_2")    # date-prefixed
             and f.endswith(".docx")]
    if not dated:
        return None
    dated.sort(key=lambda f: os.path.getmtime(os.path.join(DOCS_DIR, f)),
               reverse=True)
    newest = os.path.join(DOCS_DIR, dated[0])
    latest = os.path.join(DOCS_DIR, LATEST_NAME)
    try:
        shutil.copy2(newest, latest)
        print(f"[LATEST] {os.path.basename(newest)} -> {LATEST_NAME}")
    except OSError as e:
        # Word may hold a lock on the LATEST file if the operator is reading
        # it — that's fine, we just leave the previous copy in place.
        print(f"[LATEST] could not refresh pointer ({e}) — keeping previous copy")
    return latest


def _apply_retention() -> int:
    """Delete dated forecast .docx files older than RETAIN_DAYS.
    The *_LATEST.docx pointer is always preserved. Returns the count of
    files deleted. Read-only logs everything so the operator can audit.
    """
    if not os.path.isdir(DOCS_DIR):
        return 0
    cutoff = datetime.datetime.now() - datetime.timedelta(days=RETAIN_DAYS)
    deleted = 0
    for f in os.listdir(DOCS_DIR):
        if not (f.startswith("Pakistan_15Day_Forecast_") and f.endswith(".docx")):
            continue
        if f == LATEST_NAME:
            continue
        p = os.path.join(DOCS_DIR, f)
        try:
            mtime = datetime.datetime.fromtimestamp(os.path.getmtime(p))
        except OSError:
            continue
        if mtime < cutoff:
            try:
                os.remove(p)
                print(f"[RETAIN] purged {f} (mtime {mtime.date()}, age "
                      f"{(datetime.datetime.now() - mtime).days}d)")
                deleted += 1
            except OSError as e:
                print(f"[RETAIN] could not delete {f}: {e}")
    print(f"[RETAIN] kept docs from last {RETAIN_DAYS} days; purged {deleted}")
    return deleted


def main() -> int:
    print("=" * 64)
    print("  ATLAS — Daily HiRes EO Pakistan Surveillance Run")
    print("=" * 64)
    try:
        # 1. Snapshot current state — this captures YESTERDAY's forecast as
        #    a sibling of today's date dir, and is what forecast_diff reads.
        backup_manager.snapshot()

        # 2. Regenerate forecast JSON. We FORCE a fresh CelesTrak TLE pull
        #    on every run — never trust the 24h cache for an actual scan.
        #    Pass --no-refresh to opt out (useful when iterating offline).
        force_fresh = "--no-refresh" not in sys.argv
        print(f"[RUN] Fresh CelesTrak pull: "
              f"{'YES (forcing TLE refresh)' if force_fresh else 'NO (--no-refresh)'}")
        forecast = forecast_15day.run(
            force_refresh_tles=force_fresh,
            render_doc=False,
        )

        # 3. Diff today's fresh forecast against the most recent prior backup
        #    so the dashboard / Word doc can surface "what changed".
        forecast_diff.run()

        # 4. Archive today's prediction immutably — this builds the historical
        #    record that powers the accuracy tracker.
        predictions_archive.archive_current_forecast()

        # 5. Re-compute prediction accuracy across every archived prediction
        #    that now has a comparable "ground-truth" archive (an archive
        #    made on the target date itself, where the target is at offset 0).
        accuracy_tracker.build_accuracy_record()

        # 6. Render the Word doc — includes today's accuracy table and
        #    the diff-against-yesterday section. The output filename is
        #    Pakistan_15Day_Forecast_<start_date>.docx so each day's run
        #    produces a fresh artefact distinct from yesterday's.
        forecast_15day.render_word(forecast)

        # 7. Build the plain-text Indian targeting digest. Operator can
        #    open this in Notepad without needing Word. Always overwrites
        #    documents/Indian_Targeting_Summary.txt with the current run.
        try:
            targeting_summary.write_summary()
            print(f"[TARGETS] Indian_Targeting_Summary.txt refreshed")
        except Exception as e:
            print(f"[TARGETS] summary build failed: {e}")

        # 8. Maintain a stable Pakistan_15Day_Forecast_LATEST.docx pointer
        #    so external consumers (other launchers, the operator) always
        #    have one canonical filename to open without guessing the date.
        _refresh_latest_pointer()

        # 9. Retention: prune dated Word docs older than RETAIN_DAYS so
        #    the documents/ folder doesn't grow unbounded. The *_LATEST
        #    pointer is preserved.
        _apply_retention()

        days = forecast.get("days", [])
        total = sum(d["totals"]["crossings"] for d in days)
        ind   = sum(d["totals"]["indian_crossings"] for d in days)
        print(f"[DONE] forecast spans {len(days)} days, "
              f"{total} crossings, {ind} Indian crossings.")
        return 0
    except Exception as e:
        print(f"[FATAL] {e}")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
