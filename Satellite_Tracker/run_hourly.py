"""
Hourly TLE refresh for ATLAS HiRes EO Pakistan surveillance.

This is the LIGHTWEIGHT intra-day companion to run_daily.py. It keeps the
live picture current without the cost of the full daily pipeline.

Pipeline (in order):
  1. celestrak_tle.fetch_hires_eo_tles(force) — pull fresh TLEs
  2. forecast_15day.run()                     — regenerate the 15-day JSON
  3. forecast_diff.run()                      — diff vs the immutable
                                                prior-day archive, append
                                                the result to the rolling
                                                15-day change history

What it deliberately does NOT do (those stay on the once-a-day cadence in
run_daily.py):
  - backup_manager.snapshot()        (snapshot is first-of-day-wins)
  - predictions_archive.archive...   (archive is first-of-day-wins)
  - accuracy_tracker.build_record()  (daily granularity is enough)
  - forecast_15day.render_word()     (the Word doc is a daily artefact)
  - the *_LATEST.docx pointer / retention sweep

Net effect: forecast_15day.json, forecast_changes.json and
forecast_changes_history.json are refreshed every hour, so the dashboard
and the SCHEDULE CHANGES window always reflect TLEs no older than ~1 hour.

Schedule via Windows Task Scheduler (see "Install Daily Schedule.bat",
which now registers BOTH the daily and the hourly task), or let the Tk
dashboard's built-in hourly auto-refresh thread drive it while open.

    python C:\\...\\Satellite_Tracker\\run_hourly.py
"""

from __future__ import annotations
import os
import sys
import datetime
import traceback

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import forecast_15day
import forecast_diff


def main() -> int:
    stamp = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    print("=" * 64)
    print(f"  ATLAS — Hourly TLE Refresh   {stamp}")
    print("=" * 64)
    try:
        # 1+2. Force a fresh CelesTrak pull and regenerate the forecast JSON.
        #      render_doc=False — the Word doc stays a daily artefact.
        #      Pass --no-refresh to reuse the cached TLEs (offline iteration).
        force_fresh = "--no-refresh" not in sys.argv
        print(f"[HOURLY] Fresh CelesTrak pull: "
              f"{'YES' if force_fresh else 'NO (--no-refresh)'}")
        forecast = forecast_15day.run(
            force_refresh_tles=force_fresh,
            render_doc=False,
        )
        if forecast is None:
            print("[HOURLY] forecast regeneration returned nothing — aborting")
            return 1

        # 3. Diff vs the immutable prior-day archive and append to the
        #    rolling 15-day change history (forecast_diff.run() does both).
        forecast_diff.run()

        days = forecast.get("days", [])
        total = sum(d["totals"]["crossings"] for d in days)
        ind   = sum(d["totals"]["indian_crossings"] for d in days)
        print(f"[DONE] hourly refresh complete — forecast spans {len(days)} "
              f"days, {total} crossings ({ind} Indian). "
              f"forecast_changes_history.json updated.")
        return 0
    except Exception as e:
        print(f"[FATAL] {e}")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
