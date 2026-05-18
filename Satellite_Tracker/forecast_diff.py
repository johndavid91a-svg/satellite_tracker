"""
Forecast change-detection.

After each daily run, compare today's `forecast_15day.json` against the most
recent snapshot in `backups/` and emit `forecast_changes.json` describing
what differs. Consumers (Tk panel, Word doc) read this artefact to surface
"what's new since yesterday".

Change types detected per overlapping forecast day:
  - new_passes      : sat passes that exist today but did not yesterday
  - removed_passes  : sat passes that existed yesterday but not today
  - shifted_passes  : sat passes whose entry time moved by >= SHIFT_MIN
                      minutes (TLE refresh refined the orbit)
  - blind_delta_min : how much total blind time changed (today - yesterday)

A pass is identified by (date, norad_id, hour-of-entry-bucket). Matching uses
a +/- 30-minute fuzzy window so a tiny shift counts as "shifted", not as
"removed AND new".
"""

from __future__ import annotations
import datetime
import json
import os
from typing import Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FORECAST_JSON = os.path.join(BASE_DIR, "forecast_15day.json")
BACKUPS_DIR   = os.path.join(BASE_DIR, "backups")
CHANGES_JSON  = os.path.join(BASE_DIR, "forecast_changes.json")
# Rolling history of every day's diff so the operator can scroll back
# through "what changed each day" rather than only seeing today's delta.
CHANGES_HISTORY_JSON = os.path.join(BASE_DIR, "forecast_changes_history.json")
HISTORY_RETAIN_DAYS  = 15   # keep the last 15 daily diffs

SHIFT_MIN_THRESHOLD = 5      # minutes — passes that shifted by this much get flagged
MATCH_WINDOW_MIN    = 30     # minutes — match passes across days within +/- this


# ─────────────────────────────────────────────────────────────────────────────
# Loaders
# ─────────────────────────────────────────────────────────────────────────────
def _load_json(path: str) -> Optional[dict]:
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _previous_backup_forecast() -> tuple[Optional[dict], Optional[str]]:
    """
    Locate the baseline forecast to diff today's run against — i.e. "what
    the schedule looked like on the most recent PRIOR day".

    Baseline source priority:
      1. predictions_archive/<most-recent-prior-day>/forecast.json
         — IMMUTABLE: the first archive of each day wins and is never
           overwritten, so this is a stable yesterday-baseline even if the
           forecast is regenerated several times in one day.
      2. backups/<most-recent-prior-day>/forecast_15day.json
         — fallback when no prior archive exists.

    The old behaviour preferred backups/<today>/, but backup_manager's
    snapshot is idempotent-per-day: a second same-day run overwrites it
    with the just-regenerated forecast, collapsing the diff to "0 changes
    vs itself". Anchoring on the immutable prior-day archive fixes that.

    Returns (forecast_dict, source_date) or (None, None).
    """
    today = datetime.datetime.utcnow().strftime("%Y-%m-%d")

    # ── Priority 1: most recent PRIOR-day predictions_archive ────────────
    archive_dir = os.path.join(BASE_DIR, "predictions_archive")
    if os.path.isdir(archive_dir):
        arc_dates = []
        for name in os.listdir(archive_dir):
            if not os.path.isdir(os.path.join(archive_dir, name)):
                continue
            try:
                datetime.datetime.strptime(name, "%Y-%m-%d")
            except ValueError:
                continue
            if name < today:                       # strictly prior day
                arc_dates.append(name)
        arc_dates.sort(reverse=True)
        for cand in arc_dates:
            path = os.path.join(archive_dir, cand, "forecast.json")
            loaded = _load_json(path)
            if loaded:
                return loaded, cand

    # ── Priority 2: backups/ — prior day first, then today's snapshot ───
    if not os.path.isdir(BACKUPS_DIR):
        return None, None
    candidates = []
    for name in os.listdir(BACKUPS_DIR):
        if not os.path.isdir(os.path.join(BACKUPS_DIR, name)):
            continue
        try:
            datetime.datetime.strptime(name, "%Y-%m-%d")
        except ValueError:
            continue
        candidates.append(name)
    # Prior days, newest first; today's snapshot only as a last resort.
    prior = sorted([c for c in candidates if c < today], reverse=True)
    same  = [c for c in candidates if c == today]
    for cand in prior + same:
        path = os.path.join(BACKUPS_DIR, cand, "forecast_15day.json")
        loaded = _load_json(path)
        if loaded:
            return loaded, cand
    return None, None


# ─────────────────────────────────────────────────────────────────────────────
# Diff core
# ─────────────────────────────────────────────────────────────────────────────
def _entry_minute(c: dict) -> int:
    """UTC minute of entry within the day (0..1439)."""
    hms = c["entry_utc"][11:19]
    h, m, s = hms.split(":")
    return int(h) * 60 + int(m)


def _is_future(entry_utc: str, now_utc: datetime.datetime) -> bool:
    """True if `entry_utc` (ISO Z) is strictly after `now_utc`.

    A change about a pass that has already happened is noise — the user
    can't act on it. We keep only future-or-currently-imminent events.
    """
    try:
        # entry_utc shape: "2026-05-13T01:28:00Z"
        dt = datetime.datetime.strptime(entry_utc, "%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, TypeError):
        return True   # malformed input — keep, don't silently drop
    return dt > now_utc


def _diff_day(today_day: dict, yest_day: dict,
              now_utc: datetime.datetime | None = None) -> dict:
    """Produce change summary for one date.

    When `now_utc` is supplied, passes whose start time is already in the
    past (relative to `now_utc`) are dropped so the change feed only shows
    actionable, future events. Days entirely in the future are unaffected.
    """
    today_by_sat: dict[str, list[dict]] = {}
    for c in today_day.get("crossings", []):
        today_by_sat.setdefault(c["norad_id"], []).append(c)
    yest_by_sat: dict[str, list[dict]] = {}
    for c in yest_day.get("crossings", []):
        yest_by_sat.setdefault(c["norad_id"], []).append(c)

    new_passes:     list[dict] = []
    removed_passes: list[dict] = []
    shifted_passes: list[dict] = []

    all_nids = set(today_by_sat) | set(yest_by_sat)
    for nid in all_nids:
        t_list = sorted(today_by_sat.get(nid, []), key=_entry_minute)
        y_list = sorted(yest_by_sat.get(nid, []), key=_entry_minute)
        used = [False] * len(y_list)
        # Greedy match: each today-pass to nearest unmatched yest-pass within window
        for tc in t_list:
            tm = _entry_minute(tc)
            best_i, best_delta = -1, None
            for i, yc in enumerate(y_list):
                if used[i]:
                    continue
                delta = abs(_entry_minute(yc) - tm)
                if delta <= MATCH_WINDOW_MIN and (best_delta is None or delta < best_delta):
                    best_i, best_delta = i, delta
            if best_i >= 0:
                used[best_i] = True
                if best_delta >= SHIFT_MIN_THRESHOLD:
                    yc = y_list[best_i]
                    shifted_passes.append({
                        "name":      tc["name"],
                        "country":   tc["country"],
                        "is_indian": tc["is_indian"],
                        "pass_type": tc["pass_type"],
                        "today_entry":     tc["entry_utc"],
                        "yesterday_entry": yc["entry_utc"],
                        "shift_min":       int(best_delta) if _entry_minute(yc) <= tm
                                            else -int(best_delta),
                    })
            else:
                new_passes.append({
                    "name":      tc["name"],
                    "country":   tc["country"],
                    "is_indian": tc["is_indian"],
                    "pass_type": tc["pass_type"],
                    "entry_utc": tc["entry_utc"],
                    # FEAT-004: carry forward the strategic-site target list
                    # so the Tk popup can surface "TARGETS:" lines for new
                    # passes that put a tier-1 facility inside the sat's reach.
                    "targeted_sites": tc.get("targeted_sites", []),
                })
        for i, yc in enumerate(y_list):
            if not used[i]:
                removed_passes.append({
                    "name":      yc["name"],
                    "country":   yc["country"],
                    "is_indian": yc["is_indian"],
                    "pass_type": yc["pass_type"],
                    "entry_utc": yc["entry_utc"],
                })

    # ── Drop changes about passes that already happened ────────────────
    # The user can't act on a 06:28 PKT pass at 11:30 PKT. Each list filters
    # against its own "relevant" timestamp:
    #   - new:      filter on entry_utc (today's predicted time)
    #   - removed:  filter on entry_utc (yesterday's "would have happened" time)
    #   - shifted:  filter on today_entry (the *new* predicted time)
    if now_utc is not None:
        new_passes     = [p for p in new_passes
                          if _is_future(p["entry_utc"],       now_utc)]
        removed_passes = [p for p in removed_passes
                          if _is_future(p["entry_utc"],       now_utc)]
        shifted_passes = [p for p in shifted_passes
                          if _is_future(p["today_entry"],     now_utc)]

    blind_today = today_day["totals"].get("blind_minutes", 0)
    blind_yest  = yest_day["totals"].get("blind_minutes", 0)
    return {
        "date":            today_day["date"],
        "new_passes":      new_passes,
        "removed_passes":  removed_passes,
        "shifted_passes":  shifted_passes,
        "blind_delta_min": round(blind_today - blind_yest, 1),
        "counts": {
            "new":     len(new_passes),
            "removed": len(removed_passes),
            "shifted": len(shifted_passes),
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Public entry
# ─────────────────────────────────────────────────────────────────────────────
def run() -> Optional[dict]:
    """
    Produce `forecast_changes.json` by comparing today's forecast against
    the most recent prior backup. No-op if no prior backup exists.
    """
    today = _load_json(FORECAST_JSON)
    if today is None:
        print("[DIFF] no current forecast — nothing to compare")
        return None

    yest, yest_date = _previous_backup_forecast()
    if yest is None:
        print("[DIFF] no previous backup found — first run, skipping diff")
        # Still write an empty changes file so consumers don't 404
        empty = {
            "generated_at": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "compared_to": None,
            "days": [],
            "totals": {"new": 0, "removed": 0, "shifted": 0,
                       "blind_delta_min": 0},
        }
        _atomic_write_json(CHANGES_JSON, empty)
        return empty

    today_days = {d["date"]: d for d in today.get("days", [])}
    yest_days  = {d["date"]: d for d in yest.get("days", [])}

    # Only diff dates that appear in BOTH (the overlapping forecast horizon).
    overlap = sorted(set(today_days) & set(yest_days))

    now_utc = datetime.datetime.utcnow()
    per_day = [_diff_day(today_days[d], yest_days[d], now_utc=now_utc)
               for d in overlap]
    totals = {
        "new":     sum(d["counts"]["new"]     for d in per_day),
        "removed": sum(d["counts"]["removed"] for d in per_day),
        "shifted": sum(d["counts"]["shifted"] for d in per_day),
        "blind_delta_min": round(sum(d["blind_delta_min"] for d in per_day), 1),
    }

    out = {
        "generated_at": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "compared_to":  yest_date,
        # cutoff_utc lets every consumer (popup, Word doc) prove the filter
        # was applied — every entry in the lists has entry_utc > cutoff_utc.
        "cutoff_utc":   now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "days":   per_day,
        "totals": totals,
    }
    _atomic_write_json(CHANGES_JSON, out)
    print(f"[DIFF] vs backup {yest_date}: "
          f"+{totals['new']} new, -{totals['removed']} removed, "
          f"~{totals['shifted']} shifted, "
          f"blind delta {totals['blind_delta_min']:+.0f} min")
    # Pull out the loudest changes for the log
    indian_new = [p for d in per_day for p in d["new_passes"] if p["is_indian"]]
    if indian_new:
        print(f"[DIFF] [!] {len(indian_new)} NEW Indian crossing(s) compared to "
              f"{yest_date}:")
        for p in indian_new[:5]:
            print(f"[DIFF]     {p['entry_utc']}  {p['name']}  ({p['pass_type']})")

    # Append today's diff to the rolling 15-day change history so the
    # SCHEDULE CHANGES window can show day-by-day modifications, not just
    # the latest delta. Tag the methodology versions of both sides so a
    # v1->v2 classifier-upgrade day is flagged, not mistaken for real
    # schedule movement.
    v_today = _methodology_of(today)
    v_yest  = _methodology_of(yest)
    _append_to_history(out, now_utc,
                       methodology_curr=v_today, methodology_prev=v_yest)
    return out


def _append_to_history(diff: dict, now_utc: datetime.datetime,
                       methodology_curr: str = "v2",
                       methodology_prev: str = "v2") -> None:
    """Append `diff` to forecast_changes_history.json, keyed by run date.

    - Re-running on the same UTC day OVERWRITES that day's entry (the last
      run of the day wins — consistent with how the dashboard reads state).
    - Keeps only the most recent HISTORY_RETAIN_DAYS entries.
    - Never raises: a history write failure must not break the daily run.
    """
    run_date = now_utc.strftime("%Y-%m-%d")
    entry = {
        "run_date":     run_date,
        "generated_at": diff.get("generated_at"),
        "compared_to":  diff.get("compared_to"),
        "cutoff_utc":   diff.get("cutoff_utc"),
        "totals":       diff.get("totals", {}),
        "days":         diff.get("days", []),
        # Methodology tags — a v1->v2 classifier-upgrade day produces a
        # huge artefact delta that is NOT real schedule movement. The
        # SCHEDULE CHANGES window reads `methodology_mismatch` to badge
        # the day and suppress the artefact cards.
        "methodology_prev":     methodology_prev,
        "methodology_curr":     methodology_curr,
        "methodology_mismatch": methodology_prev != methodology_curr,
    }
    try:
        history: list[dict] = []
        existing = _load_json(CHANGES_HISTORY_JSON)
        if existing and isinstance(existing.get("history"), list):
            history = existing["history"]
        # Drop any prior entry for the same run_date, then append today's.
        history = [h for h in history if h.get("run_date") != run_date]
        history.append(entry)
        # Sort by run_date ascending, keep the last HISTORY_RETAIN_DAYS.
        history.sort(key=lambda h: h.get("run_date", ""))
        history = history[-HISTORY_RETAIN_DAYS:]
        payload = {
            "updated_at":   now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "retain_days":  HISTORY_RETAIN_DAYS,
            "count":        len(history),
            "history":      history,
        }
        _atomic_write_json(CHANGES_HISTORY_JSON, payload)
        print(f"[DIFF] change history updated: {len(history)} day(s) retained "
              f"(window {history[0]['run_date']} .. {history[-1]['run_date']})")
    except Exception as e:
        print(f"[DIFF] could not update change history ({type(e).__name__}: {e}) "
              f"— continuing")


def _atomic_write_json(path: str, payload: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)


# ─────────────────────────────────────────────────────────────────────────────
# History backfill — reconstruct the day-by-day record from the archives
# ─────────────────────────────────────────────────────────────────────────────
def _methodology_of(forecast: dict) -> str:
    """Return 'v2' if this forecast was produced with per-sat standoff
    (FEAT-003+), else 'v1' (the old single 300 km global buffer)."""
    if forecast.get("methodology_version"):
        return forecast["methodology_version"]
    for d in forecast.get("days", []):
        for c in d.get("crossings", []):
            return "v2" if "standoff_km" in c else "v1"
    return "v1"


def backfill_history_from_archives() -> dict:
    """Rebuild forecast_changes_history.json from predictions_archive/.

    The Schedule Changes window shows a rolling 15-day record, but the
    history file only starts accumulating from the day this feature
    shipped. This function reconstructs the record from every immutable
    archived prediction we already have on disk: for each consecutive pair
    (archive[d-1], archive[d]) it computes the same diff a live run would,
    so the operator immediately sees every day of real modifications the
    project has captured — without waiting 15 days for it to accumulate.

    v1->v2 methodology transitions are tagged so the day the per-sat
    standoff classifier shipped isn't mistaken for a real mass schedule
    change.
    """
    archive_dir = os.path.join(BASE_DIR, "predictions_archive")
    if not os.path.isdir(archive_dir):
        print("[BACKFILL] no predictions_archive — nothing to reconstruct")
        return {}

    dates = []
    for name in sorted(os.listdir(archive_dir)):
        if not os.path.isdir(os.path.join(archive_dir, name)):
            continue
        try:
            datetime.datetime.strptime(name, "%Y-%m-%d")
        except ValueError:
            continue
        dates.append(name)

    if len(dates) < 2:
        print(f"[BACKFILL] only {len(dates)} archive(s) — need >=2 to diff")
        # Still write whatever single entry we can (zero-change placeholder)
        return {}

    history: list[dict] = []
    for i in range(1, len(dates)):
        prev_date, curr_date = dates[i - 1], dates[i]
        prev = _load_json(os.path.join(archive_dir, prev_date, "forecast.json"))
        curr = _load_json(os.path.join(archive_dir, curr_date, "forecast.json"))
        if prev is None or curr is None:
            continue

        prev_days = {d["date"]: d for d in prev.get("days", [])}
        curr_days = {d["date"]: d for d in curr.get("days", [])}
        overlap = sorted(set(prev_days) & set(curr_days))
        # Use the curr archive's generated_at as the "now" reference so the
        # past-pass filter behaves as it did on that day.
        try:
            now_ref = datetime.datetime.strptime(
                curr.get("generated_at", curr_date + "T00:00:00Z"),
                "%Y-%m-%dT%H:%M:%SZ")
        except (ValueError, TypeError):
            now_ref = datetime.datetime.strptime(curr_date, "%Y-%m-%d")

        per_day = [_diff_day(curr_days[d], prev_days[d], now_utc=now_ref)
                   for d in overlap]
        totals = {
            "new":     sum(d["counts"]["new"]     for d in per_day),
            "removed": sum(d["counts"]["removed"] for d in per_day),
            "shifted": sum(d["counts"]["shifted"] for d in per_day),
            "blind_delta_min": round(sum(d["blind_delta_min"] for d in per_day), 1),
        }
        v_prev = _methodology_of(prev)
        v_curr = _methodology_of(curr)
        history.append({
            "run_date":       curr_date,
            "generated_at":   curr.get("generated_at"),
            "compared_to":    prev_date,
            "cutoff_utc":     curr.get("generated_at"),
            "totals":         totals,
            "days":           per_day,
            # Methodology tags — when they differ, the day's "changes" are
            # mostly the classifier upgrade, not real schedule movement.
            "methodology_prev": v_prev,
            "methodology_curr": v_curr,
            "methodology_mismatch": v_prev != v_curr,
        })

    history.sort(key=lambda h: h.get("run_date", ""))
    history = history[-HISTORY_RETAIN_DAYS:]
    payload = {
        "updated_at":  datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "retain_days": HISTORY_RETAIN_DAYS,
        "count":       len(history),
        "backfilled":  True,
        "history":     history,
    }
    _atomic_write_json(CHANGES_HISTORY_JSON, payload)
    print(f"[BACKFILL] reconstructed {len(history)} day(s) of change history "
          f"from {len(dates)} archives")
    for h in history:
        t = h["totals"]
        mm = "  [METHODOLOGY v1->v2]" if h["methodology_mismatch"] else ""
        print(f"[BACKFILL]   {h['run_date']} vs {h['compared_to']}: "
              f"+{t['new']} -{t['removed']} ~{t['shifted']}{mm}")
    return payload


if __name__ == "__main__":
    import sys
    if "--backfill" in sys.argv:
        backfill_history_from_archives()
    else:
        run()
