# 15-Day HiRes EO Surveillance Forecast

Daily-refreshed prediction of every high-resolution Earth-observation
satellite (panchromatic GSD ≤ 1 m) passing over Pakistan, plus the
"blind windows" — the UTC intervals when Pakistan is **not** observed.

## What changed (FEAT-001)

The tracker previously scanned a mixed bag of 50+ satellites
(weather, comms, nav, ISS, low-res EO). That list is replaced with a
curated set of **65 sub-metre EO + comparable SAR** satellites. Anything
that cannot produce ≤ 1 m imagery is intentionally excluded.

Indian (ISRO) satellites are highlighted in red across all surfaces:
the Word report, the Tk dashboard panel, and the JSON API.

## Pipeline

```
                     hires_eo_satellites.py        (curated 65 NORAD IDs)
                              │
                              ▼
        backup_manager  ──►  celestrak_tle.py      (24h disk cache)
              │                       │
              ▼                       ▼
  backups/<YYYY-MM-DD>/      forecast_15day.py
                                      │
                ┌─────────────────────┼─────────────────────┐
                ▼                     ▼                     ▼
      forecast_15day.json     documents/             stdout
                              Pakistan_15Day_
                              Forecast_<date>.docx
                ▲
        ┌───────┴────────┐
        │                │
  Tk Forecast panel    /api/forecast (FastAPI)
```

## Files

| Path | Purpose |
|---|---|
| `Satellite_Tracker/hires_eo_satellites.py` | Curated list — single source of truth for the satellite set. |
| `Satellite_Tracker/celestrak_tle.py` | Daily fetch of TLEs from `celestrak.org/NORAD/elements/gp.php`. 24 h disk cache. |
| `Satellite_Tracker/forecast_15day.py` | The prediction engine + Word renderer. Generates `forecast_15day.json` and `documents/Pakistan_15Day_Forecast_<date>.docx`. |
| `Satellite_Tracker/backup_manager.py` | Rolling 30-day snapshots of state into `backups/<YYYY-MM-DD>/`. |
| `Satellite_Tracker/run_daily.py` | One-shot daily entrypoint — backup → TLE refresh → forecast. |
| `Satellite_Tracker/Run Daily Forecast.bat` | Windows wrapper for Task Scheduler. |
| `space_tracker_app.py` | Adds **15-Day Forecast** tab to the desktop dashboard. |
| `pakistan-orbit-tracker-main/backend/main.py` | Adds `/api/forecast` + `/api/forecast/{health,day,blind-windows}` endpoints. |

## Running it

### Manual (from the Tk dashboard)
1. Launch the app (`Launch Space Tracker.bat`).
2. Click **15-Day Forecast** in the sidebar.
3. Click **⟳ REFRESH FORECAST** — this runs `run_daily.py` and reloads the panel when finished.

### Manual (CLI)
```powershell
cd "C:\Users\Ayyan LapTop\Desktop\project-main\project-main\Satellite_Tracker"
python run_daily.py
```

### Automated daily (Windows Task Scheduler)

**One-click install:** run `Satellite_Tracker/Install Daily Schedule.cmd`
(right-click → Run as Administrator if it fails). It registers a task
named **"ATLAS HiRes EO Forecast"** that fires `Run Daily Forecast.bat`
daily at 06:00 local.

Manual install instead:
1. Open Task Scheduler → Create Basic Task
2. Trigger: Daily, 06:00 (after CelesTrak's overnight TLE updates)
3. Action: `"C:\Users\Ayyan LapTop\Desktop\project-main\project-main\Satellite_Tracker\Run Daily Forecast.bat"`
4. Run whether user is logged on or not

Output is logged to `Satellite_Tracker/run_daily.log`.

## Data source — clarified

The pipeline does **not** fetch pre-computed predictions from anywhere.
It fetches **orbital elements** (TLEs) from CelesTrak and computes the
predictions locally with the SGP4 propagator.

- **Source:** `https://celestrak.org/NORAD/elements/gp.php?CATNR=<id>&FORMAT=tle`
  — one HTTP call per satellite in the curated list. CelesTrak refreshes
  each TLE multiple times per day as the U.S. Space Force tracks the
  satellite.
- **Local compute:** `sgp4` Python library propagates each TLE forward
  in 60-second steps for 15 days. Every minute that lands inside the
  Pakistan box (or within the 300 km tilt buffer) and is sunlit becomes
  a crossing.
- **Cache:** TLE responses cached for 24 h on disk
  (`tle_cache_celestrak.json`); on cache hit no network call is made.

## Change detection — `forecast_diff.py`

After every daily run, `forecast_diff.py` compares the freshly-generated
forecast against the snapshot in `backups/<today>/forecast_15day.json`
(which holds yesterday's forecast — `backup_manager.snapshot()` runs at
the very start of each daily run, before regeneration).

Output: `Satellite_Tracker/forecast_changes.json` with, per overlapping
forecast day:

| field | meaning |
|---|---|
| `new_passes[]`     | crossings present today, absent yesterday |
| `removed_passes[]` | crossings present yesterday, absent today |
| `shifted_passes[]` | same crossing but entry time moved ≥ 5 min |
| `blind_delta_min`  | (today's blind minutes) − (yesterday's) |

The Tk dashboard surfaces this as a **🔔 CHANGES SINCE LAST RUN** banner
near the top of the 15-Day Forecast tab. The banner turns red whenever
**any Indian-satellite change** (new / removed / shifted) is detected.

FastAPI endpoint: `GET /api/forecast/changes`. 404s until the second
daily run has completed.

## JSON contract

The Tk panel and the FastAPI `/api/forecast` endpoint both consume the
single artefact `Satellite_Tracker/forecast_15day.json`. Schema is frozen
(do not change without a major-version bump):

```jsonc
{
  "generated_at": "2026-05-12T12:00:00Z",
  "start_date":   "2026-05-12",
  "end_date":     "2026-05-26",
  "pakistan_box": { "lat_min": 23.5, "lat_max": 37.5,
                    "lon_min": 60.5, "lon_max": 77.5 },
  "satellite_count":        43,        // sats with usable TLEs
  "indian_satellite_count": 10,
  "propagator":             "sgp4" | "handrolled",
  "duration_seconds":       29.4,
  "days": [
    {
      "date": "2026-05-12",
      "crossings": [
        {
          "norad_id":     "44804",
          "name":         "CARTOSAT-3",
          "country":      "India",
          "operator":     "ISRO",
          "sensor":       "Panchromatic",
          "resolution_m": 0.25,
          "entry_utc":    "2026-05-12T05:34:12Z",
          "exit_utc":     "2026-05-12T05:39:47Z",
          "duration_min": 5.6,
          "entry_lat":    34.1, "entry_lon": 74.8,
          "exit_lat":     24.2, "exit_lon":  68.1,
          "max_alt_km":   510.4,
          "direction":    "N->S",
          "is_indian":    true
        }
      ],
      "observation_windows": [
        { "start": "...", "end": "...", "duration_min": 5.6, "sats": ["44804"] }
      ],
      "blind_windows": [
        { "start": "...", "end": "...", "duration_min": 74.2 }
      ],
      "totals": {
        "crossings":         17,
        "unique_sats":       12,
        "indian_crossings":  4,
        "blind_minutes":     923.0,
        "longest_blind_min": 118.4
      }
    }
  ]
}
```

**Invariant:** for each day, `sum(observation_windows.duration_min) + sum(blind_windows.duration_min) == 1440`
(within rounding). This is asserted in the QA test.

## FastAPI endpoints

| Method | Path | Returns |
|---|---|---|
| GET | `/api/forecast` | full JSON above |
| GET | `/api/forecast/health` | `{ok, generated_at, stale: bool}` (stale = > 36h old) |
| GET | `/api/forecast/day/{YYYY-MM-DD}` | single day's slice |
| GET | `/api/forecast/blind-windows` | every blind window aggregated, sorted longest-first |

All return `404` cleanly when the forecast file hasn't been generated yet.

## Filtering rules

A pass is reported only if **all** of the following are true:

1. The satellite's NORAD ID resolves to its expected name on CelesTrak
   (`_name_matches` in `celestrak_tle.py`) — guards against ID typos.
2. The satellite's sub-point comes within **300 km** of Pakistan's
   border (the tilt zone) at some point during a 24-hour UTC window
   (sampled every 60 s).
3. **The sun is above the horizon** at the pass midpoint — Pakistan
   is sunlit. Universal filter (applies to SAR too).

## Pass classification

Each pass is tagged `pass_type`:

| pass_type | Meaning |
|---|---|
| `overhead` | Sub-point entered the Pakistan box at some point during the pass. Direct overflight. |
| `tilt-range` | Sub-point stayed within 300 km of the border but **never crossed it**. An optical EO sensor can slew ~30° off-nadir and still image Pakistan from this range. **Highlighted distinctly** because it's a less-obvious imaging threat. |

JSON each crossing carries:
- `pass_type`: `"overhead"` or `"tilt-range"`
- `min_dist_km`: closest approach from sub-point to box edge (0 for overhead)
- `sun_elev_deg`: solar elevation at pass midpoint
- `daytime`: bool — always true (filter)
- `is_indian`: bool — drives red highlighting

## India / Others separation

Both the JSON and the Word doc now keep Indian sats **separate** from
all other countries:

- JSON each day has `india_crossings[]` and `other_crossings[]` arrays
  (in addition to the combined `crossings[]` for back-compat), plus
  totals: `indian_overhead`, `indian_tilt_range`, `other_overhead`,
  `other_tilt_range`.
- Word doc each day has an **INDIA** section (red headings) followed
  by an **OTHER COUNTRIES** section.
- Tk panel daily table has six count columns: `IND Over`, `IND Tilt`,
  `Other Over`, `Other Tilt`, `Sats`, `Blind (min)`.

### Sensors / fleet scope
- **Included:** sub-metre **optical (panchromatic)** EO satellites only —
  Cartosat-2C/2D/2E/2F, Cartosat-3, WorldView-1/2/3, GeoEye-1, Pléiades 1A/1B,
  KOMPSAT-3/3A, Gaofen-2/7/11, Deimos-2.
- **Excluded:** SAR sats (RISAT-2B, RISAT-2BR1, EOS-04, KOMPSAT-5). They
  produce sub-metre radar imagery but have low-inclination orbits that
  revisit Pakistan many times per day, which inflates the count beyond
  the user's historical optical-only baseline. Re-enable in
  `hires_eo_satellites.py` (commented-out entries) if SAR coverage is
  needed.

## Notes on accuracy

TLE-based SGP4 prediction is accurate to ~1 km for the first few days and
degrades to tens of kilometres by day 14. For "is this satellite over
Pakistan today?" the answer remains reliable; for precise entry/exit
times near day 14 expect ±2-3 minutes drift.

**Regenerate daily.** That is the entire point of the daily cron / Task
Scheduler hook — every new TLE shaves error.

## Coverage exceptions

22 NORAD IDs in the curated list currently return HTTP 404 from
CelesTrak (commercial fleet rotations, decayed birds, re-indexed
catalogue numbers). The list is exhaustive and conservative — see
`docs/bug_registry.md → KNOWN-001` for the audit task. All 10 Indian
satellites resolve successfully.

## Backups

Before every scan, `backup_manager.snapshot()` copies
`satellite_history.json`, `anomalies.json`, `forecast_15day.json`,
`tle_cache_celestrak.json`, and the whole `documents/` directory into
`backups/<YYYY-MM-DD>/`. The most recent **30** snapshots are retained;
older ones are deleted. A `MANIFEST.json` is written into each snapshot
folder describing what was copied.
