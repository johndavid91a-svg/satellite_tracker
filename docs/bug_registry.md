# Bug Registry — Space Tracker

Long-lived defects and known issues. Closed issues are kept here for
historical reference.

---

## Open

### KNOWN-001 — 22 NORAD IDs in curated EO list return HTTP 404 from CelesTrak
- **Severity:** Low (operational, not security)
- **Affects:** `Satellite_Tracker/hires_eo_satellites.py`, `celestrak_tle.py`
- **Discovered:** 2026-05-12 during FEAT-001 smoke run
- **Symptom:** 22 of 65 NORAD IDs fail per-NORAD fetch and are not resolved
  by the bulk-active fallback either:
  ```
  BLACKSKY GLOBAL-12 (51011)  - HTTP 404
  BLACKSKY GLOBAL-13 (51012)  - HTTP 404
  BLACKSKY GLOBAL-21 (53217)  - HTTP 404
  PLEIADES NEO 4    (49069)  - HTTP 404
  GAOFEN-11 02      (46026)  - HTTP 404
  SUPERVIEW-1A      (41902)  - HTTP 404
  ... 16 more
  ```
- **Root cause:** Some commercial constellations (BlackSky, SuperView,
  later SkySats) have had NORAD reassignments since the catalog snapshot
  used when authoring the curated list. Others are decayed / retired.
- **Impact:** Forecast covers 43/65 sats. **All 10 Indian satellites
  resolve correctly.** Coverage is still well over the typical revisit
  cadence; effect on Pakistan blind windows is marginal.
- **Fix path:** Audit each 404 against current CelesTrak SATCAT (search
  by satellite name, get the new NORAD ID), update
  `hires_eo_satellites.py`. Drop irrecoverable entries (decayed).
- **Owner:** PSE  |  **Target:** Within 30 days

### KNOWN-002 — `verify=False` on outbound HTTPS to CelesTrak
- **Severity:** Medium (acknowledged tech debt, project-wide pattern)
- **Affects:** `Satellite_Tracker/celestrak_tle.py`, `sat_live_api.py`
- **Symptom:** TLS certificate validation disabled on every request.
- **Root cause:** Earlier project iterations hit Windows trust-store
  failures in some Python builds and were patched with `verify=False`.
  The new fetcher follows the existing pattern for consistency.
- **Impact:** A MITM on the user's network could substitute TLE data.
  TLEs are public, so the data is not sensitive — the worst-case
  consequence is intentionally corrupted predictions.
- **Fix path:** Switch to system trust store via `certifi`, or use
  `truststore.inject_into_ssl_context()` (Python 3.10+). Remove the
  `verify=False` flag from both files.
- **Owner:** PSE  |  **Target:** Next quarterly hardening pass

### KNOWN-003 — `sgp4` library not installed; falling back to hand-rolled propagator
- **Severity:** Low
- **Affects:** `Satellite_Tracker/forecast_15day.py`
- **Symptom:** Forecast runs but logs `propagator: hand-rolled fallback`.
  Hand-rolled propagator is Kepler-only (no J2/J3 perturbations),
  accurate enough to bucket "over Pakistan at minute N" but
  drift-prone vs. the official `sgp4` library.
- **Fix:** `pip install sgp4` in the user's Python environment. The
  forecast engine prefers it automatically when importable.
- **Owner:** User  |  **Target:** Next dependency install pass

---

## Closed

### CLOSED-012 — Pakistan strategic-site targeting analysis (FEAT-004)
- **Was:** Operator could see which satellites flew over Pakistan, but not
  *which specific strategic assets* each pass could actually image given its
  per-sat tilt standoff. "RISAT-2BR1 overhead at 06:08 PKT" — but does that
  pass actually reach Sargodha PAF Mushaf? GHQ? Khushab? No way to know
  from the forecast.
- **Resolved by:**
  - **New data layer** — `Satellite_Tracker/pakistan_strategic_sites.py`
    with 26 catalogued sites (11 tier-1, 15 tier-2). Every entry sourced
    from **public domain only** (Wikipedia / OSINT / OpenStreetMap
    centroids) — no classified or speculative locations. Tier 1 covers
    the FEAT-004 named cities: Islamabad Red Zone, GHQ Rawalpindi,
    PAF Nur Khan (Chaklala), Karachi Naval HQ, PAF Masroor, PNS Karsaz,
    Lahore Cantt, PAF Walton, PAC Kamra / Minhas, Quetta Samungli,
    PAF Mushaf (Sargodha). Tier 2: corps HQs (Multan, Bahawalpur,
    Gujranwala, Mangla, Peshawar), nuclear (Khushab, Chashma),
    defence industry (POF Wah), academies (PMA Kakul, PAF Risalpur),
    coastal (Ormara Jinnah Naval, Pasni, Gwadar Port), high-altitude
    (Skardu, Gilgit).
  - **Geometry** — `find_targeted_sites(arc, standoff_km)` walks every
    timestep in a pass arc and computes haversine distance to every
    catalog site. A site is "targeted" iff the satellite sub-point comes
    within that satellite's own `standoff_km` of the site at any moment
    during the arc. Output sorted by closest-approach distance.
  - **`forecast_15day.py`** — every crossing in the JSON now carries
    `targeted_sites: [{name, city, tier, category, min_dist_km,
    closest_t_utc}]`.
  - **15-day Word doc** — new top-level "Strategic Site Coverage"
    section showing per-site SAR / Optical / Overhead / Tilt counts
    across all 15 days, plus a "Targets (PK)" column on every per-day
    crossing table. Tier-1 cells render in red.
  - **`forecast_diff.py`** — carries `targeted_sites` through into
    `new_passes` so the popup can see them.
  - **`space_tracker_app.py` ChangesPopup** — pass cards now show a
    bold red `⚠ TARGETS: Islamabad · Rawalpindi · Sargodha` line for
    tier-1 hits and an amber `secondary:` line for tier-2 hits.
  - **Backend** (`pakistan-orbit-tracker-main/.../main.py`) — imports
    the same catalog (`sys.path` to Satellite_Tracker for a single
    source of truth). `/api/positions/hires-eo` adds `targeted_sites`
    per live position (instant snapshot — which sites are reachable
    RIGHT NOW). New `/api/strategic-sites` endpoint serves the catalog.
- **Verified end-to-end:**
  - JSON: 368 of 512 crossings carry targets (72%); 4 675 total target
    hits across the 15-day window (1 968 tier-1 + 2 707 tier-2).
  - Word doc: 26-row coverage table + Targets column on every crossing.
    Top-exposed: Kamra/Minhas 194 passes, Islamabad Red Zone 194,
    POF Wah 193, GHQ Rawalpindi 193, PAF Nur Khan 193, Khushab 192.
  - Sample pass: KOMPSAT-5 (785 km standoff) on 2026-05-13 01:16 UTC
    reaches 6 sites in one arc — Masroor (60 km), Karachi Naval HQ
    (74 km), PNS Karsaz (76 km), Jinnah Naval Base Ormara (180 km),
    Quetta Samungli (224 km), PNS Siddiq Pasni (294 km).
- **Closed:** 2026-05-13

### CLOSED-011 — Forecast-change popup listed past-time passes
- **Was:** "Satellite schedule has changed" popup at 11:36 PKT listed 151 "newly
  scheduled" passes for today including times like 06:28, 07:48, 08:10 PKT —
  all already in the past, useless to the operator.
- **Root cause:** `forecast_diff._diff_day()` computed deltas by date only,
  with no time-of-day filter. Every pass present in today's forecast but
  not in the snapshot baseline became "new", regardless of whether the
  entry time was already past.
- **Resolved by:**
  - `forecast_diff.py` — added `_is_future(entry_utc, now_utc)` and a
    `now_utc` parameter on `_diff_day`. `run()` passes `datetime.utcnow()`
    so every list (`new_passes`, `removed_passes`, `shifted_passes`) drops
    entries whose relevant timestamp is in the past. Filter rule per list:
      * `new`     → keep iff `entry_utc      > now_utc`
      * `removed` → keep iff `entry_utc      > now_utc`  (the would-have-happened time)
      * `shifted` → keep iff `today_entry    > now_utc`
    Output JSON gains a `cutoff_utc` field so consumers can prove the
    filter was applied.
  - `space_tracker_app.py` `ChangesPopup._filter_past_passes()` — same
    filter at display time, defensive against stale JSON if the popup
    opens hours after the diff was written. Counts are re-derived from
    the filtered lists.
  - Deterministic unit test: 3-crossing day (2 past, 1 future) →
    unfiltered says 3 new, filtered says 1 new. PASS.
- **Closed:** 2026-05-13

### CLOSED-010 — Frontend showed 0 satellites; /api/tle?category=hires-eo returned 422
- **Was:** Browser console: `GET /api/tle?category=hires-eo 422 Unprocessable
  Content`. The `hires-eo` curated category was defined in the frontend
  (`CATEGORY_META["hires-eo"]`) but not in the backend's `Category` enum,
  so the generic `/api/tle?category=...` endpoint rejected it. Frontend
  fell back to `api.allorigins.win` which then failed CORS. Net: 0 satellites
  in the dashboard despite 8 Indian + 29 international sats in the catalog.
  Secondary problem: per-NORAD CelesTrak fetches got rate-limited the
  moment we issued 37 of them in parallel, so `/api/positions/hires-eo`
  also returned 0.
- **Resolved by:**
  - `backend/main.py` `/api/tle` — accepts `category` as a raw string,
    branches on `hires-eo` to assemble TLE from the curated NORAD list,
    falls through to `Category(...)` validation for the usual CelesTrak
    groups. Unknown categories now return 400, not 422.
  - `_fetch_hires_eo_tle()` — new bulk-mirror primary path:
    `_populate_hires_eo_cache_from_mirror()` pulls the entire `active.tle`
    block from the GitHub satvisor-data mirror in ONE request, extracts
    our 37 curated NORADs by ID match (TLE line 1 cols 2-7), populates the
    per-NORAD cache. Per-NORAD CelesTrak remains as fallback only.
  - Live verification: `/api/tle?category=hires-eo` → 200, 99 lines = 33
    satellites; `/api/positions/hires-eo` → count=33. The 4 missing match
    the stale-NORAD entries already tracked in KNOWN-001.
- **Closed:** 2026-05-13

### CLOSED-009 — Unified one-click launcher (FEAT-002)
- **Was:** Two competing launchers (`Launch Space Tracker.bat` orchestrator and
  `Launch Space Tracker.vbs` GUI-only) with the `.vbs` hardcoding
  `%LOCALAPPDATA%\Programs\Python\Python311\pythonw.exe`. On a machine without
  exactly that path, the .vbs fell back to PATH and could resolve the
  Microsoft Store stub `WindowsApps\pythonw.exe` (no packages installed) —
  silent crash with no diagnostics.
- **Resolved by:**
  - Rewrote `Launch Space Tracker.bat` as a single hardened orchestrator that
    probes Python 3.10–3.14 install locations, falls back to the existing
    backend venv, and explicitly rejects any `WindowsApps` resolution.
  - Rewrote `Launch Space Tracker.vbs` to silently invoke the .bat (hidden
    window) so there's one entry point for both manual and shortcut use.
  - Added `Install Desktop Shortcut.bat` — runs a one-liner PowerShell COM
    call that creates a `Space Tracker` desktop shortcut pointing at the
    .vbs, with the Windows built-in globe icon (`shell32.dll,14`). No
    binary icon files ship with the project.
  - .bat now runs the GUI in the foreground and cleans up the backend +
    frontend processes (port 8001, 8080) once the GUI closes — no
    orphaned services.
- **Closed:** 2026-05-13

### CLOSED-008 — Hardcoded wrong-machine path in `generate_15day_report.py`
- **Was:** Lines 10-13 hardcoded `c:\Users\User\Desktop\Project\Space_Tracker\
  Satellite_Tracker\` for inputs and dumped output to `Desktop\Pakistan_15Day_
  Surveillance_Report.docx`. After the project was moved to
  `Desktop\new\project-main\project-main\` those paths no longer resolved.
- **Resolved by:** Paths now derived from `os.path.dirname(os.path.abspath(
  __file__))`. Output lands in `Satellite_Tracker/documents/` (kept with the
  rest of the generated reports). Missing-history-file case now exits with a
  helpful message instead of an unhandled `FileNotFoundError`.
- **Closed:** 2026-05-13

### CLOSED-007 — `space_tracker_app.py` reliability fixes
- **Was:** (a) log handle opened at module load was never closed on exit;
  (b) `npm.cmd install` and `npm.cmd run dev` invoked with `shell=True` on
  Windows — path-spaces / shell metacharacter risk; (c) `sat_live_api.py`
  child Popen had no stdout/stderr capture so backend crashes vanished.
- **Resolved by:**
  - Added `atexit`-registered `_close_log_handle()` that flushes and closes
    the redirected stdout/stderr file on process exit.
  - Switched both `npm.cmd` invocations from `shell=True` string form to
    `["cmd.exe", "/c", "npm.cmd", ...]` list form (no shell parsing).
  - `sat_live_api.py` Popen now routes output to `Satellite_Tracker/
    sat_live_api.log` (`stdout=api_log_h, stderr=subprocess.STDOUT`).
- **Closed:** 2026-05-13

### CLOSED-006 — Wide-open CORS + cert-skip on Launch Library 2
- **Was:** (a) `backend/main.py` mounted `CORSMiddleware` with
  `allow_origins=["*"]` — any page in the browser could hammer the local
  backend; (b) `Rocket_Launches/launch_tracker.py` used `verify=False`
  on `ll.thespacedevs.com` (unrelated to the CelesTrak workaround tracked
  in KNOWN-002) plus a project-wide `warnings.filterwarnings("ignore")`
  that hid the resulting cert warning.
- **Resolved by:**
  - CORS now restricted to `127.0.0.1:8080`, `localhost:8080`,
    `127.0.0.1:5173`, `localhost:5173` (the local frontend dev + preview
    ports). `allow_methods` stays `GET`-only.
  - Removed `verify=False` from `launch_tracker.py` (thespacedevs uses
    a normal cert chain). Removed the broad `warnings.filterwarnings(
    "ignore")` so future cert problems are visible. Tightened a bare
    `except:` on the date parser to `except (ValueError, TypeError)`.
- **Note:** CelesTrak `verify=False` workaround in `Satellite_Tracker/`
  is unchanged — see KNOWN-002 for the planned fix path.
- **Closed:** 2026-05-13

### CLOSED-005 — Spurious Indian-crossing count (FEAT-001 v1.1.0)
- **Was:** First production run reported ~11 Indian crossings/day; user's
  historical baseline (April 2026 docs) showed 4-7 Indian/day.
- **Root causes (three combined):**
  1. **Bad NORAD IDs in curated list.** Examples: 42063 was tagged as
     CARTOSAT-2D but CelesTrak returns SENTINEL-2B (ESA); 31797 expected
     EROS-B but actually SAR-LUPE-2 (Germany); several SkySat / BlackSky /
     Pléiades-Neo IDs were stale. Country/sensor labels were taken from
     the *curated list* not the actual TLE, so any non-Indian sat with a
     mis-keyed slot was counted as Indian.
  2. **No daylight filter.** Optical sats were counted on night passes
     (cannot image). User required daytime-only.
  3. **Hand-rolled Kepler propagator producing inflated crossings**
     for low-inclination SAR sats. sgp4 library not installed.
- **Resolved by:**
  - Re-wrote `hires_eo_satellites.py` to a smaller, hand-verified core
    (17 active sats) — dropped decayed Cartosats, dropped unverified
    NORAD-ID slots, dropped SAR sats (out of historical baseline scope).
  - Added `_name_matches()` in `celestrak_tle.py` — TLE names must
    fuzzy-match expected name or the entry is rejected at fetch time.
    Universal safety net against future NORAD typos.
  - Added solar-elevation gate (`_solar_elevation_deg`) in
    `forecast_15day.py` — every crossing is now tagged with
    `sun_elev_deg` and `daytime`; only daytime crossings are kept.
  - Installed `sgp4` library.
- **Result:** 3-5 Indian crossings/day, ~12-17 total crossings/day —
  matches the user's old-document baseline.
- **Closed:** 2026-05-12

### CLOSED-004 — KNOWN-001 (NORAD 404s) subsumed
- The 22 NORAD IDs that returned 404 from CelesTrak were entirely in
  the speculatively-included commercial constellations. The new curated
  list only contains hand-verified IDs, so none of the 17 sats hit 404.
- **Closed:** 2026-05-12 (replaced by name-validation guard)

### CLOSED-003 — sgp4 library not installed
- KNOWN-003 closed: `pip install sgp4` performed. Forecast now logs
  `propagator: sgp4 library`.
- **Closed:** 2026-05-12


### CLOSED-001 — Duplicate NORAD IDs in legacy `TRACKED_SATELLITES`
- **Was:** `41848` listed twice (WorldView-3 + Pléiades 1A); `42063`
  listed twice (Cartosat-2D + Sentinel-2A).
- **Resolved by:** FEAT-001 — `TRACKED_SATELLITES` is now derived from
  `hires_eo_satellites.py` which has uniqueness asserted by
  `BY_NORAD = {str(s.norad_id): s for s in HIRES_EO_SATELLITES}` —
  any future duplicate would silently overwrite, but the smoke test
  `len(HIRES_EO_SATELLITES) == len(BY_NORAD)` catches it.
- **Closed:** 2026-05-12

### CLOSED-002 — DEIMOS-2 misidentified as NORAD 40115
- **Was:** Curated list initially used NORAD 40115 for DEIMOS-2 (collides
  with WorldView-3). Real NORAD ID is 40013.
- **Resolved by:** FEAT-001 pre-commit fix.
- **Closed:** 2026-05-12
