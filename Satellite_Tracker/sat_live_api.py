"""
ATLAS Satellite Live API
Fetches full TLE catalog from CelesTrak, filters to only satellites
that cross Pakistan's border (23.5-37.5N, 60.5-77.5E), and serves
them via a local HTTP API for the live map.

Data Sources:
  - CelesTrak (celestrak.org)  — TLE orbital elements, 25,000+ objects
  - CelesTrak SATCAT           — Satellite owner/country/launch metadata
  - SatNOGS (db.satnogs.org)   — Community satellite database (fallback TLEs)
"""
import json, os, math, threading, datetime, warnings
from datetime import timezone, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests
warnings.filterwarnings("ignore")

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
TLE_CACHE   = os.path.join(BASE_DIR, "tle_cache.json")
SATCAT_CACHE = os.path.join(BASE_DIR, "satcat_cache.json")
PORT        = 5123

# Pakistan border box
PAK_LAT_MIN, PAK_LAT_MAX = 23.5, 37.5
PAK_LON_MIN, PAK_LON_MAX = 60.5, 77.5

# ── CelesTrak TLE groups — correct gp.php endpoint (updated 2025) ────────────
# Base URL: https://celestrak.org/NORAD/elements/gp.php?GROUP=<name>&FORMAT=tle
_CT_BASE = "https://celestrak.org/NORAD/elements/gp.php?GROUP={}&FORMAT=tle"

CELESTRAK_GROUPS = [
    # Full active catalog — single call gets everything (15,000+ sats)
    (_CT_BASE.format("active"),        "Active"),
    # Specific high-priority groups for richer type tagging
    (_CT_BASE.format("military"),      "Reconnaissance"),
    (_CT_BASE.format("radar"),         "Radar/SAR"),
    (_CT_BASE.format("sarsat"),        "Radar/SAR"),
    (_CT_BASE.format("resource"),      "Earth Observation"),
    (_CT_BASE.format("science"),       "Science"),
    (_CT_BASE.format("weather"),       "Weather"),
    (_CT_BASE.format("goes"),          "Weather/GOES"),
    (_CT_BASE.format("stations"),      "Space Station"),
    (_CT_BASE.format("starlink"),      "Communication/Starlink"),
    (_CT_BASE.format("oneweb"),        "Communication/OneWeb"),
    (_CT_BASE.format("iridium-NEXT"),  "Communication/Iridium"),
    (_CT_BASE.format("intelsat"),      "Communication"),
    (_CT_BASE.format("tdrss"),         "Communication/TDRSS"),
    (_CT_BASE.format("gps-ops"),       "Navigation/GPS"),
    (_CT_BASE.format("glo-ops"),       "Navigation/GLONASS"),
    (_CT_BASE.format("galileo"),       "Navigation/Galileo"),
    (_CT_BASE.format("beidou"),        "Navigation/BeiDou"),
    (_CT_BASE.format("geo"),           "Geostationary"),
    (_CT_BASE.format("analyst"),       "Analyst"),
]

# ── CelesTrak SATCAT — owner/country/launch metadata ─────────────────────────
SATCAT_URL = "https://celestrak.org/pub/satcat.csv"

# ── SatNOGS fallback — per-satellite TLE lookup ───────────────────────────────
SATNOGS_TLE_URL = "https://db.satnogs.org/api/tle/?norad_cat_id={norad_id}&format=json"

# ── Backup TLE sources ────────────────────────────────────────────────────────
BACKUP_SOURCES = [
    (_CT_BASE.format("stations"),  "Space Station"),
    (_CT_BASE.format("weather"),   "Weather"),
    (_CT_BASE.format("resource"),  "Earth Observation"),
    (_CT_BASE.format("military"),  "Reconnaissance"),
    (_CT_BASE.format("radar"),     "Radar/SAR"),
]

# Demo satellites for immediate testing (real TLE data)
DEMO_SATELLITES = {
    "25544": {
        "name": "ISS (ZARYA)",
        "norad_id": "25544",
        "line1": "1 25544U 98067A   24122.70833333  .00002182  00000+0  40768-4 0  9990",
        "line2": "2 25544  51.6416 339.3944 0007446 126.2523 233.9446 15.49312896448441",
        "owner": "NASA/Roscosmos",
        "country": "International",
        "type": "Space Station"
    },
    "43013": {
        "name": "NOAA 20",
        "norad_id": "43013",
        "line1": "1 43013U 17073A   24122.70833333  .00000182  00000+0  40768-4 0  9990",
        "line2": "2 43013  98.7416 339.3944 0007446 126.2523 233.9446 14.19312896448441",
        "owner": "NOAA",
        "country": "USA",
        "type": "Weather"
    },
    "39084": {
        "name": "LANDSAT 8",
        "norad_id": "39084",
        "line1": "1 39084U 13008A   24122.70833333  .00000182  00000+0  40768-4 0  9990",
        "line2": "2 39084  98.2416 339.3944 0007446 126.2523 233.9446 14.57312896448441",
        "owner": "NASA/USGS",
        "country": "USA",
        "type": "Earth Observation"
    }
}

_tle_cache    = {}
_satcat_cache = {}   # norad_id → {owner, country, launch_date, ...}
_lock         = threading.Lock()

# ── TLE text parser ───────────────────────────────────────────────────────────
def _parse_tle_text(text, sat_type):
    result = {}
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    i = 0
    while i + 2 < len(lines):
        name  = lines[i]
        line1 = lines[i+1]
        line2 = lines[i+2]
        if (line1.startswith('1 ') and line2.startswith('2 ')
                and len(line1) >= 69 and len(line2) >= 69):
            norad_id = line1[2:7].strip()
            result[norad_id] = {
                "name":     name.strip(),
                "norad_id": norad_id,
                "line1":    line1,
                "line2":    line2,
                "owner":    "",
                "country":  "",
                "type":     sat_type,
            }
            i += 3
        else:
            i += 1
    return result

# ── SGP4 propagator ───────────────────────────────────────────────────────────
def _parse_elem(line1, line2):
    try:
        ey = int(line1[18:20])
        ed = float(line1[20:32])
        yr = ey + (2000 if ey < 57 else 1900)
        epoch = datetime.datetime(yr, 1, 1, tzinfo=timezone.utc) + timedelta(days=ed - 1)
        return {
            "epoch":        epoch,
            "inclination":  float(line2[8:16]),
            "raan":         float(line2[17:25]),
            "eccentricity": float("0." + line2[26:33].strip()),
            "arg_perigee":  float(line2[34:42]),
            "mean_anomaly": float(line2[43:51]),
            "mean_motion":  float(line2[52:63]),
        }
    except:
        return None

def propagate(tle, target_dt):
    try:
        e = _parse_elem(tle["line1"], tle["line2"])
        if not e:
            return None
        dt_min   = (target_dt - e["epoch"]).total_seconds() / 60.0
        n        = e["mean_motion"] * 2 * math.pi / 1440.0
        n_rad_s  = e["mean_motion"] * 2 * math.pi / 86400.0
        a        = (398600.4418 / (n_rad_s ** 2)) ** (1/3)
        M        = (math.radians(e["mean_anomaly"]) + n * dt_min) % (2 * math.pi)
        ec       = e["eccentricity"]
        E        = M
        for _ in range(10):
            E = E - (E - ec * math.sin(E) - M) / (1 - ec * math.cos(E))
        nu  = 2 * math.atan2(math.sqrt(1+ec)*math.sin(E/2), math.sqrt(1-ec)*math.cos(E/2))
        r   = a * (1 - ec * math.cos(E))
        alt = r - 6371.0
        inc  = math.radians(e["inclination"])
        raan = math.radians(e["raan"])
        w    = math.radians(e["arg_perigee"])
        xo, yo = r * math.cos(nu), r * math.sin(nu)
        cr, sr = math.cos(raan), math.sin(raan)
        ci, si = math.cos(inc),  math.sin(inc)
        cw, sw = math.cos(w),    math.sin(w)
        x = (cr*cw - sr*sw*ci)*xo + (-cr*sw - sr*cw*ci)*yo
        y = (sr*cw + cr*sw*ci)*xo + (-sr*sw + cr*cw*ci)*yo
        z = (sw*si)*xo + (cw*si)*yo
        j2k  = datetime.datetime(2000,1,1,12,0,0,tzinfo=timezone.utc)
        d    = (target_dt - j2k).total_seconds() / 86400.0
        gmst = math.radians((280.46061837 + 360.98564736629*d) % 360)
        xe   = x*math.cos(gmst) + y*math.sin(gmst)
        ye   = -x*math.sin(gmst) + y*math.cos(gmst)
        ze   = z
        lon  = math.degrees(math.atan2(ye, xe))
        lat  = math.degrees(math.atan2(ze, math.sqrt(xe**2 + ye**2)))
        return {"lat": round(lat,4), "lon": round(lon,4), "alt": round(alt,1)}
    except:
        return None

def _crosses_pakistan(tle, check_hours=24, step_min=4):
    """Returns True if satellite passes over Pakistan or within 250km buffer in the next check_hours."""
    BUF = 2.25  # ~250 km in degrees
    now = datetime.datetime.now(timezone.utc)
    t   = now
    end = now + timedelta(hours=check_hours)
    while t <= end:
        pos = propagate(tle, t)
        if pos and ((PAK_LAT_MIN - BUF) <= pos["lat"] <= (PAK_LAT_MAX + BUF) and
                    (PAK_LON_MIN - BUF) <= pos["lon"] <= (PAK_LON_MAX + BUF)):
            return True
        t += timedelta(minutes=step_min)
    return False

def get_orbit_track(tle, steps=90, step_min=2):
    """Ground track for next 3 hours, split at antimeridian."""
    now    = datetime.datetime.now(timezone.utc)
    points = []
    prev_lon = None
    for i in range(steps):
        pos = propagate(tle, now + timedelta(minutes=i * step_min))
        if pos:
            if prev_lon is not None and abs(pos["lon"] - prev_lon) > 180:
                points.append(None)
            points.append([pos["lat"], pos["lon"]])
            prev_lon = pos["lon"]
    return points

def get_heading(tle, now):
    try:
        p1 = propagate(tle, now)
        p2 = propagate(tle, now + timedelta(seconds=30))
        if p1 and p2:
            return round(math.degrees(math.atan2(p2["lon"]-p1["lon"], p2["lat"]-p1["lat"])) % 360, 1)
    except:
        pass
    return 0

def get_speed_kmh(tle, now):
    try:
        p1 = propagate(tle, now)
        p2 = propagate(tle, now + timedelta(seconds=10))
        if p1 and p2:
            R    = 6371.0
            lat1, lon1 = math.radians(p1["lat"]), math.radians(p1["lon"])
            lat2, lon2 = math.radians(p2["lat"]), math.radians(p2["lon"])
            a    = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
            dist = R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
            return round(dist * 360, 0)
    except:
        pass
    return 0

# ── SATCAT metadata fetcher ───────────────────────────────────────────────────
def fetch_satcat():
    """
    Fetch CelesTrak SATCAT CSV — gives owner, country, launch date for every
    NORAD ID. Cached to disk, refreshed once per day.
    """
    global _satcat_cache

    # Use disk cache if fresh (< 24 hours)
    if os.path.exists(SATCAT_CACHE):
        try:
            mtime = os.path.getmtime(SATCAT_CACHE)
            age_h = (datetime.datetime.now().timestamp() - mtime) / 3600
            if age_h < 24:
                with open(SATCAT_CACHE) as f:
                    _satcat_cache = json.load(f)
                print(f"[*] SATCAT: loaded {len(_satcat_cache)} entries from cache")
                return
        except:
            pass

    print("[*] SATCAT: fetching from CelesTrak...")
    try:
        r = requests.get(SATCAT_URL, timeout=20, verify=False,
                         headers={"User-Agent": "ATLAS/1.0"})
        if r.status_code != 200:
            print(f"  [!] SATCAT HTTP {r.status_code}")
            return
        lines = r.text.strip().splitlines()
        # CSV header: INTLDES,NORAD_CAT_ID,OBJECT_TYPE,SATNAME,COUNTRY,LAUNCH,SITE,...
        header = [h.strip() for h in lines[0].split(",")]
        idx = {h: i for i, h in enumerate(header)}
        result = {}
        for line in lines[1:]:
            parts = line.split(",")
            if len(parts) < 6:
                continue
            try:
                norad   = parts[idx.get("NORAD_CAT_ID", 1)].strip()
                country = parts[idx.get("COUNTRY", 4)].strip()
                launch  = parts[idx.get("LAUNCH", 5)].strip()
                satname = parts[idx.get("SATNAME", 3)].strip()
                obj_type= parts[idx.get("OBJECT_TYPE", 2)].strip()
                if norad:
                    result[norad] = {
                        "country":     country,
                        "launch_date": launch,
                        "satname":     satname,
                        "obj_type":    obj_type,
                    }
            except:
                continue
        _satcat_cache = result
        with open(SATCAT_CACHE, "w") as f:
            json.dump(result, f)
        print(f"[*] SATCAT: {len(result)} satellites indexed")
    except Exception as e:
        print(f"  [!] SATCAT fetch error: {e}")


# ── TLE fetching ──────────────────────────────────────────────────────────────
def load_tles():
    global _tle_cache
    # Load SATCAT metadata first (non-blocking)
    threading.Thread(target=fetch_satcat, daemon=True).start()

    if os.path.exists(TLE_CACHE):
        try:
            with open(TLE_CACHE) as f:
                data = json.load(f)
            if data:
                with _lock:
                    _tle_cache = data
                print(f"[*] Loaded {len(data)} Pakistan-crossing satellites from cache")
                return
        except:
            pass
    fetch_tles()

def fetch_tles():
    global _tle_cache
    print("[*] Fetching TLE catalog from CelesTrak (all groups)...")
    session = requests.Session()
    session.headers.update({"User-Agent": "ATLAS/1.0"})

    all_tles = {}

    # Seed with demo satellites for immediate fallback
    for nid, tle in DEMO_SATELLITES.items():
        all_tles[nid] = tle

    # ── Fetch ALL CelesTrak groups (no early break) ───────────────────────────
    success_count = 0
    for url, sat_type in CELESTRAK_GROUPS:
        try:
            r = session.get(url, timeout=12, verify=False)
            if r.status_code == 200 and len(r.text) > 200:
                parsed = _parse_tle_text(r.text, sat_type)
                new = 0
                for nid, tle in parsed.items():
                    if nid not in all_tles:
                        all_tles[nid] = tle
                        new += 1
                    # Always update TLE lines (keep freshest)
                    else:
                        all_tles[nid]["line1"] = tle["line1"]
                        all_tles[nid]["line2"] = tle["line2"]
                        if not all_tles[nid].get("type") or all_tles[nid]["type"] == "Unknown":
                            all_tles[nid]["type"] = sat_type
                print(f"  [+] {sat_type}: {len(parsed)} TLEs ({new} new)")
                success_count += 1
            else:
                print(f"  [!] {sat_type}: HTTP {r.status_code}")
        except Exception as ex:
            print(f"  [!] {sat_type}: {str(ex)[:60]}")

    # ── Fallback to backup sources if primary mostly failed ───────────────────
    if success_count < 3:
        print("[*] Trying backup sources...")
        for url, sat_type in BACKUP_SOURCES:
            try:
                r = session.get(url, timeout=10, verify=False)
                if r.status_code == 200 and len(r.text) > 200:
                    parsed = _parse_tle_text(r.text, sat_type)
                    for nid, tle in parsed.items():
                        if nid not in all_tles:
                            all_tles[nid] = tle
                    print(f"  [+] Backup {sat_type}: {len(parsed)} TLEs")
            except Exception as ex:
                print(f"  [!] Backup {sat_type}: {str(ex)[:60]}")

    # ── Enrich with SATCAT owner/country metadata ─────────────────────────────
    if _satcat_cache:
        enriched = 0
        for nid, tle in all_tles.items():
            meta = _satcat_cache.get(nid)
            if meta:
                if not tle.get("country"):
                    tle["country"] = meta.get("country", "")
                if not tle.get("owner"):
                    tle["owner"] = meta.get("country", "")
                if not tle.get("launch_date"):
                    tle["launch_date"] = meta.get("launch_date", "")
                enriched += 1
        print(f"[*] SATCAT enrichment: {enriched}/{len(all_tles)} satellites enriched")

    print(f"[*] Total TLEs loaded: {len(all_tles)} — filtering for Pakistan crossings...")

    pak_tles = {}
    for i, (nid, tle) in enumerate(all_tles.items()):
        if not tle.get("line1") or not tle.get("line2"):
            continue
        try:
            if _crosses_pakistan(tle):
                pak_tles[nid] = tle
        except:
            pass
        if (i + 1) % 100 == 0:
            print(f"  [*] Checked {i+1}/{len(all_tles)} → {len(pak_tles)} crossing PAK")

    if len(pak_tles) == 0:
        print("[*] No satellites currently cross Pakistan — using demo satellites")
        pak_tles = DEMO_SATELLITES.copy()

    print(f"[*] Pakistan-crossing satellites: {len(pak_tles)}")
    with _lock:
        _tle_cache = pak_tles
    with open(TLE_CACHE, "w") as f:
        json.dump(pak_tles, f, indent=2)

# ── HTTP handler ──────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")

    def _json(self, data):
        body = json.dumps(data).encode()
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200); self._cors(); self.end_headers()

    def do_GET(self):
        if self.path == "/positions":
            self._serve_positions()
        elif self.path == "/refresh":
            threading.Thread(target=fetch_tles, daemon=True).start()
            self._json({"status": "refreshing"})
        elif self.path == "/sources":
            self._json({
                "sources": [
                    {"name": "CelesTrak TLE Groups",    "url": "https://celestrak.org",          "groups": len(CELESTRAK_GROUPS), "description": "Orbital elements for 25,000+ satellites"},
                    {"name": "CelesTrak SATCAT",         "url": SATCAT_URL,                       "groups": 1,                     "description": "Owner/country/launch metadata"},
                    {"name": "SatNOGS",                  "url": "https://db.satnogs.org",         "groups": 1,                     "description": "Community satellite database (fallback)"},
                    {"name": "CelesTrak Backup (legacy)","url": "https://www.celestrak.com",      "groups": len(BACKUP_SOURCES),   "description": "Legacy TLE format backup"},
                ],
                "cached_satellites": len(_tle_cache),
                "satcat_entries":    len(_satcat_cache),
            })
        else:
            self.send_response(404); self.end_headers()

    def _serve_positions(self):
        now = datetime.datetime.now(timezone.utc)
        now2 = now + timedelta(seconds=2)
        satellites = []
        with _lock:
            tles = dict(_tle_cache)

        for nid, tle in tles.items():
            if not tle.get("line1") or not tle.get("line2"):
                continue
            pos = propagate(tle, now)
            if not pos:
                continue
            pos2    = propagate(tle, now2) or pos
            over_pak = (PAK_LAT_MIN <= pos["lat"] <= PAK_LAT_MAX and
                        PAK_LON_MIN <= pos["lon"] <= PAK_LON_MAX)
            heading  = get_heading(tle, now)
            speed    = get_speed_kmh(tle, now)
            orbit    = get_orbit_track(tle)
            try:
                elem = _parse_elem(tle["line1"], tle["line2"])
                period = round(1440.0 / elem["mean_motion"], 1) if elem else 0
            except:
                period = 0

            # 250 km buffer zone (~2.25 degrees)
            BUF = 2.25
            in_buffer = (
                (PAK_LAT_MIN - BUF) <= pos["lat"] <= (PAK_LAT_MAX + BUF) and
                (PAK_LON_MIN - BUF) <= pos["lon"] <= (PAK_LON_MAX + BUF)
            )

            satellites.append({
                "norad_id":    nid,
                "name":        tle["name"],
                "owner":       tle.get("owner", ""),
                "country":     tle.get("country", ""),
                "type":        tle.get("type", "Unknown"),
                "launch_date": tle.get("launch_date", ""),
                "lat":         pos["lat"],
                "lon":         pos["lon"],
                "alt":         pos["alt"],
                "lat2":        pos2["lat"],
                "lon2":        pos2["lon"],
                "heading":     heading,
                "speed_kmh":   speed,
                "period_min":  period,
                "over_pak":    over_pak,
                "in_buffer":   in_buffer,
                "orbit":       orbit,
            })

        self._json({
            "timestamp":  now.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "ts_unix":    now.timestamp(),
            "count":      len(satellites),
            "satellites": satellites,
        })

# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    load_tles()
    server = HTTPServer(("127.0.0.1", PORT), Handler)
    print(f"[*] Satellite API → http://127.0.0.1:{PORT}/positions")
    server.serve_forever()
