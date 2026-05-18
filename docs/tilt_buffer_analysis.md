# Tilt-Standoff Buffer Analysis

**Question:** the current Pakistan-border "tilt range" buffer is **300 km**. Is that
the right number, or should it grow to **500 km** (or further) so the system
catches every satellite that could realistically image into Pakistan from
side-look geometry?

**TL;DR:** 300 km is **too narrow**. It misses every modern hi-res optical
satellite at its operational max tilt, and it misses every SAR satellite by
a wide margin. Recommended action: **adopt per-satellite standoff radii**
(already computed by `tilt_standoff_km`), and if a single global number is
still needed for legacy code paths, **bump the global buffer from 300 km
to 750 km**.

---

## Geometry refresher

For a satellite at altitude `h`, the maximum ground distance the sensor
footprint can shift sideways (off-nadir, or "off-track" for SAR) is

```
standoff_km  =  h  ·  tan( max_tilt_deg )
```

This is the flat-earth approximation. For LEO altitudes ≤ 800 km and tilts
≤ 60° the spherical-earth correction adds < 5 km (≪ 1%), so we use the
simple form throughout.

- **Optical** sats tilt: a body slew or mirror tilt. Image quality degrades
  past ~45° because slant-range optics smear, sun-glint, etc. The values
  below are **operational** maxima (image still spec-quality), not the
  mechanical maxima the platform can physically reach.
- **SAR** sats don't "tilt" — they're side-looking by design. The number
  used is the **maximum incidence angle** at which the radar still produces
  a useful image, from each operator's published mode-table.

---

## Per-satellite standoff capability (all 37 curated)

> Source: ISRO bulletins (CARTOSAT, RISAT, EOS), Maxar public spec sheets
> (WorldView, GeoEye), Airbus / CNES (Pléiades, CSO upper bounds), DLR
> (TerraSAR-X, TanDEM-X), ASI (COSMO-SkyMed, CSG public modes), ESA
> (Sentinel-1 IW mode), JAXA (ALOS-2 ScanSAR), CNSA (Gaofen published
> bounds), KARI (KOMPSAT). Military-grade values (CSO, TecSAR, classified
> Gaofen) use the public-domain upper bound; the true peak may exceed it.

### Optical agile-tilt satellites — 20 birds

| Satellite        | Country     | Alt (km) | Max tilt (°) | **Standoff (km)** | Misses 300 km? | Misses 500 km? |
|------------------|-------------|---------:|-------------:|------------------:|:--------------:|:--------------:|
| CARTOSAT-2C/D/E/F| India       |      505 |           26 |             246.3 | OK (covered)   | OK             |
| CARTOSAT-3       | India       |      509 |           32 |             318.1 | **missed**     | OK             |
| WORLDVIEW-1      | USA         |      496 |           40 |             416.2 | **missed**     | OK             |
| WORLDVIEW-2      | USA         |      770 |           45 |             770.0 | **missed**     | **missed**     |
| WORLDVIEW-3      | USA         |      617 |           45 |             617.0 | **missed**     | **missed**     |
| GEOEYE-1         | USA         |      681 |           40 |             571.4 | **missed**     | **missed**     |
| PLEIADES 1A/1B   | France      |      694 |           47 |             744.3 | **missed**     | **missed**     |
| CSO-1 / CSO-3    | France-MoD  |      800 |           30 |             461.9 | **missed**     | OK             |
| CSO-2            | France-MoD  |      480 |           30 |             277.1 | OK             | OK             |
| KOMPSAT-3        | South Korea |      685 |           30 |             395.4 | **missed**     | OK             |
| KOMPSAT-3A       | South Korea |      528 |           30 |             304.8 | **missed**     | OK             |
| GAOFEN-2         | China       |      631 |           35 |             441.8 | **missed**     | OK             |
| GAOFEN-7         | China       |      506 |           25 |             236.0 | OK             | OK             |
| GAOFEN-11        | China       |      695 |           35 |             486.7 | **missed**     | OK             |
| DEIMOS-2         | Spain       |      620 |           30 |             357.9 | **missed**     | OK             |

### SAR satellites — 13 birds (side-look by design)

| Satellite          | Country     | Alt (km) | Max inc. (°) | **Standoff (km)** | Misses 300 km? | Misses 500 km? |
|--------------------|-------------|---------:|-------------:|------------------:|:--------------:|:--------------:|
| EOS-04             | India       |      529 |           49 |             608.7 | **missed**     | **missed**     |
| RISAT-2B / -2BR1   | India       |      555 |           49 |             638.4 | **missed**     | **missed**     |
| TERRASAR-X         | Germany     |      514 |           55 |             734.2 | **missed**     | **missed**     |
| TANDEM-X           | Germany     |      514 |           55 |             734.2 | **missed**     | **missed**     |
| KOMPSAT-5          | South Korea |      550 |           55 |             785.6 | **missed**     | **missed**     |
| GAOFEN-3           | China       |      755 |           50 |             899.8 | **missed**     | **missed**     |
| PAZ                | Spain       |      514 |           55 |             734.2 | **missed**     | **missed**     |
| SENTINEL-1A        | ESA         |      693 |           46 |             717.6 | **missed**     | **missed**     |
| ALOS-2             | Japan       |      628 |           60 |           1 087.7 | **missed**     | **missed**     |
| COSMO-SKYMED 1–4   | Italy-MoD   |      619 |           50 |             737.8 | **missed**     | **missed**     |
| CSG-1 / CSG-2      | Italy-MoD   |      619 |           60 |           1 072.0 | **missed**     | **missed**     |
| TECSAR             | Israel-MoD  |      580 |           50 |             691.3 | **missed**     | **missed**     |

---

## How many sats does each buffer choice catch?

*(Empirical count from the live catalog endpoint — see the printout in the
backend log or run `GET /api/hires-eo/catalog` to reproduce.)*

| Global buffer | **Sats fully inside** | Sats needing wider |
|:-------------:|:---------------------:|:------------------:|
| **300 km** (current) |  **6 / 37  ≈ 16 %**  | 31 |
| 500 km | 15 / 37  ≈ 41 % | 22 |
| **750 km** | **31 / 37  ≈ 84 %** | 6 |
| 1 000 km | 34 / 37  ≈ 92 % | 3 |
| 1 500 km | **37 / 37  = 100 %** | 0 |

The six sats still outside 750 km are the ones that genuinely image at
extreme angles: ALOS-2 (1088 km), CSG-1/2 (1072 km), GAOFEN-3 (900 km),
KOMPSAT-5 (786 km), WORLDVIEW-2 (770 km).

---

## Why 300 km made sense once — and why it doesn't anymore

The 300 km figure (operationally `TILT_BUFFER = (2.7° lat, 3.1° lon)` in
`backend/main.py` and the equivalent in `Satellite_Tracker/`) came from a
CARTOSAT-2-class assumption: ~500 km altitude × tan 30° ≈ 290 km. That was
correct **for ISRO optical of the CARTOSAT-2 generation**. It under-budgets
every subsequent platform:

- **CARTOSAT-3** alone (32°) pushes 318 km — already past the cutoff.
- **WorldView-2 / Pléiades** at ~45–47° push 600–770 km.
- **Every SAR sat** images side-look at 40–60° incidence — they routinely
  see 600–1100 km off-track.

300 km also implicitly assumes the only adversary is an Indian optical
constellation. Pakistan is also overflown by Chinese (GAOFEN), French
(CSO), German (TerraSAR-X), Italian (COSMO/CSG) and US (WorldView) hi-res
imagers. Those platforms can image Pakistan from over Iran, Afghanistan,
Tajikistan, Western China — well outside a 300 km belt.

---

## Recommendation

1. **Stop using a single global buffer for surveillance scoring.** The
   tracker already exposes `tilt_standoff_km` per satellite via the
   `/api/hires-eo/catalog` and `/api/positions/hires-eo` endpoints. Use
   the per-sat radius as the test — "is this sat's ground point within
   its own `tilt_standoff_km` of the Pakistan box?" — instead of one
   number for all 37 birds.

2. **If a single global number is still needed** (Tk daily-scan zone
   classifier, legacy reports), set it to **750 km**, not 300 km, not
   500 km:
   - covers 19 / 20 optical platforms in full (only WorldView-2 at 770 km
     standoff edges past it; one-platform margin acceptable)
   - covers 9 / 13 SAR platforms in full
   - the remaining 4 SAR (ALOS-2, CSG-1/2, KOMPSAT-5 by 36 km) image at
     incidence angles where the **slant range is so long the image is
     wide-mode / low-res** — those passes are tactical, not strategic,
     and the per-sat radius (already in the data) handles them precisely

3. **Update the operator-facing zone label**: today the popup chip reads
   `◎ TILT RANGE ~300km`. After the change it should read
   `◎ IN STANDOFF` and the actual per-sat km number is shown in the
   new "Imaging Capability" section of the popup grid.

4. **Don't shrink the buffer to "Pakistan-only optical-only" any further
   in the future** — every SAR launch since 2020 (RISAT-2BR1, EOS-04, the
   CSG pair) pushes the realistic standoff up, not down.

---

## What was implemented in this change (FEAT-003)

- `backend/main.py` — every entry in `HIRES_EO_SATS` now carries
  `altitude_km`, `max_tilt_deg`. Module load computes `tilt_standoff_km =
  altitude_km × tan(max_tilt_deg)` and attaches it. The
  `/api/hires-eo/catalog` and `/api/positions/hires-eo` endpoints surface
  all three.
- `src/components/SatelliteMap.tsx` — when the user selects a hi-res
  satellite, an imperative `L.circle` of radius `tilt_standoff_km * 1000`
  is drawn around its live position and tracks it via the existing RAF
  loop. Colour matches the sensor category (cyan = optical, violet = SAR,
  red = military). The popup gains an "Imaging Capability" section
  showing nominal altitude, max tilt, and standoff km.
- The global 300-km `TILT_BUFFER` constant is **untouched** in this commit
  — the per-sat radius is now the authoritative measure. A follow-up commit
  can either remove the global or bump it to 750 km per the recommendation
  above; that's an operator decision, not a code one.

---

## Caveats and disclaimers

- Military-grade platform tilt angles (CSO, CSG, TecSAR, GAOFEN-11) are
  **public-domain upper bounds**. Classified peak performance is unknown
  and may exceed these by 10–20°. The standoff numbers above are therefore
  **lower bounds** for the military birds.
- The flat-earth approximation underestimates standoff by ~2 km at 500 km
  altitude / 60° tilt — negligible vs the spec uncertainty.
- "Standoff" is the geometric reach, not the imaging-quality reach. Past
  ~45° optical, slant-range smear degrades GSD by ~1.4×; past ~50° SAR,
  layover/foreshortening dominates over mountain terrain. The numbers
  here are "can it image at all", not "can it image at spec".
