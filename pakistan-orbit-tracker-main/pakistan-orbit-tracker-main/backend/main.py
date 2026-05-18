from enum import Enum
from math import sqrt
import time
from datetime import datetime, timezone
import math
from functools import lru_cache

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from sgp4.api import Satrec, jday


TLE_TTL = 2 * 60 * 60  # 2 hours — matches mirror update cadence

# GitHub mirror of CelesTrak — updated automatically via GitHub Actions
# https://github.com/satvisorcom/satvisor-data
MIRROR_BASE = "https://raw.githubusercontent.com/satvisorcom/satvisor-data/master/celestrak/tle/"


class Category(str, Enum):
    stations  = "stations"
    starlink  = "starlink"
    oneweb    = "oneweb"
    gps_ops   = "gps-ops"
    glo_ops   = "glo-ops"
    galileo   = "galileo"
    beidou    = "beidou"
    weather   = "weather"
    noaa      = "noaa"
    goes      = "goes"
    resource  = "resource"
    sarsat    = "sarsat"
    radar     = "radar"
    military  = "military"
    science   = "science"
    geo       = "geo"
    iridium   = "iridium-NEXT"
    intelsat  = "intelsat"
    tdrss     = "tdrss"
    analyst   = "analyst"
    active    = "active"


CATEGORY_META = {
    Category.stations:  {"label": "Space Stations (ISS/CSS)", "slug": "stations",     "max": 50},
    Category.starlink:  {"label": "Starlink",                  "slug": "starlink",     "max": 7000},
    Category.oneweb:    {"label": "OneWeb",                    "slug": "oneweb",       "max": 700},
    Category.gps_ops:   {"label": "GPS Operational",           "slug": "gps-ops",      "max": 50},
    Category.glo_ops:   {"label": "GLONASS",                   "slug": "glo-ops",      "max": 50},
    Category.galileo:   {"label": "Galileo",                   "slug": "galileo",      "max": 50},
    Category.beidou:    {"label": "BeiDou",                    "slug": "beidou",       "max": 60},
    Category.weather:   {"label": "Weather (NOAA)",            "slug": "weather",      "max": 80},
    Category.noaa:      {"label": "NOAA",                      "slug": "noaa",         "max": 20},
    Category.goes:      {"label": "GOES",                      "slug": "goes",         "max": 20},
    Category.resource:  {"label": "Earth Observation",         "slug": "resource",     "max": 200},
    Category.sarsat:    {"label": "SAR / SARSAT",              "slug": "sarsat",       "max": 100},
    Category.radar:     {"label": "Radar",                     "slug": "radar",        "max": 50},
    Category.military:  {"label": "Military / Recon",          "slug": "military",     "max": 100},
    Category.science:   {"label": "Science",                   "slug": "science",      "max": 100},
    Category.geo:       {"label": "Geostationary",             "slug": "geo",          "max": 600},
    Category.iridium:   {"label": "Iridium NEXT",              "slug": "iridium-NEXT", "max": 100},
    Category.intelsat:  {"label": "Intelsat",                  "slug": "intelsat",     "max": 60},
    Category.tdrss:     {"label": "TDRSS",                     "slug": "tdrss",        "max": 30},
    Category.analyst:   {"label": "Analyst",                   "slug": "analyst",      "max": 300},
    Category.active:    {"label": "Active (all)",              "slug": "active",       "max": 15000},
}

# In-memory TLE cache: category -> {fetched_at, text}
tle_cache: dict[Category, dict] = {}

app = FastAPI(title="Pakistan Orbit Tracker Backend")
# Backend runs on 127.0.0.1 and is only consumed by the local Vite dev server
# (port 8080) or its preview port (5173). Locking origins prevents any other
# page in the browser from probing the backend.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:8080",
        "http://localhost:8080",
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


# ── TLE fetching ──────────────────────────────────────────────────────────────

async def fetch_tle(category: Category) -> str:
    slug = CATEGORY_META[category]["slug"]
    url = MIRROR_BASE + slug + ".tle"
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        r = await client.get(url, headers={"User-Agent": "pakistan-orbit-tracker/1.0"})
        r.raise_for_status()
        text = r.text.strip()
        if len(text) < 100:
            raise ValueError(f"TLE response too short ({len(text)} bytes)")
        return text


async def get_tle_text(category: Category) -> str:
    now_ts = time.time()
    cached = tle_cache.get(category)
    if cached and now_ts - cached["fetched_at"] < TLE_TTL:
        return cached["text"]
    try:
        text = await fetch_tle(category)
        tle_cache[category] = {"fetched_at": now_ts, "text": text}
        return text
    except Exception as exc:
        if cached:
            return cached["text"]  # serve stale on failure
        raise HTTPException(502, detail=f"Failed to fetch TLE: {exc}") from exc


def parse_records(text: str, max_count: int) -> list[tuple[str, str, str]]:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    records: list[tuple[str, str, str]] = []
    for i in range(0, len(lines) - 2, 3):
        name, l1, l2 = lines[i], lines[i + 1], lines[i + 2]
        if l1.startswith("1 ") and l2.startswith("2 "):
            records.append((name, l1, l2))
        if len(records) >= max_count:
            break
    return records


# ── SGP4 propagation ──────────────────────────────────────────────────────────

def propagate_now(name: str, line1: str, line2: str) -> dict | None:
    try:
        sat = Satrec.twoline2rv(line1, line2)
        now = datetime.now(timezone.utc)
        jd, fr = jday(now.year, now.month, now.day,
                      now.hour, now.minute, now.second + now.microsecond / 1e6)
        e, r, v = sat.sgp4(jd, fr)
        if e != 0 or not r:
            return None

        x, y, z = r
        vx, vy, vz = v

        # GMST (radians)
        jd_ut1 = jd + fr
        gmst_deg = (280.46061837 + 360.98564736629 * (jd_ut1 - 2451545.0)) % 360
        gmst_rad = math.radians(gmst_deg)

        # ECI → geodetic (WGS84 iterative)
        lon_rad = math.atan2(y, x) - gmst_rad
        lon_deg = (math.degrees(lon_rad) + 180) % 360 - 180

        a = 6378.137
        f = 1 / 298.257223563
        e2 = 2 * f - f * f
        p = math.sqrt(x * x + y * y)
        lat_rad = math.atan2(z, p * (1 - e2))
        for _ in range(5):
            sin_lat = math.sin(lat_rad)
            N = a / math.sqrt(1 - e2 * sin_lat * sin_lat)
            lat_rad = math.atan2(z + e2 * N * sin_lat, p)

        lat_deg = math.degrees(lat_rad)
        sin_lat = math.sin(lat_rad)
        cos_lat = math.cos(lat_rad)
        N = a / math.sqrt(1 - e2 * sin_lat * sin_lat)
        alt_km = (p / cos_lat - N) if abs(cos_lat) > 1e-6 else (abs(z) / abs(sin_lat) - N * (1 - e2))

        return {
            "name": name,
            "lat": round(lat_deg, 4),
            "lon": round(lon_deg, 4),
            "altKm": round(alt_km, 2),
            "velocityKms": round(sqrt(vx*vx + vy*vy + vz*vz), 4),
        }
    except Exception:
        return None


# ── endpoints ─────────────────────────────────────────────────────────────────

# Country code → full name
COUNTRY_NAMES: dict[str, str] = {
    "US": "United States", "RU": "Russia", "CN": "China", "GB": "United Kingdom",
    "FR": "France", "DE": "Germany", "JP": "Japan", "IN": "India",
    "CA": "Canada", "AU": "Australia", "IT": "Italy", "ES": "Spain",
    "KR": "South Korea", "IL": "Israel", "BR": "Brazil", "AE": "UAE",
    "SA": "Saudi Arabia", "PK": "Pakistan", "BD": "Bangladesh", "TH": "Thailand",
    "MX": "Mexico", "AR": "Argentina", "ZA": "South Africa", "NG": "Nigeria",
    "EG": "Egypt", "TR": "Turkey", "UA": "Ukraine", "SE": "Sweden",
    "NO": "Norway", "NL": "Netherlands", "BE": "Belgium", "CH": "Switzerland",
    "AT": "Austria", "PL": "Poland", "CZ": "Czech Republic", "FI": "Finland",
    "DK": "Denmark", "PT": "Portugal", "GR": "Greece", "HU": "Hungary",
    "LU": "Luxembourg", "SG": "Singapore", "MY": "Malaysia", "ID": "Indonesia",
    "PH": "Philippines", "VN": "Vietnam", "NZ": "New Zealand", "IR": "Iran",
    "IQ": "Iraq", "QA": "Qatar", "KW": "Kuwait", "OM": "Oman",
    "TW": "Taiwan", "HK": "Hong Kong", "TH": "Thailand", "LK": "Sri Lanka",
    "MM": "Myanmar", "KZ": "Kazakhstan", "UZ": "Uzbekistan", "AZ": "Azerbaijan",
    "GE": "Georgia", "AM": "Armenia", "BY": "Belarus", "MD": "Moldova",
    "RS": "Serbia", "HR": "Croatia", "SI": "Slovenia", "SK": "Slovakia",
    "RO": "Romania", "BG": "Bulgaria", "LT": "Lithuania", "LV": "Latvia",
    "EE": "Estonia", "IS": "Iceland", "IE": "Ireland", "CY": "Cyprus",
    "MT": "Malta", "AL": "Albania", "MK": "North Macedonia", "BA": "Bosnia",
    "ME": "Montenegro", "XK": "Kosovo", "LI": "Liechtenstein", "MC": "Monaco",
    "SM": "San Marino", "VA": "Vatican", "AD": "Andorra",
    "INT": "International", "ESA": "European Space Agency",
}

# Known patterns for satellites not in SatNOGS catalog.
# Match order matters — most specific first, generic last.
NAME_PATTERNS: list[tuple[str, dict]] = [
    # ── Broadband / Internet constellations ────────────────────────────────
    ("STARLINK",  {"operator": "SpaceX",            "country": "US",  "country_name": "United States",         "purpose": "Broadband Internet Constellation",     "source": "SpaceX",            "destination": "Global Internet Coverage"}),
    ("KUIPER",    {"operator": "Amazon",            "country": "US",  "country_name": "United States",         "purpose": "Broadband Internet Constellation",     "source": "Amazon",            "destination": "Global Internet Coverage"}),
    ("ONEWEB",    {"operator": "Eutelsat OneWeb",   "country": "GB",  "country_name": "United Kingdom",        "purpose": "Broadband Internet Constellation",     "source": "Eutelsat OneWeb",   "destination": "Global Internet Coverage (LEO)"}),
    ("IRIDIUM",   {"operator": "Iridium Communications", "country": "US", "country_name": "United States",     "purpose": "Voice / Data Communications",          "source": "Iridium",           "destination": "Global Mobile Comms (LEO)"}),
    ("GLOBALSTAR",{"operator": "Globalstar Inc.",    "country": "US",  "country_name": "United States",         "purpose": "Voice / Data Communications",          "source": "Globalstar",        "destination": "LEO Comms"}),
    ("ORBCOMM",   {"operator": "Orbcomm",            "country": "US",  "country_name": "United States",         "purpose": "M2M / IoT Communications",             "source": "Orbcomm",           "destination": "LEO Data Network"}),

    # ── Navigation (GNSS) ──────────────────────────────────────────────────
    ("GPS",       {"operator": "US Space Force",     "country": "US",  "country_name": "United States",         "purpose": "Navigation & Positioning (GPS)",       "source": "US Space Force",    "destination": "Global Navigation (MEO)"}),
    ("NAVSTAR",   {"operator": "US Space Force",     "country": "US",  "country_name": "United States",         "purpose": "Navigation & Positioning (GPS)",       "source": "US Space Force",    "destination": "Global Navigation (MEO)"}),
    ("GLONASS",   {"operator": "Roscosmos",          "country": "RU",  "country_name": "Russia",                "purpose": "Navigation & Positioning (GLONASS)",   "source": "Roscosmos",         "destination": "Global Navigation (MEO)"}),
    ("GALILEO",   {"operator": "European GNSS Agency","country": "ESA","country_name": "European Union",        "purpose": "Navigation & Positioning (Galileo)",   "source": "ESA / EUSPA",       "destination": "Global Navigation (MEO)"}),
    ("BEIDOU",    {"operator": "CNSA / CASC",        "country": "CN",  "country_name": "China",                 "purpose": "Navigation & Positioning (BeiDou)",    "source": "CNSA",              "destination": "Global Navigation"}),
    ("COMPASS",   {"operator": "CNSA / CASC",        "country": "CN",  "country_name": "China",                 "purpose": "Navigation & Positioning (BeiDou)",    "source": "CNSA",              "destination": "Global Navigation"}),
    ("QZS",       {"operator": "JAXA / Cabinet Office Japan", "country": "JP", "country_name": "Japan",         "purpose": "Regional Navigation (QZSS)",           "source": "JAXA",              "destination": "Asia-Oceania Navigation"}),
    ("IRNSS",     {"operator": "ISRO",               "country": "IN",  "country_name": "India",                 "purpose": "Regional Navigation (NavIC)",          "source": "ISRO",              "destination": "Indian Subcontinent Navigation"}),
    ("NVS",       {"operator": "ISRO",               "country": "IN",  "country_name": "India",                 "purpose": "Regional Navigation (NavIC)",          "source": "ISRO",              "destination": "Indian Subcontinent Navigation"}),

    # ── Weather ────────────────────────────────────────────────────────────
    ("NOAA",      {"operator": "NOAA / NASA",        "country": "US",  "country_name": "United States",         "purpose": "Weather & Earth Observation",          "source": "NOAA",              "destination": "Global Weather Monitoring"}),
    ("GOES",      {"operator": "NOAA",               "country": "US",  "country_name": "United States",         "purpose": "Geostationary Weather",                "source": "NOAA",              "destination": "Americas Weather Coverage"}),
    ("METEOR",    {"operator": "Roscosmos",          "country": "RU",  "country_name": "Russia",                "purpose": "Weather Observation",                  "source": "Roscosmos",         "destination": "Global Weather Monitoring"}),
    ("METOP",     {"operator": "EUMETSAT / ESA",     "country": "ESA", "country_name": "European Space Agency", "purpose": "Polar-orbiting Meteorology",           "source": "ESA / EUMETSAT",    "destination": "Global Weather Monitoring"}),
    ("HIMAWARI",  {"operator": "JMA",                "country": "JP",  "country_name": "Japan",                 "purpose": "Geostationary Weather",                "source": "JMA",               "destination": "Asia-Pacific Weather"}),
    ("FY-",       {"operator": "CMA / CNSA",         "country": "CN",  "country_name": "China",                 "purpose": "Meteorology (Fengyun)",                "source": "CMA",               "destination": "Global Weather Monitoring"}),
    ("FENGYUN",   {"operator": "CMA / CNSA",         "country": "CN",  "country_name": "China",                 "purpose": "Meteorology (Fengyun)",                "source": "CMA",               "destination": "Global Weather Monitoring"}),
    ("INSAT",     {"operator": "ISRO",               "country": "IN",  "country_name": "India",                 "purpose": "Weather & Communications",             "source": "ISRO",              "destination": "Indian Region"}),

    # ── Earth Observation ──────────────────────────────────────────────────
    ("LANDSAT",   {"operator": "USGS / NASA",        "country": "US",  "country_name": "United States",         "purpose": "Land Imaging",                         "source": "USGS",              "destination": "Earth Observation (SSO)"}),
    ("SENTINEL",  {"operator": "ESA / Copernicus",   "country": "ESA", "country_name": "European Space Agency", "purpose": "Earth Observation (Copernicus)",       "source": "ESA",               "destination": "Earth Observation"}),
    ("WORLDVIEW", {"operator": "Maxar Technologies", "country": "US",  "country_name": "United States",         "purpose": "Commercial High-Res Imaging",          "source": "Maxar",             "destination": "Commercial Earth Observation"}),
    ("GEOEYE",    {"operator": "Maxar Technologies", "country": "US",  "country_name": "United States",         "purpose": "Commercial High-Res Imaging",          "source": "Maxar",             "destination": "Commercial Earth Observation"}),
    ("QUICKBIRD", {"operator": "Maxar Technologies", "country": "US",  "country_name": "United States",         "purpose": "Commercial High-Res Imaging",          "source": "Maxar",             "destination": "Commercial Earth Observation"}),
    ("IKONOS",    {"operator": "Maxar Technologies", "country": "US",  "country_name": "United States",         "purpose": "Commercial High-Res Imaging",          "source": "Maxar",             "destination": "Commercial Earth Observation"}),
    ("PLANET",    {"operator": "Planet Labs",        "country": "US",  "country_name": "United States",         "purpose": "Daily Earth Imaging (Dove)",           "source": "Planet Labs",       "destination": "Commercial Earth Observation"}),
    ("DOVE",      {"operator": "Planet Labs",        "country": "US",  "country_name": "United States",         "purpose": "Daily Earth Imaging",                  "source": "Planet Labs",       "destination": "Commercial Earth Observation"}),
    ("SKYSAT",    {"operator": "Planet Labs",        "country": "US",  "country_name": "United States",         "purpose": "Commercial High-Res Imaging",          "source": "Planet Labs",       "destination": "Commercial Earth Observation"}),
    ("ICEYE",     {"operator": "ICEYE",              "country": "FI",  "country_name": "Finland",               "purpose": "Commercial SAR Imaging",               "source": "ICEYE",             "destination": "Commercial SAR Constellation"}),
    ("CAPELLA",   {"operator": "Capella Space",      "country": "US",  "country_name": "United States",         "purpose": "Commercial SAR Imaging",               "source": "Capella Space",     "destination": "Commercial SAR Constellation"}),
    ("CARTOSAT",  {"operator": "ISRO",               "country": "IN",  "country_name": "India",                 "purpose": "Cartography & High-Res Imaging",       "source": "ISRO",              "destination": "Earth Observation"}),
    ("RESOURCESAT",{"operator": "ISRO",              "country": "IN",  "country_name": "India",                 "purpose": "Natural Resources Monitoring",         "source": "ISRO",              "destination": "Earth Observation"}),
    ("RISAT",     {"operator": "ISRO",               "country": "IN",  "country_name": "India",                 "purpose": "Radar / SAR Imaging",                  "source": "ISRO",              "destination": "Earth Observation (SAR)"}),
    ("EMISAT",    {"operator": "ISRO / DRDO",        "country": "IN",  "country_name": "India",                 "purpose": "Electronic Intelligence (ELINT)",      "source": "DRDO",              "destination": "Signal Intelligence"}),
    ("HYSIS",     {"operator": "ISRO",               "country": "IN",  "country_name": "India",                 "purpose": "Hyperspectral Imaging",                "source": "ISRO",              "destination": "Earth Observation"}),
    ("GSAT",      {"operator": "ISRO",               "country": "IN",  "country_name": "India",                 "purpose": "Communications / Broadcast",           "source": "ISRO",              "destination": "Indian Region (GEO)"}),
    ("OCEANSAT",  {"operator": "ISRO",               "country": "IN",  "country_name": "India",                 "purpose": "Ocean Color & Sea State",              "source": "ISRO",              "destination": "Ocean Monitoring"}),
    ("GAOFEN",    {"operator": "CNSA",               "country": "CN",  "country_name": "China",                 "purpose": "High-Res Earth Observation",           "source": "CNSA",              "destination": "Earth Observation"}),
    ("ZIYUAN",    {"operator": "CNSA",               "country": "CN",  "country_name": "China",                 "purpose": "Civilian Earth Observation",           "source": "CNSA",              "destination": "Earth Observation"}),
    ("HAIYANG",   {"operator": "CNSA",               "country": "CN",  "country_name": "China",                 "purpose": "Ocean Monitoring",                     "source": "CNSA",              "destination": "Ocean Observation"}),
    ("TERRA",     {"operator": "NASA",               "country": "US",  "country_name": "United States",         "purpose": "Earth System Science (EOS)",           "source": "NASA",              "destination": "Earth Observation (SSO)"}),
    ("AQUA",      {"operator": "NASA",               "country": "US",  "country_name": "United States",         "purpose": "Water Cycle Observation (EOS)",        "source": "NASA",              "destination": "Earth Observation (SSO)"}),
    ("AURA",      {"operator": "NASA",               "country": "US",  "country_name": "United States",         "purpose": "Atmospheric Composition (EOS)",        "source": "NASA",              "destination": "Earth Observation (SSO)"}),
    ("MODIS",     {"operator": "NASA",               "country": "US",  "country_name": "United States",         "purpose": "Spectroradiometer Imaging",            "source": "NASA",              "destination": "Earth Observation"}),

    # ── Military / Reconnaissance ──────────────────────────────────────────
    ("OFEK",      {"operator": "IAI / Israeli MoD",  "country": "IL",  "country_name": "Israel",                "purpose": "Reconnaissance",                       "source": "Israeli MoD",       "destination": "Military Earth Observation"}),
    ("OFEQ",      {"operator": "IAI / Israeli MoD",  "country": "IL",  "country_name": "Israel",                "purpose": "Reconnaissance",                       "source": "Israeli MoD",       "destination": "Military Earth Observation"}),
    ("TECSAR",    {"operator": "IAI / Israeli MoD",  "country": "IL",  "country_name": "Israel",                "purpose": "Radar Reconnaissance (SAR)",           "source": "Israeli MoD",       "destination": "Military SAR"}),
    ("EROS",      {"operator": "ImageSat International","country":"IL","country_name": "Israel",                "purpose": "Commercial Reconnaissance",            "source": "ImageSat",          "destination": "Commercial Earth Observation"}),
    ("KH-",       {"operator": "NRO",                "country": "US",  "country_name": "United States",         "purpose": "Optical Reconnaissance (KH)",          "source": "NRO",               "destination": "Military Earth Observation"}),
    ("USA-",      {"operator": "US DoD / NRO",       "country": "US",  "country_name": "United States",         "purpose": "Classified Military",                  "source": "US DoD",            "destination": "Military"}),
    ("YAOGAN",    {"operator": "PLA / CNSA",         "country": "CN",  "country_name": "China",                 "purpose": "Reconnaissance",                       "source": "PLA",               "destination": "Military Earth Observation"}),
    ("LACROSSE",  {"operator": "NRO",                "country": "US",  "country_name": "United States",         "purpose": "Radar Reconnaissance",                 "source": "NRO",               "destination": "Military SAR"}),
    ("RADARSAT",  {"operator": "CSA / MDA",          "country": "CA",  "country_name": "Canada",                "purpose": "Radar Earth Observation",              "source": "CSA",               "destination": "Earth Observation (SAR)"}),
    ("COSMOS",    {"operator": "Roscosmos / VKS",    "country": "RU",  "country_name": "Russia",                "purpose": "Military / Multi-purpose",             "source": "Russian MoD",       "destination": "Military"}),
    ("DMSP",      {"operator": "US Space Force",     "country": "US",  "country_name": "United States",         "purpose": "Military Weather",                     "source": "US DoD",            "destination": "Global Military Weather"}),

    # ── Geostationary Communications ───────────────────────────────────────
    ("INTELSAT",  {"operator": "Intelsat",           "country": "US",  "country_name": "United States",         "purpose": "Geostationary Communications",         "source": "Intelsat",          "destination": "GEO Comms"}),
    ("EUTELSAT",  {"operator": "Eutelsat",           "country": "FR",  "country_name": "France",                "purpose": "Geostationary Communications",         "source": "Eutelsat",          "destination": "GEO Comms"}),
    ("HOTBIRD",   {"operator": "Eutelsat",           "country": "FR",  "country_name": "France",                "purpose": "Geostationary Broadcast",              "source": "Eutelsat",          "destination": "GEO Comms"}),
    ("INMARSAT",  {"operator": "Inmarsat",           "country": "GB",  "country_name": "United Kingdom",        "purpose": "Geostationary Mobile Comms",           "source": "Inmarsat",          "destination": "GEO Comms"}),
    ("ASTRA",     {"operator": "SES",                "country": "LU",  "country_name": "Luxembourg",            "purpose": "Geostationary Broadcast",              "source": "SES",               "destination": "GEO Comms"}),
    ("SES-",      {"operator": "SES",                "country": "LU",  "country_name": "Luxembourg",            "purpose": "Geostationary Communications",         "source": "SES",               "destination": "GEO Comms"}),
    ("TELSTAR",   {"operator": "Telesat",            "country": "CA",  "country_name": "Canada",                "purpose": "Geostationary Communications",         "source": "Telesat",           "destination": "GEO Comms"}),
    ("ANIK",      {"operator": "Telesat",            "country": "CA",  "country_name": "Canada",                "purpose": "Geostationary Communications",         "source": "Telesat",           "destination": "GEO Comms"}),
    ("BSAT",      {"operator": "B-SAT Corporation",  "country": "JP",  "country_name": "Japan",                 "purpose": "Geostationary Broadcast",              "source": "B-SAT",             "destination": "Japan Broadcast (GEO)"}),
    ("PAKSAT",    {"operator": "SUPARCO",            "country": "PK",  "country_name": "Pakistan",              "purpose": "Geostationary Communications",         "source": "SUPARCO",           "destination": "Pakistan GEO Comms"}),
    ("BADR",      {"operator": "Arabsat",            "country": "SA",  "country_name": "Saudi Arabia",          "purpose": "Geostationary Broadcast",              "source": "Arabsat",           "destination": "MENA Region (GEO)"}),
    ("NILESAT",   {"operator": "Nilesat",            "country": "EG",  "country_name": "Egypt",                 "purpose": "Geostationary Broadcast",              "source": "Nilesat",           "destination": "MENA Region (GEO)"}),
    ("YAMAL",     {"operator": "Gazprom Space Systems","country": "RU","country_name": "Russia",                "purpose": "Geostationary Communications",         "source": "Gazprom",           "destination": "Russia GEO Comms"}),
    ("EXPRESS",   {"operator": "RSCC",               "country": "RU",  "country_name": "Russia",                "purpose": "Geostationary Communications",         "source": "RSCC",              "destination": "Russia GEO Comms"}),
    ("CHINASAT",  {"operator": "China Satcom",       "country": "CN",  "country_name": "China",                 "purpose": "Geostationary Communications",         "source": "China Satcom",      "destination": "China GEO Comms"}),
    ("APSTAR",    {"operator": "APT Satellite",      "country": "HK",  "country_name": "Hong Kong",             "purpose": "Geostationary Communications",         "source": "APT Satellite",     "destination": "Asia-Pacific GEO"}),
    ("THAICOM",   {"operator": "Thaicom",            "country": "TH",  "country_name": "Thailand",              "purpose": "Geostationary Communications",         "source": "Thaicom",           "destination": "Asia-Pacific GEO"}),
    ("MEASAT",    {"operator": "MEASAT",             "country": "MY",  "country_name": "Malaysia",              "purpose": "Geostationary Communications",         "source": "MEASAT",            "destination": "Asia-Pacific GEO"}),
    ("KOREASAT",  {"operator": "KT SAT",             "country": "KR",  "country_name": "South Korea",           "purpose": "Geostationary Communications",         "source": "KT SAT",            "destination": "Asia-Pacific GEO"}),

    # ── Space Stations / Crewed / Cargo ────────────────────────────────────
    ("ISS",       {"operator": "NASA / Roscosmos / ESA / JAXA / CSA", "country": "INT", "country_name": "International", "purpose": "Crewed Space Station",   "source": "Multi-national",    "destination": "Low Earth Orbit Research"}),
    ("TIANGONG",  {"operator": "CMSA",               "country": "CN",  "country_name": "China",                 "purpose": "Crewed Space Station",                 "source": "CMSA",              "destination": "Low Earth Orbit Research"}),
    ("CSS",       {"operator": "CMSA",               "country": "CN",  "country_name": "China",                 "purpose": "Space Station Module",                 "source": "CMSA",              "destination": "Low Earth Orbit Research"}),
    ("SOYUZ",     {"operator": "Roscosmos",          "country": "RU",  "country_name": "Russia",                "purpose": "Crewed Transport",                     "source": "Roscosmos",         "destination": "ISS / LEO"}),
    ("PROGRESS",  {"operator": "Roscosmos",          "country": "RU",  "country_name": "Russia",                "purpose": "Cargo Resupply",                       "source": "Roscosmos",         "destination": "ISS"}),
    ("CYGNUS",    {"operator": "Northrop Grumman",   "country": "US",  "country_name": "United States",         "purpose": "Cargo Resupply",                       "source": "Northrop Grumman",  "destination": "ISS"}),
    ("DRAGON",    {"operator": "SpaceX / NASA",      "country": "US",  "country_name": "United States",         "purpose": "Crewed / Cargo Transport",             "source": "SpaceX",            "destination": "ISS"}),
    ("SHENZHOU",  {"operator": "CMSA",               "country": "CN",  "country_name": "China",                 "purpose": "Crewed Transport",                     "source": "CMSA",              "destination": "Tiangong"}),
    ("TIANZHOU",  {"operator": "CMSA",               "country": "CN",  "country_name": "China",                 "purpose": "Cargo Resupply",                       "source": "CMSA",              "destination": "Tiangong"}),

    # ── Science / Research ─────────────────────────────────────────────────
    ("HUBBLE",    {"operator": "NASA / ESA",         "country": "US",  "country_name": "United States",         "purpose": "Space Telescope (Optical)",            "source": "NASA",              "destination": "Astronomy"}),
    ("JWST",      {"operator": "NASA / ESA / CSA",   "country": "US",  "country_name": "United States",         "purpose": "Space Telescope (Infrared)",           "source": "NASA",              "destination": "Sun-Earth L2"}),
    ("CHANDRA",   {"operator": "NASA",               "country": "US",  "country_name": "United States",         "purpose": "X-Ray Space Telescope",                "source": "NASA",              "destination": "Astronomy"}),
    ("SWIFT",     {"operator": "NASA",               "country": "US",  "country_name": "United States",         "purpose": "Gamma-Ray Burst Observatory",          "source": "NASA",              "destination": "Astronomy"}),
    ("FERMI",     {"operator": "NASA",               "country": "US",  "country_name": "United States",         "purpose": "Gamma-Ray Space Telescope",            "source": "NASA",              "destination": "Astronomy"}),

    # ── Ham / Amateur radio ────────────────────────────────────────────────
    ("AO-",       {"operator": "AMSAT",              "country": "INT", "country_name": "International",         "purpose": "Amateur Radio",                        "source": "AMSAT",             "destination": "Amateur Radio"}),
    ("FO-",       {"operator": "JARL",               "country": "JP",  "country_name": "Japan",                 "purpose": "Amateur Radio",                        "source": "JARL",              "destination": "Amateur Radio"}),
    ("SO-",       {"operator": "AMSAT",              "country": "INT", "country_name": "International",         "purpose": "Amateur Radio",                        "source": "AMSAT",             "destination": "Amateur Radio"}),

    # ── Modern military / intelligence / SDA & USSF programs ───────────────
    # These names started flying 2020+ and are missing from older SatNOGS dumps.
    ("PRAETORIAN", {"operator": "US Space Force / USSF",      "country": "US",  "country_name": "United States",  "purpose": "Space Domain Awareness / SSA",       "source": "US Space Force",     "destination": "Space Domain Awareness"}),
    ("USSF-",      {"operator": "US Space Force",             "country": "US",  "country_name": "United States",  "purpose": "Classified Military",                 "source": "US Space Force",     "destination": "Military"}),
    ("NROL-",      {"operator": "NRO",                        "country": "US",  "country_name": "United States",  "purpose": "Classified Reconnaissance",           "source": "NRO",                "destination": "Military Reconnaissance"}),
    ("VICTUS",     {"operator": "US Space Force / SSC",       "country": "US",  "country_name": "United States",  "purpose": "Tactically Responsive Space",         "source": "US Space Force",     "destination": "Military"}),
    ("SDA-T",      {"operator": "Space Development Agency",   "country": "US",  "country_name": "United States",  "purpose": "Tranche Tracking / Transport Layer",  "source": "SDA",                "destination": "Proliferated LEO Constellation"}),
    ("TRANSPORT",  {"operator": "Space Development Agency",   "country": "US",  "country_name": "United States",  "purpose": "Tactical Comms Constellation",        "source": "SDA",                "destination": "Proliferated LEO Constellation"}),
    ("TRACKING",   {"operator": "Space Development Agency",   "country": "US",  "country_name": "United States",  "purpose": "Missile Warning / Tracking",          "source": "SDA",                "destination": "Proliferated LEO Constellation"}),
    ("SBIRS",      {"operator": "US Space Force",             "country": "US",  "country_name": "United States",  "purpose": "Missile Warning (SBIRS)",             "source": "US Space Force",     "destination": "Strategic Surveillance"}),
    ("STP-SAT",    {"operator": "DoD Space Test Program",     "country": "US",  "country_name": "United States",  "purpose": "Military Technology Demonstration",   "source": "US DoD",             "destination": "Military Research"}),

    # ── Modern commercial constellations (post-2018) ──────────────────────
    ("BLACKSKY",   {"operator": "BlackSky Technology",        "country": "US",  "country_name": "United States",  "purpose": "Commercial High-Res Imaging",         "source": "BlackSky",           "destination": "Commercial Earth Observation"}),
    ("HAWKEYE",    {"operator": "HawkEye 360",                "country": "US",  "country_name": "United States",  "purpose": "RF Geolocation",                      "source": "HawkEye 360",        "destination": "Commercial SIGINT"}),
    ("HAWK-",      {"operator": "HawkEye 360",                "country": "US",  "country_name": "United States",  "purpose": "RF Geolocation",                      "source": "HawkEye 360",        "destination": "Commercial SIGINT"}),
    ("LEMUR-",     {"operator": "Spire Global",               "country": "US",  "country_name": "United States",  "purpose": "AIS / Weather / RF Sensing",          "source": "Spire Global",       "destination": "Commercial Data Network"}),
    ("SPIRE",      {"operator": "Spire Global",               "country": "US",  "country_name": "United States",  "purpose": "AIS / Weather / RF Sensing",          "source": "Spire Global",       "destination": "Commercial Data Network"}),
    ("FLOCK",      {"operator": "Planet Labs",                "country": "US",  "country_name": "United States",  "purpose": "Daily Earth Imaging (Dove)",          "source": "Planet Labs",        "destination": "Commercial Earth Observation"}),
    ("SUPERDOVE",  {"operator": "Planet Labs",                "country": "US",  "country_name": "United States",  "purpose": "Daily Earth Imaging",                 "source": "Planet Labs",        "destination": "Commercial Earth Observation"}),
    ("BLUEBIRD",   {"operator": "AST SpaceMobile",            "country": "US",  "country_name": "United States",  "purpose": "Direct-to-Phone Broadband",           "source": "AST SpaceMobile",    "destination": "Cellular Constellation"}),
    ("BLUEWALKER", {"operator": "AST SpaceMobile",            "country": "US",  "country_name": "United States",  "purpose": "Direct-to-Phone Broadband (Prototype)","source": "AST SpaceMobile",   "destination": "Cellular Constellation"}),
    ("JILIN",      {"operator": "Chang Guang Satellite",      "country": "CN",  "country_name": "China",          "purpose": "Commercial High-Res Imaging",         "source": "Chang Guang",        "destination": "Commercial Earth Observation"}),
    ("YUNHAI",     {"operator": "CASC",                       "country": "CN",  "country_name": "China",          "purpose": "Atmospheric Observation / Recon",     "source": "CASC",               "destination": "Earth Observation"}),
    ("GUOWANG",    {"operator": "China SatNet",               "country": "CN",  "country_name": "China",          "purpose": "Broadband Internet Constellation",    "source": "China SatNet",       "destination": "Global Internet Coverage"}),
    ("QIANFAN",    {"operator": "Shanghai Spacecom (SSST)",   "country": "CN",  "country_name": "China",          "purpose": "Broadband Internet Constellation",    "source": "SSST",               "destination": "Global Internet Coverage"}),
    ("STARSHIELD", {"operator": "SpaceX / NRO",               "country": "US",  "country_name": "United States",  "purpose": "Military Reconnaissance Constellation","source": "NRO / SpaceX",      "destination": "Military Reconnaissance"}),
    ("YAM-",       {"operator": "Loft Orbital",               "country": "US",  "country_name": "United States",  "purpose": "Satellite-as-a-Service Hosted Payload","source": "Loft Orbital",      "destination": "Multi-Payload LEO"}),
    ("VARDA",      {"operator": "Varda Space Industries",     "country": "US",  "country_name": "United States",  "purpose": "In-Space Manufacturing",              "source": "Varda",              "destination": "Microgravity Production"}),
    ("BANDWAGON",  {"operator": "SpaceX (Rideshare)",         "country": "INT", "country_name": "International",  "purpose": "Rideshare Payload",                   "source": "SpaceX Rideshare",   "destination": "Various (Rideshare)"}),
    ("TRANSPORTER",{"operator": "SpaceX (Rideshare)",         "country": "INT", "country_name": "International",  "purpose": "Rideshare Payload",                   "source": "SpaceX Rideshare",   "destination": "Various (Rideshare)"}),
    ("O3B",        {"operator": "SES O3b",                    "country": "LU",  "country_name": "Luxembourg",     "purpose": "MEO Broadband Communications",        "source": "SES",                "destination": "MEO Comms"}),
    ("MPOWER",     {"operator": "SES O3b mPOWER",             "country": "LU",  "country_name": "Luxembourg",     "purpose": "MEO Broadband Communications",        "source": "SES",                "destination": "MEO Comms"}),
    ("KINEIS",     {"operator": "Kineis (CLS)",               "country": "FR",  "country_name": "France",         "purpose": "IoT Constellation (Argos)",           "source": "Kineis",             "destination": "Global IoT Network"}),
    ("ELSA-",      {"operator": "Astroscale",                 "country": "JP",  "country_name": "Japan",          "purpose": "Active Debris Removal Demo",          "source": "Astroscale",         "destination": "On-Orbit Servicing"}),
    ("CLEARSPACE", {"operator": "ClearSpace",                 "country": "CH",  "country_name": "Switzerland",    "purpose": "Active Debris Removal",               "source": "ClearSpace",         "destination": "On-Orbit Servicing"}),

    # ── Specific identifier prefixes that signal classified/unidentified ──
    ("OBJECT",     {"operator": "Unknown (Unidentified Object)","country": "??","country_name": "Unidentified",   "purpose": "Unidentified Object",                 "source": "Catalog placeholder","destination": "Unknown"}),
    ("TBA-",       {"operator": "Unknown (To Be Assigned)",   "country": "??", "country_name": "Unassigned",      "purpose": "Newly Catalogued (TBA)",              "source": "Catalog placeholder","destination": "Unknown"}),
]

# SatNOGS catalog cache
_satnogs_catalog: dict | None = None
_catalog_fetched_at: float = 0
CATALOG_TTL = 24 * 3600  # refresh daily

async def get_satnogs_catalog() -> dict:
    global _satnogs_catalog, _catalog_fetched_at
    now = time.time()
    if _satnogs_catalog and now - _catalog_fetched_at < CATALOG_TTL:
        return _satnogs_catalog
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(
                "https://raw.githubusercontent.com/satvisorcom/satvisor-data/master/catalog/satnogs.json"
            )
            r.raise_for_status()
            _satnogs_catalog = r.json()
            _catalog_fetched_at = now
    except Exception:
        if _satnogs_catalog:
            return _satnogs_catalog
        _satnogs_catalog = {}
    return _satnogs_catalog


def _parse_intl_designator(line1: str) -> dict:
    """Extract launch year + launch number from TLE line 1 columns 10-17.

    Format: 'YYNNNAAA' where YY is 2-digit year (00-56 = 2000-2056, 57-99 =
    1957-1999 per NORAD convention), NNN is launch # in that year, AAA is
    the piece letter(s) within that launch. Returns
      {launch_year, launch_num, intl_designator}
    or {} if the line is too short to parse.
    """
    if not line1 or len(line1) < 17:
        return {}
    chunk = line1[9:17].strip()
    if len(chunk) < 5:
        return {}
    try:
        yy = int(chunk[:2])
        full_year = 2000 + yy if yy <= 56 else 1900 + yy
        num = int(chunk[2:5])
        piece = chunk[5:].strip() or ""
        return {
            "launch_year": full_year,
            "launch_num":  num,
            "intl_designator": f"{full_year}-{num:03d}{piece}",
        }
    except (ValueError, TypeError):
        return {}


def _find_tle_lines_for_norad(norad: str) -> tuple[str, str, str] | None:
    """Search all cached TLE blocks (per-category mirror cache + per-NORAD
    hires-eo cache) for a NORAD ID. Returns (name, line1, line2) or None.
    """
    # Per-NORAD hi-res EO cache: dict[norad -> {line1, line2}]
    cached = _hires_eo_tle_cache.get(norad)
    if cached:
        sat = _HIRES_EO_BY_NORAD.get(norad)
        nm = sat["name"] if sat else norad
        return (nm, cached["line1"], cached["line2"])
    # Category bulk cache
    for cat_cache in tle_cache.values():
        lines = [l.strip() for l in cat_cache["text"].splitlines() if l.strip()]
        for i in range(0, len(lines) - 2, 3):
            if (lines[i+1].startswith("1 ")
                    and lines[i+1][2:7].strip() == norad):
                return (lines[i], lines[i+1], lines[i+2])
    return None


def build_metadata(norad: str, name: str, catalog: dict) -> dict:
    """Build full satellite metadata from catalog + name pattern matching."""
    meta: dict = {"norad": norad, "name": name}

    # Pre-compute TLE-derived launch year. Even when SatNOGS or pattern match
    # gives us most of the data, the intl designator is a reliable anchor.
    tle = _find_tle_lines_for_norad(norad)
    intl = _parse_intl_designator(tle[1]) if tle else {}

    # 1. Try SatNOGS catalog first
    entry = catalog.get(norad)
    if entry:
        sat = entry.get("sat", [])
        if len(sat) >= 9:
            cc_raw = sat[5] or ""
            ccs = [c.strip() for c in cc_raw.split(",") if c.strip()]
            country_names = ", ".join(COUNTRY_NAMES.get(c, c) for c in ccs)
            meta.update({
                "operator":     sat[6] or "Unknown",
                "country":      cc_raw,
                "country_name": country_names or "Unknown",
                "status":       sat[3] or "unknown",
                "launch_date":  sat[4],
                "image":        f"https://db.satnogs.org/media/{sat[7]}" if sat[7] else None,
                "website":      sat[8],
                "purpose":      _infer_purpose(name),
                "source":       country_names or "Unknown",
                "destination":  _infer_destination(name),
                "catalog_source": "SatNOGS / CelesTrak",
                "intl_designator": intl.get("intl_designator"),
            })
            return meta

    # 2. Fall back to name pattern matching
    name_up = name.upper()
    for pattern, info in NAME_PATTERNS:
        if pattern in name_up:
            meta.update(info)
            meta["status"] = "operational"
            # Use TLE launch year as launch date if we don't have a real one.
            meta["launch_date"] = (str(intl["launch_year"])
                                   if intl.get("launch_year") else None)
            meta["image"] = None
            meta["website"] = None
            meta["catalog_source"] = (
                f"Pattern match + TLE intl-designator ({intl.get('intl_designator')})"
                if intl.get("intl_designator") else "Pattern match"
            )
            meta["intl_designator"] = intl.get("intl_designator")
            return meta

    # 3. Honest unknown — but enriched with whatever we can derive from the TLE
    meta.update({
        "operator": "Unknown",
        "country": "Unknown",
        "country_name": "Unknown",
        # If the satellite is being actively tracked it's operational by
        # definition; "unknown" is misleading for an object we're showing
        # a live position for.
        "status": "operational" if tle else "unknown",
        "launch_date": str(intl["launch_year"]) if intl.get("launch_year") else None,
        "image": None,
        "website": None,
        "purpose": _infer_purpose(name),
        "source": (f"TLE intl-designator {intl.get('intl_designator')}"
                   if intl.get("intl_designator") else "Unknown"),
        "destination": _infer_destination(name),
        "catalog_source": (
            f"TLE only — not in public catalogs (intl-designator "
            f"{intl.get('intl_designator')})"
            if intl.get("intl_designator") else "None"
        ),
        "intl_designator": intl.get("intl_designator"),
    })
    return meta


def _infer_purpose(name: str) -> str:
    n = name.upper()
    if any(x in n for x in ["STARLINK", "ONEWEB", "KUIPER"]): return "Broadband Internet"
    if any(x in n for x in ["GPS", "NAVSTAR", "GLONASS", "GALILEO", "BEIDOU"]): return "Navigation"
    if any(x in n for x in ["NOAA", "METEOR", "METOP", "GOES", "DMSP"]): return "Weather / Earth Observation"
    if any(x in n for x in ["ISS", "TIANGONG", "CSS", "MIR"]): return "Space Station"
    if any(x in n for x in ["SOYUZ", "PROGRESS", "CYGNUS", "DRAGON", "HTV"]): return "Cargo / Crew Transport"
    if any(x in n for x in ["IRIDIUM", "GLOBALSTAR", "INTELSAT", "SES"]): return "Communications"
    if any(x in n for x in ["LANDSAT", "SENTINEL", "SPOT", "WORLDVIEW"]): return "Earth Observation"
    if any(x in n for x in ["CUBESAT", "NANOSAT"]): return "CubeSat / Research"
    return "Scientific / Research"


def _infer_destination(name: str) -> str:
    n = name.upper()
    if any(x in n for x in ["STARLINK", "ONEWEB"]): return "Global Internet Coverage"
    if any(x in n for x in ["GPS", "NAVSTAR", "GLONASS", "GALILEO"]): return "Global Navigation"
    if any(x in n for x in ["NOAA", "METEOR", "METOP", "GOES", "DMSP"]): return "Global Weather Monitoring"
    if any(x in n for x in ["ISS", "CSS", "TIANGONG"]): return "Low Earth Orbit Research"
    if any(x in n for x in ["PROGRESS", "CYGNUS", "DRAGON", "SOYUZ", "HTV"]): return "ISS Resupply"
    return "Low Earth Orbit"


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/categories")
def list_categories():
    return {
        cat.value: {"label": meta["label"], "max": meta["max"]}
        for cat, meta in CATEGORY_META.items()
    }


@app.get("/api/tle", response_class=PlainTextResponse)
async def get_tle(category: str = Query(...)):
    # Special case: the curated Imagery+SAR list is not a single CelesTrak group
    # but a hand-picked NORAD set. Assemble its TLE block on the fly so the
    # frontend's generic loadSatellites() path works without an external proxy.
    if category == "hires-eo":
        import asyncio
        results = await asyncio.gather(
            *[_fetch_hires_eo_tle(s["norad"]) for s in HIRES_EO_SATS]
        )
        out: list[str] = []
        for sat, res in zip(HIRES_EO_SATS, results):
            if res is None:
                continue
            l1, l2 = res
            out.extend([sat["name"], l1, l2])
        return "\n".join(out) + "\n"

    try:
        cat = Category(category)
    except ValueError:
        raise HTTPException(400, detail=f"Unknown category: {category}")
    return await get_tle_text(cat)


@app.get("/api/positions")
async def get_positions(category: Category = Query(...)):
    """Return live SGP4-propagated positions for all satellites in a category."""
    text = await get_tle_text(category)
    records = parse_records(text, CATEGORY_META[category]["max"])
    positions = [p for name, l1, l2 in records if (p := propagate_now(name, l1, l2))]
    return {
        "category": category.value,
        "count": len(positions),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "positions": positions,
    }


@app.get("/api/positions/pakistan")
async def get_positions_pakistan(category: Category = Query(...)):
    """Return only satellites currently over Pakistan (23-37N, 60-78E)."""
    text = await get_tle_text(category)
    records = parse_records(text, CATEGORY_META[category]["max"])
    all_positions = [p for name, l1, l2 in records if (p := propagate_now(name, l1, l2))]
    over_pk = [
        p for p in all_positions
        if 23 <= p["lat"] <= 37 and 60 <= p["lon"] <= 78
    ]
    return {
        "category": category.value,
        "total": len(all_positions),
        "over_pakistan": len(over_pk),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "positions": over_pk,
    }


# ── Curated imagery & SAR surveillance satellite list (mirrors hires_eo_satellites.py) ───
# sensor_category: "Optical" | "SAR" | "Military"
# Per-satellite tilt + altitude metadata.
#
#   altitude_km    : nominal operating altitude (from spec sheet, NOT from live
#                    TLE — TLEs can be stale/swapped; nominal is the truth-of-
#                    record for capability analysis).
#   max_tilt_deg   : operationally documented maximum off-nadir tilt (optical)
#                    or maximum incidence angle (SAR). Sources:
#                      ISRO bulletins (CARTOSAT/RISAT/EOS),
#                      Maxar public spec sheets (WV/GeoEye),
#                      Airbus/CNES (Pleiades, CSO public bounds),
#                      DLR (TerraSAR-X), ASI (COSMO/CSG public modes),
#                      ESA (Sentinel-1 IW mode), JAXA (ALOS-2 ScanSAR),
#                      CNSA published bounds.
#                    For military-grade systems (CSO, TecSAR) the value is the
#                    public-domain upper bound; classified peak may exceed it.
#   tilt_standoff_km: pre-computed alt * tan(max_tilt_deg) — the ground-track
#                    horizontal distance the sensor footprint shifts at max
#                    tilt. Inserted at module load (see _annotate_hires_eo_).
#
HIRES_EO_SATS: list[dict] = [
    # India (ISRO) — Optical
    {"norad": "41599", "name": "CARTOSAT-2C",   "country": "India",       "operator": "ISRO",             "resolution_m": 0.65, "sensor": "Panchromatic",        "sensor_category": "Optical",  "altitude_km": 505, "max_tilt_deg": 26},
    {"norad": "41948", "name": "CARTOSAT-2D",   "country": "India",       "operator": "ISRO",             "resolution_m": 0.65, "sensor": "Panchromatic",        "sensor_category": "Optical",  "altitude_km": 505, "max_tilt_deg": 26},
    {"norad": "42767", "name": "CARTOSAT-2E",   "country": "India",       "operator": "ISRO",             "resolution_m": 0.65, "sensor": "Panchromatic",        "sensor_category": "Optical",  "altitude_km": 505, "max_tilt_deg": 26},
    {"norad": "43111", "name": "CARTOSAT-2F",   "country": "India",       "operator": "ISRO",             "resolution_m": 0.65, "sensor": "Panchromatic",        "sensor_category": "Optical",  "altitude_km": 505, "max_tilt_deg": 26},
    {"norad": "44804", "name": "CARTOSAT-3",    "country": "India",       "operator": "ISRO",             "resolution_m": 0.25, "sensor": "Panchromatic",        "sensor_category": "Optical",  "altitude_km": 509, "max_tilt_deg": 32},
    # India (ISRO) — SAR reconnaissance
    {"norad": "51656", "name": "EOS-04",         "country": "India",       "operator": "ISRO",             "resolution_m": 1.00, "sensor": "SAR C-band",          "sensor_category": "SAR",      "altitude_km": 529, "max_tilt_deg": 49},
    {"norad": "44233", "name": "RISAT-2B",       "country": "India",       "operator": "ISRO",             "resolution_m": 0.50, "sensor": "SAR X-band",          "sensor_category": "SAR",      "altitude_km": 555, "max_tilt_deg": 49},
    {"norad": "44857", "name": "RISAT-2BR1",     "country": "India",       "operator": "ISRO",             "resolution_m": 0.50, "sensor": "SAR X-band",          "sensor_category": "SAR",      "altitude_km": 555, "max_tilt_deg": 49},
    # USA (Maxar) — Optical
    {"norad": "32060", "name": "WORLDVIEW-1",   "country": "USA",         "operator": "Maxar",            "resolution_m": 0.50, "sensor": "Panchromatic",        "sensor_category": "Optical",  "altitude_km": 496, "max_tilt_deg": 40},
    {"norad": "35946", "name": "WORLDVIEW-2",   "country": "USA",         "operator": "Maxar",            "resolution_m": 0.46, "sensor": "Panchromatic",        "sensor_category": "Optical",  "altitude_km": 770, "max_tilt_deg": 45},
    {"norad": "40115", "name": "WORLDVIEW-3",   "country": "USA",         "operator": "Maxar",            "resolution_m": 0.31, "sensor": "Panchromatic",        "sensor_category": "Optical",  "altitude_km": 617, "max_tilt_deg": 45},
    {"norad": "33331", "name": "GEOEYE-1",      "country": "USA",         "operator": "Maxar",            "resolution_m": 0.41, "sensor": "Panchromatic",        "sensor_category": "Optical",  "altitude_km": 681, "max_tilt_deg": 40},
    # France — Optical + Military
    {"norad": "38012", "name": "PLEIADES 1A",   "country": "France",      "operator": "Airbus DS",        "resolution_m": 0.50, "sensor": "Panchromatic",        "sensor_category": "Optical",  "altitude_km": 694, "max_tilt_deg": 47},
    {"norad": "39019", "name": "PLEIADES 1B",   "country": "France",      "operator": "Airbus DS",        "resolution_m": 0.50, "sensor": "Panchromatic",        "sensor_category": "Optical",  "altitude_km": 694, "max_tilt_deg": 47},
    {"norad": "43813", "name": "CSO-1",          "country": "France",      "operator": "DGA/French MoD",   "resolution_m": 0.35, "sensor": "Optical Military",    "sensor_category": "Military", "altitude_km": 800, "max_tilt_deg": 30},
    {"norad": "46070", "name": "CSO-2",          "country": "France",      "operator": "DGA/French MoD",   "resolution_m": 0.35, "sensor": "Optical Military",    "sensor_category": "Military", "altitude_km": 480, "max_tilt_deg": 30},
    {"norad": "49438", "name": "CSO-3",          "country": "France",      "operator": "DGA/French MoD",   "resolution_m": 0.35, "sensor": "Optical Military",    "sensor_category": "Military", "altitude_km": 800, "max_tilt_deg": 30},
    # Italy — COSMO-SkyMed military SAR
    {"norad": "31598", "name": "COSMO-SKYMED 1","country": "Italy",       "operator": "ASI/Italian MoD",  "resolution_m": 1.00, "sensor": "SAR X-band Military", "sensor_category": "Military", "altitude_km": 619, "max_tilt_deg": 50},
    {"norad": "32376", "name": "COSMO-SKYMED 2","country": "Italy",       "operator": "ASI/Italian MoD",  "resolution_m": 1.00, "sensor": "SAR X-band Military", "sensor_category": "Military", "altitude_km": 619, "max_tilt_deg": 50},
    {"norad": "33053", "name": "COSMO-SKYMED 3","country": "Italy",       "operator": "ASI/Italian MoD",  "resolution_m": 1.00, "sensor": "SAR X-band Military", "sensor_category": "Military", "altitude_km": 619, "max_tilt_deg": 50},
    {"norad": "36599", "name": "COSMO-SKYMED 4","country": "Italy",       "operator": "ASI/Italian MoD",  "resolution_m": 1.00, "sensor": "SAR X-band Military", "sensor_category": "Military", "altitude_km": 619, "max_tilt_deg": 50},
    {"norad": "45026", "name": "CSG-1",          "country": "Italy",       "operator": "ASI/Italian MoD",  "resolution_m": 0.40, "sensor": "SAR X-band Military", "sensor_category": "Military", "altitude_km": 619, "max_tilt_deg": 60},
    {"norad": "49719", "name": "CSG-2",          "country": "Italy",       "operator": "ASI/Italian MoD",  "resolution_m": 0.40, "sensor": "SAR X-band Military", "sensor_category": "Military", "altitude_km": 619, "max_tilt_deg": 60},
    # Germany — SAR
    {"norad": "31698", "name": "TERRASAR-X",    "country": "Germany",     "operator": "DLR/Airbus",       "resolution_m": 0.25, "sensor": "SAR X-band",          "sensor_category": "SAR",      "altitude_km": 514, "max_tilt_deg": 55},
    {"norad": "36605", "name": "TANDEM-X",      "country": "Germany",     "operator": "DLR/Airbus",       "resolution_m": 0.25, "sensor": "SAR X-band",          "sensor_category": "SAR",      "altitude_km": 514, "max_tilt_deg": 55},
    # South Korea
    {"norad": "38338", "name": "KOMPSAT-3",     "country": "South Korea", "operator": "KARI",             "resolution_m": 0.70, "sensor": "Panchromatic",        "sensor_category": "Optical",  "altitude_km": 685, "max_tilt_deg": 30},
    {"norad": "40536", "name": "KOMPSAT-3A",    "country": "South Korea", "operator": "KARI",             "resolution_m": 0.55, "sensor": "Panchromatic",        "sensor_category": "Optical",  "altitude_km": 528, "max_tilt_deg": 30},
    {"norad": "39227", "name": "KOMPSAT-5",     "country": "South Korea", "operator": "KARI",             "resolution_m": 1.00, "sensor": "SAR X-band",          "sensor_category": "SAR",      "altitude_km": 550, "max_tilt_deg": 55},
    # China
    {"norad": "40118", "name": "GAOFEN-2",      "country": "China",       "operator": "CNSA",             "resolution_m": 0.80, "sensor": "Panchromatic",        "sensor_category": "Optical",  "altitude_km": 631, "max_tilt_deg": 35},
    {"norad": "44703", "name": "GAOFEN-7",      "country": "China",       "operator": "CNSA",             "resolution_m": 0.65, "sensor": "Panchromatic",        "sensor_category": "Optical",  "altitude_km": 506, "max_tilt_deg": 25},
    {"norad": "43585", "name": "GAOFEN-11",     "country": "China",       "operator": "CNSA",             "resolution_m": 0.10, "sensor": "Panchromatic",        "sensor_category": "Optical",  "altitude_km": 695, "max_tilt_deg": 35},
    {"norad": "41384", "name": "GAOFEN-3",      "country": "China",       "operator": "CNSA",             "resolution_m": 1.00, "sensor": "SAR C-band",          "sensor_category": "SAR",      "altitude_km": 755, "max_tilt_deg": 50},
    # Spain
    {"norad": "40013", "name": "DEIMOS-2",      "country": "Spain",       "operator": "Deimos Imaging",   "resolution_m": 0.75, "sensor": "Panchromatic",        "sensor_category": "Optical",  "altitude_km": 620, "max_tilt_deg": 30},
    {"norad": "43215", "name": "PAZ",            "country": "Spain",       "operator": "Hisdesat",         "resolution_m": 0.25, "sensor": "SAR X-band",          "sensor_category": "SAR",      "altitude_km": 514, "max_tilt_deg": 55},
    # ESA — Sentinel-1 SAR
    {"norad": "39634", "name": "SENTINEL-1A",   "country": "ESA",         "operator": "ESA",              "resolution_m": 5.00, "sensor": "SAR C-band",          "sensor_category": "SAR",      "altitude_km": 693, "max_tilt_deg": 46},
    # Israel — Military SAR
    {"norad": "32273", "name": "TECSAR",         "country": "Israel",      "operator": "IAI/Israeli MoD",  "resolution_m": 0.18, "sensor": "SAR X-band Military", "sensor_category": "Military", "altitude_km": 580, "max_tilt_deg": 50},
    # Japan — SAR
    {"norad": "39769", "name": "ALOS-2",         "country": "Japan",       "operator": "JAXA",             "resolution_m": 3.00, "sensor": "SAR L-band",          "sensor_category": "SAR",      "altitude_km": 628, "max_tilt_deg": 60},
]

# Pre-compute the tilt standoff radius for each satellite once at import.
# Standoff = altitude * tan(max_tilt). This is the flat-earth approximation
# which is accurate to within a few percent for LEO altitudes <= 800 km and
# tilt angles <= 60 deg; spherical-earth correction would add < 5 km here.
def _annotate_hires_eo_with_standoff():
    for s in HIRES_EO_SATS:
        alt = s.get("altitude_km", 0)
        tilt = s.get("max_tilt_deg", 0)
        s["tilt_standoff_km"] = round(alt * math.tan(math.radians(tilt)), 1)
_annotate_hires_eo_with_standoff()
_HIRES_EO_BY_NORAD = {s["norad"]: s for s in HIRES_EO_SATS}


# ── Pakistan strategic-site catalog (FEAT-004) ──────────────────────────────
# Import from the Satellite_Tracker sibling module so both the Tk app and
# this backend share one source of truth for the publicly-known military /
# capital / nuclear / port facilities used in targeting analysis.
import os as _os
import sys as _sys
_SAT_DIR = _os.path.normpath(_os.path.join(
    _os.path.dirname(__file__), "..", "..", "..", "Satellite_Tracker"))
if _SAT_DIR not in _sys.path:
    _sys.path.insert(0, _SAT_DIR)
try:
    from pakistan_strategic_sites import STRATEGIC_SITES, haversine_km
    _STRATEGIC_SITES_OK = True
except ImportError:
    STRATEGIC_SITES = []
    _STRATEGIC_SITES_OK = False
    def haversine_km(a, b, c, d): return 1e9


def _instant_targets(lat: float, lon: float,
                     standoff_km: float | None) -> list[dict]:
    """Snapshot version of strategic-site targeting: which catalog sites
    are within the satellite's standoff_km of THIS sub-point right now.
    Used by the live /api/positions endpoint (the forecast does the same
    over the full pass arc, not just instant).
    """
    if not standoff_km or standoff_km <= 0:
        return []
    out: list[dict] = []
    for s in STRATEGIC_SITES:
        d = haversine_km(lat, lon, s["lat"], s["lon"])
        if d <= standoff_km:
            out.append({
                "name":        s["name"],
                "city":        s["city"],
                "tier":        s["tier"],
                "category":    s["category"],
                "min_dist_km": round(d, 1),
            })
    out.sort(key=lambda x: x["min_dist_km"])
    return out

# TLE cache for individual NORAD fetches: norad -> {fetched_at, line1, line2}
_hires_eo_tle_cache: dict[str, dict] = {}
_HIRES_EO_TLE_TTL = 2 * 3600   # 2 h — matches category cache

# Bulk-mirror cache: a single fetch of the active.tle file (~15k sats) on the
# GitHub mirror covers nearly every curated NORAD. Per-NORAD CelesTrak
# requests get rate-limited fast (37 parallel requests trip it instantly),
# so the mirror is the primary path; CelesTrak is the fallback for any
# NORAD missing from the mirror.
_HIRES_EO_NORADS: set[str] = {s["norad"] for s in HIRES_EO_SATS}


async def _populate_hires_eo_cache_from_mirror() -> int:
    """Fetch the bulk active TLE from the mirror, extract our 37 curated NORADs.
    Returns the number of entries populated into the per-NORAD cache."""
    try:
        text = await get_tle_text(Category.active)
    except Exception:
        return 0
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    populated = 0
    now = time.time()
    for i in range(0, len(lines) - 2):
        l1, l2 = lines[i + 1], lines[i + 2]
        if not l1.startswith("1 ") or not l2.startswith("2 "):
            continue
        # TLE line 1: "1 NNNNNU ..." — NORAD is chars 2-7, strip non-digits
        norad_raw = l1[2:7].strip()
        norad = norad_raw.lstrip("0") or "0"
        if norad in _HIRES_EO_NORADS:
            _hires_eo_tle_cache[norad] = {
                "fetched_at": now,
                "line1": l1,
                "line2": l2,
            }
            populated += 1
    return populated


async def _fetch_hires_eo_tle(norad: str) -> tuple[str, str] | None:
    """Fetch TLE for a single NORAD ID with bulk-mirror primary, per-NORAD
    CelesTrak fallback, both with 2-h cache."""
    now = time.time()
    cached = _hires_eo_tle_cache.get(norad)
    if cached and now - cached["fetched_at"] < _HIRES_EO_TLE_TTL:
        return cached["line1"], cached["line2"]

    # Cache miss — try to repopulate from the bulk mirror once.
    # Subsequent NORADs in the same call wave will hit the warm cache.
    if not _hires_eo_tle_cache or all(
        now - e["fetched_at"] >= _HIRES_EO_TLE_TTL for e in _hires_eo_tle_cache.values()
    ):
        await _populate_hires_eo_cache_from_mirror()
        cached = _hires_eo_tle_cache.get(norad)
        if cached:
            return cached["line1"], cached["line2"]

    # Fallback: per-NORAD CelesTrak. May be rate-limited.
    url = f"https://celestrak.org/NORAD/elements/gp.php?CATNR={norad}&FORMAT=tle"
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            r = await client.get(url, headers={"User-Agent": "pakistan-orbit-tracker/1.0"})
            r.raise_for_status()
            lines = [l.strip() for l in r.text.splitlines() if l.strip()]
            if len(lines) >= 3 and lines[1].startswith("1 ") and lines[2].startswith("2 "):
                _hires_eo_tle_cache[norad] = {
                    "fetched_at": now,
                    "line1": lines[1],
                    "line2": lines[2],
                }
                return lines[1], lines[2]
    except Exception:
        if cached:
            return cached["line1"], cached["line2"]
    return None


# Pakistan bounding box
_PK_LAT_MIN, _PK_LAT_MAX = 23.5, 37.5
_PK_LON_MIN, _PK_LON_MAX = 60.5, 77.5
# 300 km ≈ 2.7° lat, 3.1° lon at ~30°N
_TILT_LAT_BUF = 2.7
_TILT_LON_BUF = 3.1


def _pk_zone(lat: float, lon: float) -> str:
    """
    Return zone string for a satellite ground point:
      'overhead'   — sub-satellite point inside Pakistan box
      'tilt_range' — within 300 km buffer of Pakistan border
      'outside'    — beyond tilt range
    """
    if (_PK_LAT_MIN <= lat <= _PK_LAT_MAX and
            _PK_LON_MIN <= lon <= _PK_LON_MAX):
        return "overhead"
    if (_PK_LAT_MIN - _TILT_LAT_BUF <= lat <= _PK_LAT_MAX + _TILT_LAT_BUF and
            _PK_LON_MIN - _TILT_LON_BUF <= lon <= _PK_LON_MAX + _TILT_LON_BUF):
        return "tilt_range"
    return "outside"


@app.get("/api/positions/hires-eo")
async def get_hires_eo_positions():
    """Return live positions for all curated Imagery & SAR surveillance satellites."""
    import asyncio
    async def _pos(sat: dict):
        result = await _fetch_hires_eo_tle(sat["norad"])
        if result is None:
            return None
        l1, l2 = result
        p = propagate_now(sat["name"], l1, l2)
        if p is None:
            return None
        zone = _pk_zone(p["lat"], p["lon"])
        return {
            **p,
            "norad":             sat["norad"],
            "country":           sat["country"],
            "operator":          sat["operator"],
            "resolution_m":      sat["resolution_m"],
            "sensor":            sat.get("sensor", "Unknown"),
            "sensor_category":   sat.get("sensor_category", "Optical"),
            "altitude_km":       sat.get("altitude_km"),
            "max_tilt_deg":      sat.get("max_tilt_deg"),
            "tilt_standoff_km":  sat.get("tilt_standoff_km"),
            "over_pakistan":     zone == "overhead",
            "tilt_range":        zone == "tilt_range",
            "zone":              zone,
            # FEAT-004: which Pakistan strategic sites are within this sat's
            # standoff radius RIGHT NOW (instant snapshot — different from
            # the forecast's per-arc targeting). Empty when nothing in reach.
            "targeted_sites":    _instant_targets(
                p["lat"], p["lon"], sat.get("tilt_standoff_km")),
        }

    results = await asyncio.gather(*[_pos(s) for s in HIRES_EO_SATS])
    positions = [r for r in results if r is not None]
    return {
        "category":   "hires-eo",
        "count":      len(positions),
        "timestamp":  datetime.now(timezone.utc).isoformat(),
        "satellites": len(HIRES_EO_SATS),
        "positions":  positions,
    }


@app.get("/api/hires-eo/catalog")
def get_hires_eo_catalog():
    """Return the curated ≤1m satellite catalog with metadata."""
    return {"satellites": HIRES_EO_SATS, "count": len(HIRES_EO_SATS)}


@app.get("/api/strategic-sites")
def get_strategic_sites():
    """Return the Pakistan strategic-site catalog (FEAT-004) — public-domain
    coordinates used by the targeting analysis. Frontend can render these
    as pins on the Leaflet map; document generators consume the same list."""
    return {
        "sites":  STRATEGIC_SITES,
        "count":  len(STRATEGIC_SITES),
        "loaded": _STRATEGIC_SITES_OK,
        "source": "public open-source (Wikipedia / OSINT) — no classified data",
    }


@app.get("/api/satellite/{norad}")
async def get_satellite_metadata(norad: str):
    """Return full metadata for a satellite by NORAD ID: country, operator, purpose, source/destination."""
    catalog = await get_satnogs_catalog()

    # Try to find the name from any cached TLE
    name = norad
    for cached in tle_cache.values():
        lines = [l.strip() for l in cached["text"].splitlines() if l.strip()]
        for i in range(0, len(lines)-2, 3):
            if lines[i+1][2:7].strip() == norad:
                name = lines[i]
                break

    return build_metadata(norad, name, catalog)


@app.get("/api/metadata")
async def get_bulk_metadata(category: Category = Query(...)):
    """Return metadata for all satellites in a category (bulk, one call)."""
    catalog = await get_satnogs_catalog()
    text = await get_tle_text(category)
    records = parse_records(text, CATEGORY_META[category]["max"])
    result = {}
    for name, l1, _ in records:
        norad = l1[2:7].strip()
        result[name] = build_metadata(norad, name, catalog)
    return result


# ── HiRes EO 15-day forecast ──────────────────────────────────────────────────
# The forecast JSON is produced by Satellite_Tracker/forecast_15day.py and
# saved to that module's directory. We read it directly off disk so this
# backend stays decoupled from the tracker module.
import json
import os
from pathlib import Path

# Resolve the forecast file path relative to this backend file:
#   backend/main.py -> ../../../Satellite_Tracker/forecast_15day.json
_FORECAST_PATH = (
    Path(__file__).resolve().parents[3]
    / "Satellite_Tracker" / "forecast_15day.json"
)


def _load_forecast() -> dict | None:
    if not _FORECAST_PATH.is_file():
        return None
    try:
        with _FORECAST_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


@app.get("/api/forecast/health")
def forecast_health():
    """
    Lightweight readiness probe for the forecast pipeline.
    Returns whether a forecast exists and whether it is stale (> 36 h old).
    """
    fc = _load_forecast()
    if fc is None:
        return {"ok": False, "reason": "no forecast generated yet"}
    generated_at = fc.get("generated_at")
    stale = False
    if generated_at:
        try:
            gen_dt = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
            age_hours = (datetime.now(timezone.utc) - gen_dt).total_seconds() / 3600
            stale = age_hours > 36
        except ValueError:
            pass
    return {
        "ok": True,
        "generated_at": generated_at,
        "start_date": fc.get("start_date"),
        "end_date": fc.get("end_date"),
        "satellite_count": fc.get("satellite_count"),
        "indian_satellite_count": fc.get("indian_satellite_count"),
        "stale": stale,
    }


@app.get("/api/forecast")
def get_forecast():
    """
    Return the full 15-day HiRes EO surveillance forecast.

    Shape:
      generated_at, start_date, end_date, satellite_count,
      indian_satellite_count, propagator, days[].crossings,
      days[].observation_windows, days[].blind_windows, days[].totals
    """
    fc = _load_forecast()
    if fc is None:
        raise HTTPException(
            status_code=404,
            detail="No forecast available. Run Satellite_Tracker/run_daily.py.",
        )
    return fc


@app.get("/api/forecast/day/{date}")
def get_forecast_day(date: str):
    """Return a single day's forecast slice (date format YYYY-MM-DD)."""
    fc = _load_forecast()
    if fc is None:
        raise HTTPException(404, detail="No forecast available.")
    for day in fc.get("days", []):
        if day.get("date") == date:
            return day
    raise HTTPException(
        404, detail=f"Date {date} not in forecast window "
                    f"{fc.get('start_date')}..{fc.get('end_date')}",
    )


@app.get("/api/forecast/blind-windows")
def get_blind_windows():
    """Aggregate every blind window across the forecast window, sorted longest-first."""
    fc = _load_forecast()
    if fc is None:
        raise HTTPException(404, detail="No forecast available.")
    out = []
    for day in fc.get("days", []):
        for b in day.get("blind_windows", []):
            out.append({"date": day["date"], **b})
    out.sort(key=lambda b: -b["duration_min"])
    return {
        "generated_at": fc.get("generated_at"),
        "count": len(out),
        "blind_windows": out,
    }


_CHANGES_PATH = (
    Path(__file__).resolve().parents[3]
    / "Satellite_Tracker" / "forecast_changes.json"
)


@app.get("/api/forecast/changes")
def get_forecast_changes():
    """
    Return the latest 'what changed vs the previous daily run' diff.
    Each day-bucket has new_passes, removed_passes, shifted_passes
    (entry-time shift in minutes), plus blind_delta_min.
    """
    if not _CHANGES_PATH.is_file():
        raise HTTPException(404,
            detail="No change record yet — run Satellite_Tracker/run_daily.py at least twice.")
    try:
        with _CHANGES_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        raise HTTPException(500, detail="forecast_changes.json unreadable.")
