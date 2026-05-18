"""
Prediction-accuracy tracker.

For every target date T where we have BOTH (a) an archived prediction made
some days earlier (in `predictions_archive/<P>/forecast.json`, with T at
offset T-P in that archive's `days[]`) AND (b) the freshest archive for T
itself (where T sits at offset 0, propagated from a TLE epoch within hours
of T) — we can compare what we PREDICTED-FOR-T against what we BELIEVE-NOW
about T.

The freshest-day-0 forecast is the best available "ground truth": SGP4
prediction error grows roughly linearly with lookback, so an archive made
on T itself is the most trustworthy single estimate of what happened.

Each comparison produces:
  - matched_passes   : crossings that appear in both lists, matched by
                       (norad_id, entry-time window ±30 min)
  - missed_passes    : in actual, not in prediction          (we missed it)
  - phantom_passes   : in prediction, not in actual           (we cried wolf)
  - mean_shift_min   : average |actual_entry - predicted_entry| across matches
  - accuracy_pct     : matched / (matched + missed + phantom)

Output is a list of {target_date, lookback_days, ...} records, plus a
summary of accuracy bucketed by lookback distance.
"""

from __future__ import annotations
import datetime
import json
import os
from typing import Optional

import predictions_archive as pa


BASE_DIR        = os.path.dirname(os.path.abspath(__file__))
ACCURACY_JSON   = os.path.join(BASE_DIR, "accuracy_track_record.json")

MATCH_WINDOW_MIN = 30   # minutes — match passes within ±this window


def _archive_version(forecast: dict) -> str:
    """Return the methodology_version of an archived forecast.

    Forecasts produced by FEAT-003+ carry an explicit `methodology_version`
    field ('v2'). Older archives (pre-FEAT-003) don't have the field —
    those used the single 300 km global tilt buffer with no per-sat
    standoff. We infer 'v1' for them by checking the per-crossing fields.
    """
    explicit = forecast.get("methodology_version")
    if explicit:
        return explicit
    # Infer: v2 crossings always carry standoff_km/max_tilt_deg
    days = forecast.get("days", [])
    for d in days:
        for c in d.get("crossings", []):
            if "standoff_km" in c:
                return "v2"
            return "v1"
    return "v1"


# ─────────────────────────────────────────────────────────────────────────────
# Pass matching helpers
# ─────────────────────────────────────────────────────────────────────────────
def _entry_min(c: dict) -> int:
    hh, mm, ss = c["entry_utc"][11:19].split(":")
    return int(hh) * 60 + int(mm)


def _match_passes(actual: list[dict], predicted: list[dict]) -> dict:
    """
    Greedy match by (norad_id, |entry_time delta| <= MATCH_WINDOW_MIN).
    Returns counters + the shifts.
    """
    by_sat_actual: dict[str, list[dict]] = {}
    for c in actual:
        by_sat_actual.setdefault(c["norad_id"], []).append(c)
    by_sat_predicted: dict[str, list[dict]] = {}
    for c in predicted:
        by_sat_predicted.setdefault(c["norad_id"], []).append(c)

    matched = 0
    missed  = 0
    phantom = 0
    shifts_min: list[int] = []

    all_nids = set(by_sat_actual) | set(by_sat_predicted)
    for nid in all_nids:
        a_list = sorted(by_sat_actual.get(nid, []),    key=_entry_min)
        p_list = sorted(by_sat_predicted.get(nid, []), key=_entry_min)
        used_p = [False] * len(p_list)
        for ac in a_list:
            am = _entry_min(ac)
            best_i, best_delta = -1, None
            for i, pc in enumerate(p_list):
                if used_p[i]:
                    continue
                d = abs(_entry_min(pc) - am)
                if d <= MATCH_WINDOW_MIN and (best_delta is None or d < best_delta):
                    best_i, best_delta = i, d
            if best_i >= 0:
                used_p[best_i] = True
                matched += 1
                shifts_min.append(int(best_delta))
            else:
                missed += 1
        phantom += sum(1 for u in used_p if not u)

    total = matched + missed + phantom
    return {
        "matched":        matched,
        "missed":         missed,    # in actual but predicted didn't catch
        "phantom":        phantom,   # predicted but actual didn't catch
        "total":          total,
        "accuracy_pct":   round(100.0 * matched / total, 1) if total else None,
        "mean_shift_min": round(sum(shifts_min) / len(shifts_min), 1) if shifts_min else None,
        "max_shift_min":  max(shifts_min) if shifts_min else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Build accuracy record
# ─────────────────────────────────────────────────────────────────────────────
def build_accuracy_record() -> dict:
    """
    Walk every archived prediction. For each (prediction_date P, offset N)
    where an archive also exists for P+N, compute the accuracy metrics.

    Returns a dict written to disk.
    """
    archive_dates = pa.list_archive_dates()
    archives: dict[str, dict] = {}
    for d in archive_dates:
        f = pa.load_archive(d)
        if f is not None:
            archives[d] = f

    records: list[dict] = []
    for p_date, p_forecast in archives.items():
        p_dt = datetime.datetime.strptime(p_date, "%Y-%m-%d").date()
        p_version = _archive_version(p_forecast)
        for offset, day_block in enumerate(p_forecast.get("days", [])):
            target = p_dt + datetime.timedelta(days=offset)
            target_str = target.strftime("%Y-%m-%d")
            if target_str not in archives:
                continue   # we don't have ground truth yet
            actual_archive = archives[target_str]
            actual_days = actual_archive.get("days", [])
            if not actual_days:
                continue
            actual_day0 = actual_days[0]
            if actual_day0.get("date") != target_str:
                continue   # archive shape unexpected
            actual_version = _archive_version(actual_archive)

            predicted_xings = day_block.get("crossings", [])
            actual_xings    = actual_day0.get("crossings", [])
            match = _match_passes(actual_xings, predicted_xings)
            mismatch = (p_version != actual_version)
            records.append({
                "target_date":     target_str,
                "predicted_on":    p_date,
                "lookback_days":   offset,
                "predicted_count": len(predicted_xings),
                "actual_count":    len(actual_xings),
                # Methodology versions on each side — if they differ the
                # comparison is NOT a SGP4-drift accuracy measurement,
                # it's a code-change artefact. UI badges this as MIXED.
                "predicted_methodology": p_version,
                "actual_methodology":    actual_version,
                "methodology_mismatch":  mismatch,
                **match,
            })

    # Bucket accuracy by lookback distance. Methodology-mismatched pairs
    # (e.g. v1 archive vs v2 ground-truth) are EXCLUDED from the averages
    # because their pass-count delta is a code-change artefact, not an
    # SGP4 prediction-accuracy signal. Mismatch records are still kept in
    # the per-comparison list so the operator can see and audit them.
    buckets: dict[int, list[dict]] = {}
    excluded_mismatches = 0
    for r in records:
        if r["accuracy_pct"] is None:
            continue
        if r.get("methodology_mismatch"):
            excluded_mismatches += 1
            continue
        buckets.setdefault(r["lookback_days"], []).append(r)
    by_lookback = []
    for lb in sorted(buckets):
        rs = buckets[lb]
        accs   = [r["accuracy_pct"] for r in rs]
        shifts = [r["mean_shift_min"] for r in rs if r["mean_shift_min"] is not None]
        by_lookback.append({
            "lookback_days": lb,
            "sample_size":   len(rs),
            "mean_accuracy_pct": round(sum(accs) / len(accs), 1),
            "mean_shift_min":    round(sum(shifts) / len(shifts), 1) if shifts else None,
        })

    out = {
        "generated_at": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "archive_dates_available": archive_dates,
        "records":      records,
        "by_lookback":  by_lookback,
        "excluded_mismatches": excluded_mismatches,
    }
    _atomic_write_json(ACCURACY_JSON, out)
    if by_lookback:
        print("[ACCURACY] lookback   samples   mean_acc%   mean_shift_min")
        for b in by_lookback:
            ms = f"{b['mean_shift_min']:>5.1f}" if b['mean_shift_min'] is not None else "  -  "
            print(f"[ACCURACY]   {b['lookback_days']:>2}d        {b['sample_size']:>3}        "
                  f"{b['mean_accuracy_pct']:>5.1f}        {ms}")
    else:
        print("[ACCURACY] no comparable archive pairs yet — "
              "need at least 2 daily runs covering overlapping target dates")
    if excluded_mismatches:
        print(f"[ACCURACY] {excluded_mismatches} comparison(s) excluded from "
              f"averages — methodology mismatch (e.g. pre-FEAT-003 v1 archive "
              f"compared against v2 ground-truth). Per-record table still shows them.")
    return out


def _atomic_write_json(path: str, payload: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)


def load_accuracy_record() -> Optional[dict]:
    if not os.path.isfile(ACCURACY_JSON):
        return None
    try:
        with open(ACCURACY_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


if __name__ == "__main__":
    build_accuracy_record()
