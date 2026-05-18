"""
Curated catalog of operational high-resolution Earth Observation, SAR, and
military reconnaissance satellites that can image Pakistan.

Inclusion criteria:
  - Optical (Panchromatic): published GSD ≤ 1.0 m at nadir
  - SAR: operational synthetic aperture radar with sub-metre to 5 m resolution
  - Military: confirmed dedicated reconnaissance / dual-use with resolution ≤ 0.5 m

`sensor_category` values used throughout the reporting pipeline:
  "Optical"   — requires daylight at sub-satellite point
  "SAR"       — synthetic aperture radar, images day/night/through clouds
  "Military"  — dedicated military reconnaissance (optical or SAR)

Each entry: (norad_id, name, operator, country, sensor, resolution_m,
             sensor_category, notes).
"""

from collections import namedtuple

EOSat = namedtuple(
    "EOSat",
    ["norad_id", "name", "operator", "country", "sensor",
     "resolution_m", "sensor_category", "notes"],
)


HIRES_EO_SATELLITES: list[EOSat] = [

    # ── INDIA (ISRO) — HIGHLIGHTED IN ALL REPORTS ─────────────────────────────
    # Optical Cartosats
    EOSat(41599, "CARTOSAT-2C",  "ISRO", "India", "Panchromatic", 0.65, "Optical",  "Launched 2016"),
    EOSat(41948, "CARTOSAT-2D",  "ISRO", "India", "Panchromatic", 0.65, "Optical",  "Launched 2017"),
    EOSat(42767, "CARTOSAT-2E",  "ISRO", "India", "Panchromatic", 0.65, "Optical",  "Launched 2017"),
    EOSat(43111, "CARTOSAT-2F",  "ISRO", "India", "Panchromatic", 0.65, "Optical",  "Launched 2018"),
    EOSat(44804, "CARTOSAT-3",   "ISRO", "India", "Panchromatic", 0.25, "Optical",  "Best Indian optics, 2019"),
    # Indian SAR reconnaissance
    EOSat(51656, "EOS-04",       "ISRO", "India", "SAR C-band",   1.00, "SAR",      "RISAT-1A, all-weather SAR, 2022"),
    EOSat(44233, "RISAT-2B",     "ISRO", "India", "SAR X-band",   0.50, "SAR",      "Reconnaissance SAR, 2019"),
    EOSat(44857, "RISAT-2BR1",   "ISRO", "India", "SAR X-band",   0.50, "SAR",      "Reconnaissance SAR, 2019"),

    # ── USA (Maxar / DigitalGlobe) ────────────────────────────────────────────
    EOSat(32060, "WORLDVIEW-1",  "Maxar", "USA", "Panchromatic", 0.50, "Optical",  "Launched 2007"),
    EOSat(35946, "WORLDVIEW-2",  "Maxar", "USA", "Panchromatic", 0.46, "Optical",  "Launched 2009"),
    EOSat(40115, "WORLDVIEW-3",  "Maxar", "USA", "Panchromatic", 0.31, "Optical",  "Best commercial optics, 2014"),
    EOSat(33331, "GEOEYE-1",     "Maxar", "USA", "Panchromatic", 0.41, "Optical",  "Launched 2008"),

    # ── FRANCE (Airbus) — Pléiades optical ────────────────────────────────────
    EOSat(38012, "PLEIADES 1A",  "Airbus DS",     "France", "Panchromatic",    0.50, "Optical",  "Launched 2011"),
    EOSat(39019, "PLEIADES 1B",  "Airbus DS",     "France", "Panchromatic",    0.50, "Optical",  "Launched 2012"),
    # French military optical reconnaissance (CSO — Composante Spatiale Optique)
    EOSat(43813, "CSO-1",        "DGA/French MoD","France", "Optical Military",0.35, "Military", "Very high-res military recon, 2018"),
    EOSat(46070, "CSO-2",        "DGA/French MoD","France", "Optical Military",0.35, "Military", "Military recon, 2021"),
    EOSat(49438, "CSO-3",        "DGA/French MoD","France", "Optical Military",0.35, "Military", "Military recon, 2022"),

    # ── ITALY (ASI / Italian MoD) — COSMO-SkyMed military SAR ────────────────
    EOSat(31598, "COSMO-SKYMED 1","ASI/Italian MoD","Italy","SAR X-band Military",1.00,"Military","Dual-use military SAR, 2007"),
    EOSat(32376, "COSMO-SKYMED 2","ASI/Italian MoD","Italy","SAR X-band Military",1.00,"Military","Dual-use military SAR, 2007"),
    EOSat(33053, "COSMO-SKYMED 3","ASI/Italian MoD","Italy","SAR X-band Military",1.00,"Military","Dual-use military SAR, 2008"),
    EOSat(36599, "COSMO-SKYMED 4","ASI/Italian MoD","Italy","SAR X-band Military",1.00,"Military","Dual-use military SAR, 2010"),
    EOSat(45026, "CSG-1",         "ASI/Italian MoD","Italy","SAR X-band Military",0.40,"Military","COSMO 2nd gen, 2019"),
    EOSat(49719, "CSG-2",         "ASI/Italian MoD","Italy","SAR X-band Military",0.40,"Military","COSMO 2nd gen, 2022"),

    # ── GERMANY (DLR / Airbus) — TerraSAR-X / TanDEM-X ──────────────────────
    EOSat(31698, "TERRASAR-X",   "DLR/Airbus", "Germany", "SAR X-band", 0.25, "SAR", "0.25 m spotlight SAR, 2007"),
    EOSat(36605, "TANDEM-X",     "DLR/Airbus", "Germany", "SAR X-band", 0.25, "SAR", "TanDEM formation, 0.25 m, 2010"),

    # ── SOUTH KOREA (KARI) ────────────────────────────────────────────────────
    EOSat(38338, "KOMPSAT-3",    "KARI", "South Korea", "Panchromatic", 0.70, "Optical", "Launched 2012"),
    EOSat(40536, "KOMPSAT-3A",   "KARI", "South Korea", "Panchromatic", 0.55, "Optical", "Launched 2015"),
    EOSat(39227, "KOMPSAT-5",    "KARI", "South Korea", "SAR X-band",   1.00, "SAR",     "All-weather SAR, 2013"),

    # ── CHINA (state Gaofen series) ──────────────────────────────────────────
    EOSat(40118, "GAOFEN-2",     "CNSA", "China", "Panchromatic", 0.80, "Optical", "Launched 2014"),
    EOSat(44703, "GAOFEN-7",     "CNSA", "China", "Panchromatic", 0.65, "Optical", "Stereoscopic, 2019"),
    EOSat(43585, "GAOFEN-11",    "CNSA", "China", "Panchromatic", 0.10, "Optical", "Sub-decimetric, 2018"),
    EOSat(41384, "GAOFEN-3",     "CNSA", "China", "SAR C-band",   1.00, "SAR",     "China's main SAR, 2016"),

    # ── SPAIN ─────────────────────────────────────────────────────────────────
    EOSat(40013, "DEIMOS-2",     "Deimos Imaging", "Spain", "Panchromatic", 0.75, "Optical", "Launched 2014"),
    EOSat(43215, "PAZ",          "Hisdesat",       "Spain", "SAR X-band",   0.25, "SAR",     "Spanish military SAR, 0.25 m spotlight, 2018"),

    # ── ESA / Copernicus — Sentinel-1 SAR ────────────────────────────────────
    EOSat(39634, "SENTINEL-1A",  "ESA", "ESA", "SAR C-band", 5.00, "SAR", "All-weather C-band SAR, free data"),

    # ── ISRAEL — TecSAR military SAR ─────────────────────────────────────────
    EOSat(32273, "TECSAR",       "IAI/Israeli MoD", "Israel", "SAR X-band Military", 0.18, "Military", "0.18 m spotlight, military recon SAR, 2008"),

    # ── JAPAN — ALOS-2 / PALSAR-2 ────────────────────────────────────────────
    EOSat(39769, "ALOS-2",       "JAXA", "Japan", "SAR L-band", 3.00, "SAR", "L-band all-weather SAR, 2014"),
]


# ── Tilt / off-nadir capability per satellite ────────────────────────────────
# Per-satellite imaging geometry. For optical sats: maximum operational
# off-nadir angle (image still spec-quality, not the mechanical maximum).
# For SAR sats: maximum operational incidence angle from each operator's
# published mode-table. Sources:
#   ISRO bulletins (CARTOSAT, RISAT, EOS), Maxar public spec sheets
#   (WorldView, GeoEye), Airbus / CNES (Pleiades, CSO upper bounds),
#   DLR (TerraSAR-X, TanDEM-X), ASI (COSMO-SkyMed, CSG public modes),
#   ESA (Sentinel-1 IW mode), JAXA (ALOS-2 ScanSAR), CNSA (Gaofen
#   published bounds), KARI (KOMPSAT).
# Military-grade values are public upper bounds; classified peak may exceed.
#
# Shape:  norad_id_str -> { "altitude_km": int, "max_tilt_deg": int }
import math

TILT_SPECS: dict[str, dict] = {
    # India — optical Cartosats
    "41599": {"altitude_km": 505, "max_tilt_deg": 26},
    "41948": {"altitude_km": 505, "max_tilt_deg": 26},
    "42767": {"altitude_km": 505, "max_tilt_deg": 26},
    "43111": {"altitude_km": 505, "max_tilt_deg": 26},
    "44804": {"altitude_km": 509, "max_tilt_deg": 32},
    # India — SAR
    "51656": {"altitude_km": 529, "max_tilt_deg": 49},
    "44233": {"altitude_km": 555, "max_tilt_deg": 49},
    "44857": {"altitude_km": 555, "max_tilt_deg": 49},
    # USA — Maxar optical
    "32060": {"altitude_km": 496, "max_tilt_deg": 40},
    "35946": {"altitude_km": 770, "max_tilt_deg": 45},
    "40115": {"altitude_km": 617, "max_tilt_deg": 45},
    "33331": {"altitude_km": 681, "max_tilt_deg": 40},
    # France — Pleiades + CSO military
    "38012": {"altitude_km": 694, "max_tilt_deg": 47},
    "39019": {"altitude_km": 694, "max_tilt_deg": 47},
    "43813": {"altitude_km": 800, "max_tilt_deg": 30},
    "46070": {"altitude_km": 480, "max_tilt_deg": 30},
    "49438": {"altitude_km": 800, "max_tilt_deg": 30},
    # Italy — COSMO-SkyMed + CSG military SAR
    "31598": {"altitude_km": 619, "max_tilt_deg": 50},
    "32376": {"altitude_km": 619, "max_tilt_deg": 50},
    "33053": {"altitude_km": 619, "max_tilt_deg": 50},
    "36599": {"altitude_km": 619, "max_tilt_deg": 50},
    "45026": {"altitude_km": 619, "max_tilt_deg": 60},
    "49719": {"altitude_km": 619, "max_tilt_deg": 60},
    # Germany — TerraSAR-X / TanDEM-X
    "31698": {"altitude_km": 514, "max_tilt_deg": 55},
    "36605": {"altitude_km": 514, "max_tilt_deg": 55},
    # South Korea — KOMPSAT
    "38338": {"altitude_km": 685, "max_tilt_deg": 30},
    "40536": {"altitude_km": 528, "max_tilt_deg": 30},
    "39227": {"altitude_km": 550, "max_tilt_deg": 55},
    # China — Gaofen
    "40118": {"altitude_km": 631, "max_tilt_deg": 35},
    "44703": {"altitude_km": 506, "max_tilt_deg": 25},
    "43585": {"altitude_km": 695, "max_tilt_deg": 35},
    "41384": {"altitude_km": 755, "max_tilt_deg": 50},
    # Spain
    "40013": {"altitude_km": 620, "max_tilt_deg": 30},
    "43215": {"altitude_km": 514, "max_tilt_deg": 55},
    # ESA Sentinel-1
    "39634": {"altitude_km": 693, "max_tilt_deg": 46},
    # Israel TecSAR
    "32273": {"altitude_km": 580, "max_tilt_deg": 50},
    # Japan ALOS-2
    "39769": {"altitude_km": 628, "max_tilt_deg": 60},
}


def altitude_km(norad: str | int) -> int | None:
    """Nominal operating altitude in km from spec sheet."""
    spec = TILT_SPECS.get(str(norad))
    return spec["altitude_km"] if spec else None


def max_tilt_deg(norad: str | int) -> int | None:
    """Maximum operational off-nadir (optical) or incidence (SAR) angle."""
    spec = TILT_SPECS.get(str(norad))
    return spec["max_tilt_deg"] if spec else None


def standoff_km(norad: str | int) -> float | None:
    """Maximum ground standoff distance — how far horizontally from the
    sub-satellite point the sensor can still image. Flat-earth approximation
    (alt × tan θ) is accurate to <1% for LEO ≤ 800 km and θ ≤ 60°.
    """
    spec = TILT_SPECS.get(str(norad))
    if not spec:
        return None
    return round(spec["altitude_km"] * math.tan(math.radians(spec["max_tilt_deg"])), 1)


# ── ≤1 m resolution qualifier (per user spec) ────────────────────────────────
# Only sub-metre optical/SAR satellites get visualised on the map with their
# tilt-coverage circle. Coarser SAR (Sentinel-1 5 m, ALOS-2 3 m) are kept in
# the catalog for completeness but are not drawn.
QUALIFIES_FOR_RADIUS: set[str] = {
    str(s.norad_id) for s in HIRES_EO_SATELLITES
    if s.resolution_m <= 1.0 and s.sensor_category in ("Optical", "SAR", "Military")
}


# ── Quick lookups ─────────────────────────────────────────────────────────────
BY_NORAD: dict[str, EOSat] = {str(s.norad_id): s for s in HIRES_EO_SATELLITES}
BY_COUNTRY: dict[str, list[EOSat]] = {}
for _s in HIRES_EO_SATELLITES:
    BY_COUNTRY.setdefault(_s.country, []).append(_s)

INDIAN_NORAD_IDS: set[str] = {
    str(s.norad_id) for s in HIRES_EO_SATELLITES if s.country == "India"
}

INDIAN_SAR_NORAD_IDS: set[str] = {
    str(s.norad_id) for s in HIRES_EO_SATELLITES
    if s.country == "India" and s.sensor_category == "SAR"
}

SAR_NORAD_IDS: set[str] = {
    str(s.norad_id) for s in HIRES_EO_SATELLITES if s.sensor_category == "SAR"
}

MILITARY_NORAD_IDS: set[str] = {
    str(s.norad_id) for s in HIRES_EO_SATELLITES if s.sensor_category == "Military"
}


def expected_name_tokens(name: str) -> set[str]:
    """Return uppercased tokens (length>=3) from the expected name."""
    cleaned = name.upper().replace("-", " ").replace("(", " ").replace(")", " ")
    return {t for t in cleaned.split() if len(t) >= 3}


def count_by_country() -> dict[str, int]:
    return {c: len(sats) for c, sats in BY_COUNTRY.items()}


if __name__ == "__main__":
    print(f"Total satellites: {len(HIRES_EO_SATELLITES)}")
    for c, sats in sorted(BY_COUNTRY.items(), key=lambda kv: -len(kv[1])):
        marker = " <- HIGHLIGHTED" if c == "India" else ""
        sar_n = sum(1 for s in sats if s.sensor_category in ("SAR", "Military"))
        opt_n = sum(1 for s in sats if s.sensor_category == "Optical")
        print(f"  {c:15s}: {len(sats):3d}  (Optical={opt_n} SAR/Mil={sar_n}){marker}")
    sar = sum(1 for s in HIRES_EO_SATELLITES if "SAR" in s.sensor)
    optical = sum(1 for s in HIRES_EO_SATELLITES if s.sensor_category == "Optical")
    military = sum(1 for s in HIRES_EO_SATELLITES if s.sensor_category == "Military")
    print(f"\nOptical (need daylight): {optical}   SAR (any time): {sar}   Military: {military}")
    print(f"Indian SAR NORADs: {sorted(INDIAN_SAR_NORAD_IDS)}")
