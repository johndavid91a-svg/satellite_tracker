"""
ATLAS Pakistan Border Satellite Tracker
Tracks only satellites that cross Pakistani airspace with anomaly detection
"""
import os, json, sys, time, math, requests, datetime
from datetime import timezone, timedelta
from collections import Counter

# ── Pakistan Border Box ──────────────────────────────────────────────────────
PAK_LAT_MIN, PAK_LAT_MAX = 23.5, 37.5
PAK_LON_MIN, PAK_LON_MAX = 60.5, 77.5

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOCS_DIR = os.path.join(BASE_DIR, "documents")
HISTORY_FILE = os.path.join(BASE_DIR, "satellite_history.json")
ANOMALY_FILE = os.path.join(BASE_DIR, "anomalies.json")
os.makedirs(DOCS_DIR, exist_ok=True)

# ── Curated Satellite List — sourced from hires_eo_satellites.py ─────────────
# Only Earth-observation satellites with panchromatic GSD <= 1 m (commercial +
# state) are tracked. Weather / comms / nav / low-res EO are intentionally
# excluded — see Satellite_Tracker/hires_eo_satellites.py and docs/forecast_15day.md.
sys.path.insert(0, BASE_DIR)
from hires_eo_satellites import HIRES_EO_SATELLITES  # noqa: E402
from celestrak_tle import fetch_hires_eo_tles  # noqa: E402

TRACKED_SATELLITES = [
    (s.norad_id, s.name, s.operator, s.country, s.sensor)
    for s in HIRES_EO_SATELLITES
]


# ── Fetch TLEs from CelesTrak (24h disk cache) ───────────────────────────────
def fetch_tles():
    """
    Refresh the curated TLE set from CelesTrak (cached 24h), then re-shape
    each entry to the legacy {owner, country, type} schema this file expects.
    """
    raw = fetch_hires_eo_tles()
    tles = {}
    for nid, entry in raw.items():
        tles[nid] = {
            "name":     entry["name"],
            "norad_id": nid,
            "line1":    entry["line1"],
            "line2":    entry["line2"],
            "owner":    entry.get("operator", ""),
            "country":  entry.get("country", ""),
            "type":     entry.get("sensor", "Earth Observation"),
        }
    print(f"[*] Loaded {len(tles)} HiRes EO satellites from CelesTrak")
    return tles


# ── Simple SGP4 Propagator ───────────────────────────────────────────────────
def parse_tle(line1, line2):
    try:
        epoch_year = int(line1[18:20])
        epoch_day = float(line1[20:32])
        year = epoch_year + (2000 if epoch_year < 57 else 1900)
        epoch_dt = datetime.datetime(year, 1, 1, tzinfo=timezone.utc) + timedelta(days=epoch_day - 1)
        
        inclination = float(line2[8:16])
        raan = float(line2[17:25])
        ecc_str = "0." + line2[26:33].strip()
        eccentricity = float(ecc_str)
        arg_perigee = float(line2[34:42])
        mean_anomaly = float(line2[43:51])
        mean_motion = float(line2[52:63])
        
        return {
            "epoch": epoch_dt, "inclination": inclination, "raan": raan,
            "eccentricity": eccentricity, "arg_perigee": arg_perigee,
            "mean_anomaly": mean_anomaly, "mean_motion": mean_motion,
        }
    except:
        return None


def propagate(tle_data, target_dt):
    try:
        elem = parse_tle(tle_data["line1"], tle_data["line2"])
        if not elem:
            return None
        
        dt_min = (target_dt - elem["epoch"]).total_seconds() / 60.0
        n = elem["mean_motion"] * 2 * math.pi / 1440.0
        mu = 398600.4418
        n_rad_s = elem["mean_motion"] * 2 * math.pi / 86400.0
        a = (mu / (n_rad_s ** 2)) ** (1/3)
        
        M = math.radians(elem["mean_anomaly"]) + n * dt_min
        M = M % (2 * math.pi)
        
        e = elem["eccentricity"]
        E = M
        for _ in range(10):
            E = E - (E - e * math.sin(E) - M) / (1 - e * math.cos(E))
        
        nu = 2 * math.atan2(math.sqrt(1 + e) * math.sin(E / 2), math.sqrt(1 - e) * math.cos(E / 2))
        r = a * (1 - e * math.cos(E))
        alt = r - 6371.0
        
        inc = math.radians(elem["inclination"])
        raan = math.radians(elem["raan"])
        w = math.radians(elem["arg_perigee"])
        
        x_orb = r * math.cos(nu)
        y_orb = r * math.sin(nu)
        
        cos_raan = math.cos(raan); sin_raan = math.sin(raan)
        cos_inc = math.cos(inc); sin_inc = math.sin(inc)
        cos_w = math.cos(w); sin_w = math.sin(w)
        
        x = (cos_raan * cos_w - sin_raan * sin_w * cos_inc) * x_orb + (-cos_raan * sin_w - sin_raan * cos_w * cos_inc) * y_orb
        y = (sin_raan * cos_w + cos_raan * sin_w * cos_inc) * x_orb + (-sin_raan * sin_w + cos_raan * cos_w * cos_inc) * y_orb
        z = (sin_w * sin_inc) * x_orb + (cos_w * sin_inc) * y_orb
        
        j2000 = datetime.datetime(2000, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        d = (target_dt - j2000).total_seconds() / 86400.0
        gmst = math.radians((280.46061837 + 360.98564736629 * d) % 360)
        
        x_ecef = x * math.cos(gmst) + y * math.sin(gmst)
        y_ecef = -x * math.sin(gmst) + y * math.cos(gmst)
        z_ecef = z
        
        lon = math.degrees(math.atan2(y_ecef, x_ecef))
        lat = math.degrees(math.atan2(z_ecef, math.sqrt(x_ecef**2 + y_ecef**2)))
        
        return {"lat": lat, "lon": lon, "alt": alt}
    except:
        return None


def is_over_pakistan(lat, lon):
    return (PAK_LAT_MIN <= lat <= PAK_LAT_MAX and PAK_LON_MIN <= lon <= PAK_LON_MAX)


# ── Calculate Border Crossings ───────────────────────────────────────────────
def calculate_border_crossings(tles, target_date):
    print(f"[*] Calculating border crossings for {target_date}...")
    
    start_dt = datetime.datetime(target_date.year, target_date.month, target_date.day, 0, 0, 0, tzinfo=timezone.utc)
    end_dt = start_dt + timedelta(days=1)
    
    crossings = []
    step_seconds = 60
    
    for norad_id, tle in tles.items():
        over_pak = False
        entry_time = None
        entry_lat = entry_lon = None
        positions = []
        
        t = start_dt
        while t <= end_dt:
            pos = propagate(tle, t)
            if pos and -90 <= pos["lat"] <= 90 and -180 <= pos["lon"] <= 180:
                if is_over_pakistan(pos["lat"], pos["lon"]):
                    if not over_pak:
                        over_pak = True
                        entry_time = t
                        entry_lat = pos["lat"]
                        entry_lon = pos["lon"]
                    positions.append((t, pos["lat"], pos["lon"], pos["alt"]))
                else:
                    if over_pak:
                        exit_time = t
                        exit_lat = pos["lat"]
                        exit_lon = pos["lon"]
                        duration_min = (exit_time - entry_time).total_seconds() / 60
                        
                        direction = "N/A"
                        if len(positions) >= 2:
                            dlat = positions[-1][1] - positions[0][1]
                            dlon = positions[-1][2] - positions[0][2]
                            if abs(dlat) > abs(dlon):
                                direction = "N→S" if dlat < 0 else "S→N"
                            else:
                                direction = "W→E" if dlon > 0 else "E→W"
                        
                        max_alt = max(p[3] for p in positions) if positions else 0
                        
                        crossings.append({
                            "norad_id": norad_id,
                            "name": tle["name"],
                            "owner": tle["owner"],
                            "country": tle["country"],
                            "type": tle["type"],
                            "entry_time": entry_time.strftime("%Y-%m-%d %H:%M:%S UTC"),
                            "exit_time": exit_time.strftime("%Y-%m-%d %H:%M:%S UTC"),
                            "duration_min": round(duration_min, 1),
                            "entry_lat": round(entry_lat, 2),
                            "entry_lon": round(entry_lon, 2),
                            "exit_lat": round(exit_lat, 2),
                            "exit_lon": round(exit_lon, 2),
                            "max_alt_km": round(max_alt, 1),
                            "direction": direction,
                            "date": str(target_date),
                        })
                        over_pak = False
                        positions = []
            
            t += timedelta(seconds=step_seconds)
    
    crossings.sort(key=lambda x: x["entry_time"])
    
    # Count and highlight Indian satellites
    indian_count = sum(1 for c in crossings if c["country"] == "India")
    if indian_count > 0:
        print(f"[+] Found {len(crossings)} border crossings")
        print(f"[!] 🇮🇳 {indian_count} INDIAN SATELLITE CROSSINGS DETECTED 🔴")
    else:
        print(f"[+] Found {len(crossings)} border crossings")
    
    return crossings


# ── Anomaly Detection ────────────────────────────────────────────────────────
def detect_anomalies(crossings, history):
    anomalies = []
    
    # Build baseline stats per satellite
    baseline = {}
    for date_str, day_data in history.items():
        for crossing in day_data.get("crossings", []):
            nid = crossing["norad_id"]
            if nid not in baseline:
                baseline[nid] = {"durations": [], "count": 0}
            baseline[nid]["durations"].append(crossing["duration_min"])
            baseline[nid]["count"] += 1
    
    # Check today's crossings — deduplicate per satellite (use longest crossing)
    worst_crossing = {}  # norad_id -> crossing with max duration
    for crossing in crossings:
        nid = crossing["norad_id"]
        if nid not in worst_crossing or crossing["duration_min"] > worst_crossing[nid]["duration_min"]:
            worst_crossing[nid] = crossing

    for nid, crossing in worst_crossing.items():
        name = crossing["name"]
        duration = crossing["duration_min"]
        
        if nid in baseline and len(baseline[nid]["durations"]) >= 3:
            avg_duration = sum(baseline[nid]["durations"]) / len(baseline[nid]["durations"])
            
            # Anomaly 1: Duration 50% longer than average
            if duration > avg_duration * 1.5:
                anomalies.append({
                    "type": "LONG_DURATION",
                    "satellite": name,
                    "norad_id": nid,
                    "owner": crossing["owner"],
                    "severity": "HIGH",
                    "details": f"Duration {duration:.1f}min is {((duration/avg_duration-1)*100):.0f}% longer than avg {avg_duration:.1f}min",
                    "crossing": crossing,
                })
    
    # Anomaly 2: Frequency increase
    today_counts = Counter(c["norad_id"] for c in crossings)
    for nid, today_count in today_counts.items():
        if nid in baseline:
            avg_count = baseline[nid]["count"] / len(history)
            if today_count > avg_count * 1.5 and today_count >= 3:
                sat = next((c for c in crossings if c["norad_id"] == nid), None)
                if sat:
                    anomalies.append({
                        "type": "INCREASED_FREQUENCY",
                        "satellite": sat["name"],
                        "norad_id": nid,
                        "owner": sat["owner"],
                        "severity": "MEDIUM",
                        "details": f"{today_count} crossings today vs avg {avg_count:.1f} per day",
                        "crossing": sat,
                    })
    
    return anomalies


# ── Report Generator ─────────────────────────────────────────────────────────
def generate_report(crossings, date_str, history, anomalies):
    try:
        from docx import Document
        from docx.shared import RGBColor, Pt, Inches
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        import matplotlib
        matplotlib.use('Agg')  # Non-interactive backend
        import matplotlib.pyplot as plt
        from matplotlib.patches import Polygon
        import numpy as np
    except ImportError as e:
        print(f"[!] Required library not installed: {e}")
        return None
    
    doc = Document()
    # ── Print-ready A4 page setup ─────────────────────────────────────────────
    from docx.shared import Cm
    section = doc.sections[0]
    section.page_width  = Cm(21.0)
    section.page_height = Cm(29.7)
    section.left_margin   = Cm(2.0)
    section.right_margin  = Cm(2.0)
    section.top_margin    = Cm(2.5)
    section.bottom_margin = Cm(2.5)
    # ─────────────────────────────────────────────────────────────────────────
    now = datetime.datetime.now()
    
    # Filter Indian satellites
    indian_crossings = [c for c in crossings if c["country"] == "India"]
    indian_imagery = [c for c in indian_crossings if "observation" in c["type"].lower() or "radar" in c["type"].lower() or "sar" in c["type"].lower()]
    
    # Time helper — entry_time field is stored as "YYYY-MM-DD HH:MM:SS UTC";
    # operator reads this report in Pakistan, so render all times as PKT (UTC+5).
    def _entry_time_pkt(stamp: str) -> str:
        """Convert 'YYYY-MM-DD HH:MM:SS UTC' to 'HH:MM PKT' (UTC+5h, no DST)."""
        try:
            dt = datetime.datetime.strptime(stamp.replace(" UTC", ""), "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError, AttributeError):
            # Fallback: best-effort split
            return stamp.split()[1] if stamp else "-"
        return (dt + datetime.timedelta(hours=5)).strftime("%H:%M PKT")

    def _full_pkt(stamp: str) -> str:
        try:
            dt = datetime.datetime.strptime(stamp.replace(" UTC", ""), "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError, AttributeError):
            return stamp
        return (dt + datetime.timedelta(hours=5)).strftime("%Y-%m-%d %H:%M PKT")

    # Title
    t = doc.add_heading("ATLAS — Pakistan Border Satellite Surveillance Report", 0)
    t.alignment = WD_ALIGN_PARAGRAPH.CENTER
    gen_pkt = (now + datetime.timedelta(hours=5)).strftime('%Y-%m-%d %H:%M PKT')
    doc.add_paragraph(f"Date: {date_str}  |  Generated: {gen_pkt}").alignment = WD_ALIGN_PARAGRAPH.CENTER
    # Timezone declaration — every time in this document is PKT (UTC+5).
    tz_p = doc.add_paragraph()
    tz_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    tz_r = tz_p.add_run("All times in this document are Pakistan Standard Time (PKT, UTC+5h, no DST).")
    tz_r.italic = True
    tz_r.font.size = Pt(9)
    doc.add_paragraph("")
    
    # Executive Summary
    doc.add_heading("Executive Summary", level=1)
    summary = doc.add_table(rows=6, cols=2)
    summary.style = "Table Grid"
    for r, (lbl, val) in enumerate([
        ("Total Border Crossings", str(len(crossings))),
        ("Unique Satellites", str(len(set(c["norad_id"] for c in crossings)))),
        ("Indian Satellites Detected", f"{len(indian_crossings)} crossings ({len(set(c['norad_id'] for c in indian_crossings))} unique)"),
        ("Indian Imagery Satellites", f"{len(indian_imagery)} crossings"),
        ("Anomalies Detected", str(len(anomalies))),
        ("Surveillance Region", "23.5°N–37.5°N, 60.5°E–77.5°E"),
    ]):
        summary.cell(r, 0).text = lbl
        summary.cell(r, 1).text = val
        summary.cell(r, 0).paragraphs[0].runs[0].bold = True
        # Highlight Indian satellite rows in RED
        if "Indian" in lbl:
            for cell in [summary.cell(r, 0), summary.cell(r, 1)]:
                cell.paragraphs[0].runs[0].font.color.rgb = RGBColor(255, 0, 0)  # RED
                cell.paragraphs[0].runs[0].bold = True
    doc.add_paragraph("")
    
    # Indian Satellites Section
    if indian_crossings:
        doc.add_heading(f"🇮🇳 INDIAN SATELLITE ACTIVITY ({len(indian_crossings)} crossings)", level=1)
        for run in doc.paragraphs[-1].runs:
            run.font.color.rgb = RGBColor(255, 0, 0)  # RED
        
        # Indian satellite purposes
        indian_purposes = {}
        for c in indian_crossings:
            sat_name = c["name"]
            sat_type = c["type"]
            if sat_name not in indian_purposes:
                indian_purposes[sat_name] = {
                    "type": sat_type,
                    "owner": c["owner"],
                    "crossings": 0,
                    "purpose": ""
                }
            indian_purposes[sat_name]["crossings"] += 1
        
        # Define purposes
        purpose_map = {
            "CARTOSAT": "High-resolution Earth imaging for cartography, urban planning, and military reconnaissance",
            "RESOURCESAT": "Natural resource monitoring, agriculture, forestry, and land use mapping",
            "RISAT": "All-weather Radar imaging (SAR) for surveillance, disaster monitoring, and military applications",
        }
        
        for sat_name in indian_purposes:
            for key, purpose in purpose_map.items():
                if key in sat_name.upper():
                    indian_purposes[sat_name]["purpose"] = purpose
                    break
            if not indian_purposes[sat_name]["purpose"]:
                indian_purposes[sat_name]["purpose"] = "Earth observation and monitoring"
        
        doc.add_paragraph("Indian Space Research Organisation (ISRO) satellites detected over Pakistan:", style="Body Text")
        doc.add_paragraph("")
        
        # Indian satellite table
        indian_tbl = doc.add_table(rows=1 + len(indian_purposes), cols=4)
        indian_tbl.style = "Table Grid"
        headers = ["Satellite", "Type", "Crossings", "Primary Purpose"]
        for i, h in enumerate(headers):
            cell = indian_tbl.rows[0].cells[i]
            cell.text = h
            cell.paragraphs[0].runs[0].bold = True
            cell.paragraphs[0].runs[0].font.color.rgb = RGBColor(255, 140, 0)
        
        for i, (sat_name, info) in enumerate(sorted(indian_purposes.items()), 1):
            row = indian_tbl.rows[i].cells
            row[0].text = sat_name
            row[1].text = info["type"]
            row[2].text = str(info["crossings"])
            row[3].text = info["purpose"]
            # Highlight imagery satellites in RED
            if "observation" in info["type"].lower() or "radar" in info["type"].lower():
                row[0].paragraphs[0].runs[0].bold = True
                row[0].paragraphs[0].runs[0].font.color.rgb = RGBColor(255, 0, 0)  # RED
        
        doc.add_paragraph("")
    
    # Indian Imagery Satellites - Detailed Border Crossings
    if indian_imagery:
        # Sort so OPTICAL passes come first, SAR last (operator-requested layout)
        def _is_sar_imagery(c):
            t = (c.get("type", "") or "").lower()
            return "sar" in t or "radar" in t
        indian_optical = [c for c in indian_imagery if not _is_sar_imagery(c)]
        indian_sar     = [c for c in indian_imagery if     _is_sar_imagery(c)]
        indian_imagery = indian_optical + indian_sar

        doc.add_heading(f"📷 INDIAN IMAGERY SATELLITES - BORDER CROSSING DETAILS", level=1)
        for run in doc.paragraphs[-1].runs:
            run.font.color.rgb = RGBColor(255, 0, 0)  # RED

        doc.add_paragraph(
            f"Detailed entry/exit points for Indian reconnaissance and imaging satellites — "
            f"{len(indian_optical)} optical + {len(indian_sar)} SAR.",
            style="Body Text")
        doc.add_paragraph("")

        # Create visual map for all Indian satellites
        map_path = os.path.join(DOCS_DIR, f"map_India_{date_str}.png")
        if create_satellite_path_map(indian_imagery, "India", date_str, map_path):
            doc.add_paragraph("Visual Map - All Indian Satellite Paths:", style="Body Text").runs[0].bold = True
            doc.add_picture(map_path, width=Inches(6.0))
            doc.add_paragraph("")

        # Section banners — OPTICAL above / SAR below
        _opt_banner_idx = 0
        _sar_banner_idx = len(indian_optical)
        for i, crossing in enumerate(indian_imagery, 1):
            # Insert a banner just before the first item of each kind
            if i - 1 == _opt_banner_idx and indian_optical:
                h = doc.add_heading(f"  Optical  ({len(indian_optical)} passes)", level=2)
                for r in h.runs:
                    r.font.color.rgb = RGBColor(255, 0, 0)
            if i - 1 == _sar_banner_idx and indian_sar:
                h = doc.add_heading(f"  SAR  ({len(indian_sar)} passes)", level=2)
                for r in h.runs:
                    r.font.color.rgb = RGBColor(255, 0, 0)
            # Satellite header
            p = doc.add_paragraph()
            run = p.add_run(f"{i}. {crossing['name']} ({crossing['type']})")
            run.bold = True
            run.font.size = Pt(11)
            run.font.color.rgb = RGBColor(255, 0, 0)  # RED
            
            # Details table
            detail_tbl = doc.add_table(rows=7, cols=2)
            detail_tbl.style = "Light Grid Accent 1"
            
            details = [
                ("Entry Time", _full_pkt(crossing["entry_time"])),
                ("Entry Point", f"{crossing['entry_lat']}°N, {crossing['entry_lon']}°E"),
                ("Exit Time", _full_pkt(crossing["exit_time"])),
                ("Duration Over Pakistan", f"{crossing['duration_min']} minutes"),
                ("Maximum Altitude", f"{crossing['max_alt_km']} km"),
                ("Direction of Travel", crossing["direction"]),
                ("Owner/Operator", crossing["owner"]),
            ]
            
            for r, (label, value) in enumerate(details):
                detail_tbl.cell(r, 0).text = label
                detail_tbl.cell(r, 1).text = str(value)
                detail_tbl.cell(r, 0).paragraphs[0].runs[0].bold = True
            
            # Border crossing description
            entry_desc = get_border_region(crossing["entry_lat"], crossing["entry_lon"])
            direction_desc = get_direction_description(crossing["direction"])
            
            doc.add_paragraph(
                f"   ➤ Entered Pakistani airspace from {entry_desc}, traveling {direction_desc}. "
                f"Satellite remained over Pakistan for {crossing['duration_min']} minutes at altitude {crossing['max_alt_km']} km.",
                style="Body Text"
            )
            doc.add_paragraph("")
    
    # Other Countries' Imagery Satellites
    imagery_countries = {}
    for c in crossings:
        if ("observation" in c["type"].lower() or "radar" in c["type"].lower() or "sar" in c["type"].lower()) and c["country"] != "India":
            if c["country"] not in imagery_countries:
                imagery_countries[c["country"]] = []
            imagery_countries[c["country"]].append(c)
    
    # Create sections for each country with imagery satellites
    for country, country_crossings in sorted(imagery_countries.items()):
        if len(country_crossings) > 0:
            # Country header
            country_flag = {"China": "🇨🇳", "USA": "🇺🇸", "Europe": "🇪🇺", "France": "🇫🇷"}.get(country, "🛰")
            doc.add_heading(f"{country_flag} {country.upper()} IMAGERY SATELLITES", level=1)
            
            # Create visual map
            map_path = os.path.join(DOCS_DIR, f"map_{country.replace(' ', '_')}_{date_str}.png")
            if create_satellite_path_map(country_crossings, country, date_str, map_path):
                doc.add_paragraph(f"Visual Map - All {country} Satellite Paths:", style="Body Text").runs[0].bold = True
                doc.add_picture(map_path, width=Inches(6.0))
                doc.add_paragraph("")
            
            # Summary table — adds Max Tilt (°) and Standoff (km) so the
            # reader sees per-satellite imaging reach instead of a single
            # global buffer. Values come from hires_eo_satellites.TILT_SPECS.
            # Split into Optical (above) / SAR (below) per operator request.
            try:
                from hires_eo_satellites import (
                    max_tilt_deg as _v2_tilt,
                    standoff_km as _v2_so,
                )
            except ImportError:
                _v2_tilt = lambda _n: None
                _v2_so   = lambda _n: None

            def _is_sar_pass(c: dict) -> bool:
                t = (c.get("type", "") or "").lower()
                return "sar" in t or "radar" in t

            optical_pass = [c for c in country_crossings if not _is_sar_pass(c)]
            sar_pass     = [c for c in country_crossings if     _is_sar_pass(c)]

            headers = ["Satellite", "Type", "Entry Time", "Duration (min)",
                       "Entry Point", "Direction", "Max Tilt (°)", "Standoff (km)"]

            def _render_country_block(label: str, rows: list):
                if not rows:
                    return
                lbl = doc.add_paragraph(
                    f"{country} — {label} ({len(rows)} passes)", style="Body Text")
                lbl.runs[0].bold = True
                ctbl = doc.add_table(rows=1 + len(rows), cols=8)
                ctbl.style = "Light Grid"
                for i, h in enumerate(headers):
                    cell = ctbl.rows[0].cells[i]
                    cell.text = h
                    cell.paragraphs[0].runs[0].bold = True
                for i, c in enumerate(rows, 1):
                    r = ctbl.rows[i].cells
                    nid = str(c.get("norad_id", ""))
                    r[0].text = c["name"][:25]
                    r[1].text = c["type"][:15]
                    r[2].text = _entry_time_pkt(c["entry_time"])
                    r[3].text = str(c["duration_min"])
                    r[4].text = f"{c['entry_lat']}°N, {c['entry_lon']}°E"
                    r[5].text = c["direction"]
                    tilt = _v2_tilt(nid)
                    r[6].text = f"{tilt}" if tilt is not None else "-"
                    so = _v2_so(nid)
                    r[7].text = f"{so:.0f}" if so is not None else "-"
                doc.add_paragraph("")

            doc.add_paragraph(
                f"{country} reconnaissance and imaging satellites detected "
                f"({len(optical_pass)} optical + {len(sar_pass)} SAR):",
                style="Body Text")
            _render_country_block("Optical", optical_pass)
            _render_country_block("SAR",     sar_pass)
            doc.add_paragraph("")
    
    # Anomalies Section
    if anomalies:
        doc.add_heading(f"⚠ ANOMALIES DETECTED ({len(anomalies)})", level=1)
        for run in doc.paragraphs[-1].runs:
            run.font.color.rgb = RGBColor(251, 113, 133)
        
        for i, anom in enumerate(anomalies, 1):
            p = doc.add_paragraph(style="List Number")
            run = p.add_run(f"[{anom['severity']}] {anom['type']}: {anom['satellite']}")
            run.bold = True
            if anom['severity'] == "HIGH":
                run.font.color.rgb = RGBColor(251, 113, 133)
            else:
                run.font.color.rgb = RGBColor(232, 121, 249)
            
            doc.add_paragraph(f"   Owner: {anom['owner']} | NORAD {anom['norad_id']}")
            doc.add_paragraph(f"   Details: {anom['details']}")
        doc.add_paragraph("")
    
    # Country Breakdown
    doc.add_heading("Crossings by Country", level=1)
    country_counts = Counter(c["country"] for c in crossings)
    country_tbl = doc.add_table(rows=1 + len(country_counts), cols=2)
    country_tbl.style = "Table Grid"
    country_tbl.rows[0].cells[0].text = "Country"
    country_tbl.rows[0].cells[1].text = "Crossings"
    for cell in country_tbl.rows[0].cells:
        cell.paragraphs[0].runs[0].bold = True
    for i, (country, cnt) in enumerate(country_counts.most_common(), 1):
        country_tbl.rows[i].cells[0].text = country
        country_tbl.rows[i].cells[1].text = str(cnt)
        # Highlight India
        if country == "India":
            country_tbl.rows[i].cells[0].paragraphs[0].runs[0].font.color.rgb = RGBColor(255, 140, 0)
            country_tbl.rows[i].cells[0].paragraphs[0].runs[0].bold = True
    doc.add_paragraph("")
    
    # Type Breakdown
    doc.add_heading("Crossings by Satellite Type", level=1)
    type_counts = Counter(c["type"] for c in crossings)
    type_tbl = doc.add_table(rows=1 + len(type_counts), cols=2)
    type_tbl.style = "Table Grid"
    type_tbl.rows[0].cells[0].text = "Type"
    type_tbl.rows[0].cells[1].text = "Crossings"
    for cell in type_tbl.rows[0].cells:
        cell.paragraphs[0].runs[0].bold = True
    for i, (sat_type, cnt) in enumerate(type_counts.most_common(), 1):
        type_tbl.rows[i].cells[0].text = sat_type
        type_tbl.rows[i].cells[1].text = str(cnt)
    doc.add_paragraph("")
    
    # Full Crossing List
    doc.add_heading(f"All Border Crossings ({len(crossings)} total)", level=1)
    cols = ["#", "Satellite", "Owner", "Country", "Type", "Entry Time", "Duration (min)", "Alt (km)", "Direction"]
    tbl = doc.add_table(rows=1 + len(crossings), cols=len(cols))
    tbl.style = "Table Grid"
    for i, h in enumerate(cols):
        tbl.rows[0].cells[i].text = h
        tbl.rows[0].cells[i].paragraphs[0].runs[0].bold = True
        tbl.rows[0].cells[i].paragraphs[0].runs[0].font.size = Pt(8)
    
    for i, c in enumerate(crossings, 1):
        row = tbl.rows[i].cells
        row[0].text = str(i)
        row[1].text = c["name"][:30]
        row[2].text = c["owner"][:20]
        row[3].text = c["country"]
        row[4].text = c["type"][:15]
        row[5].text = _full_pkt(c["entry_time"])
        row[6].text = str(c["duration_min"])
        row[7].text = str(c["max_alt_km"])
        row[8].text = c["direction"]
        for cell in row:
            cell.paragraphs[0].runs[0].font.size = Pt(7)
        
        # Highlight Indian satellites in RED
        if c["country"] == "India":
            row[1].paragraphs[0].runs[0].font.color.rgb = RGBColor(255, 0, 0)  # RED
            row[1].paragraphs[0].runs[0].bold = True
            row[3].paragraphs[0].runs[0].font.color.rgb = RGBColor(255, 0, 0)  # RED
            row[3].paragraphs[0].runs[0].bold = True
    
    os.makedirs(DOCS_DIR, exist_ok=True)
    filename = f"Pakistan_Border_Surveillance_{date_str}.docx"
    filepath = os.path.join(DOCS_DIR, filename)
    doc.save(filepath)
    print(f"[+] Report saved: {filepath}")
    return filepath


# ── Helper Functions for Border Descriptions ─────────────────────────────────
def get_border_region(lat, lon):
    """Determine which border region the satellite entered from."""
    # Pakistan borders: North (China/Afghanistan), East (India), West (Iran/Afghanistan), South (Arabian Sea)
    if lat > 35:  # Northern border
        if lon < 72:
            return "the northwest (Afghanistan/China border region)"
        else:
            return "the northeast (China/Kashmir border region)"
    elif lat < 26:  # Southern region
        return "the south (Arabian Sea/Indian Ocean)"
    elif lon > 75:  # Eastern border
        return "the east (Indian border - Punjab/Rajasthan sector)"
    elif lon < 63:  # Western border
        return "the west (Iran/Afghanistan border)"
    else:
        return "the border region"


def get_direction_description(direction):
    """Convert direction code to descriptive text."""
    descriptions = {
        "N→S": "north to south",
        "S→N": "south to north",
        "E→W": "east to west",
        "W→E": "west to east",
    }
    return descriptions.get(direction, direction)


def _load_pakistan_geojson():
    """Download and cache Pakistan GeoJSON border from PakData/GISData."""
    import json, os, requests
    cache_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pak_border.geojson")
    
    # Use cached file if available
    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)
    
    # Download from GitHub
    urls = [
        "https://raw.githubusercontent.com/PakData/GISData/master/PAK-GeoJSON/PAK_adm0.json",
        "https://raw.githubusercontent.com/PakData/GISData/master/PAK-GeoJSON/PAK_adm1.json",
    ]
    for url in urls:
        try:
            print(f"  [*] Downloading Pakistan GeoJSON from {url.split('/')[-1]}...")
            r = requests.get(url, timeout=15)
            if r.status_code == 200:
                data = r.json()
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump(data, f)
                print(f"  [+] Pakistan GeoJSON cached at {cache_path}")
                return data
        except Exception as e:
            print(f"  [!] Could not download GeoJSON: {e}")
    return None


def _draw_pakistan_border(ax, geojson, zorder=5):
    """Draw Pakistan border/provinces from GeoJSON onto matplotlib axes."""
    import numpy as np
    from matplotlib.patches import Polygon as MplPolygon
    from matplotlib.collections import PatchCollection

    if not geojson or "features" not in geojson:
        return

    patches = []
    for feature in geojson["features"]:
        geom = feature.get("geometry", {})
        gtype = geom.get("type", "")
        coords_list = geom.get("coordinates", [])

        if gtype == "Polygon":
            coords_list = [coords_list]
        elif gtype != "MultiPolygon":
            continue

        for polygon in coords_list:
            if not polygon:
                continue
            exterior = np.array(polygon[0])  # outer ring
            if exterior.shape[0] < 3:
                continue
            patch = MplPolygon(exterior, closed=True)
            patches.append(patch)

    if patches:
        # Draw filled provinces with semi-transparent white
        col = PatchCollection(patches, facecolor='white', edgecolor='#00ff00',
                              linewidth=2.5, alpha=0.08, zorder=zorder)
        ax.add_collection(col)
        # Draw border outline on top (bright green, thick)
        col2 = PatchCollection(patches, facecolor='none', edgecolor='#00ff00',
                               linewidth=2.5, alpha=0.95, zorder=zorder + 1)
        ax.add_collection(col2)


def create_satellite_path_map(crossings, country_name, date_str, output_path):
    """Create a visual map showing all satellite paths overlaid on Google Maps satellite imagery with real Pakistan GeoJSON border."""
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import contextily as ctx
    except ImportError as e:
        print(f"Missing required library: {e}")
        return None

    # Load Pakistan GeoJSON (provincial level for detail)
    pak_geojson = _load_pakistan_geojson()

    # Create figure
    fig, ax = plt.subplots(figsize=(16, 12))

    # Pakistan boundaries (lat/lon)
    pak_extent = [60.5, 77.5, 23.5, 37.8]  # [lon_min, lon_max, lat_min, lat_max]

    # Set the map extent
    ax.set_xlim(pak_extent[0], pak_extent[1])
    ax.set_ylim(pak_extent[2], pak_extent[3])

    # Add Google Maps satellite imagery as background
    try:
        ctx.add_basemap(ax, crs='EPSG:4326', source=ctx.providers.Esri.WorldImagery, zoom=6, attribution=False)
    except Exception as e:
        print(f"Warning: Could not load satellite imagery: {e}")
        ax.set_facecolor('#1a1a2e')

    # Draw real Pakistan border from GeoJSON
    if pak_geojson:
        _draw_pakistan_border(ax, pak_geojson, zorder=5)
        print(f"  [+] Pakistan GeoJSON border drawn")
    
    # Add major cities with bright markers for visibility on satellite imagery
    cities = {
        # Capital (red star)
        'Islamabad': (73.05, 33.72, '#ff0000', '*', 20),
        # Major cities (bright yellow dots)
        'Karachi': (67.01, 24.86, '#ffff00', 'o', 12),
        'Lahore': (74.35, 31.52, '#ffff00', 'o', 12),
        'Peshawar': (71.58, 34.01, '#ffff00', 'o', 10),
        'Quetta': (67.00, 30.18, '#ffff00', 'o', 10),
        'Rawalpindi': (73.06, 33.60, '#ffff00', 'o', 9),
        'Faisalabad': (73.09, 31.42, '#ffff00', 'o', 9),
        'Multan': (71.47, 30.20, '#ffff00', 'o', 9),
        'Hyderabad': (68.37, 25.39, '#ffff00', 'o', 9),
        'Gujranwala': (74.18, 32.16, '#ffff00', 'o', 8),
        'Sialkot': (74.53, 32.49, '#ffff00', 'o', 8),
        'Sargodha': (72.67, 32.08, '#ffff00', 'o', 8),
        'Bahawalpur': (71.68, 29.40, '#ffff00', 'o', 8),
        'Sukkur': (68.86, 27.70, '#ffff00', 'o', 8),
        'Gilgit': (74.33, 35.92, '#ffff00', 'o', 8),
        'Skardu': (75.63, 35.30, '#ffff00', 'o', 8),
    }
    
    for city, (lon, lat, color, marker, size) in cities.items():
        ax.plot(lon, lat, marker, color=color, markersize=size, 
                markeredgecolor='black', markeredgewidth=2, zorder=10)
        # City label with white background for visibility
        offset = 0.3 if marker == '*' else 0.25
        ax.text(lon + offset, lat + 0.15, city, fontsize=9, color='white', 
                weight='bold', zorder=11,
                bbox=dict(boxstyle='round,pad=0.3', facecolor='black', 
                         edgecolor='white', alpha=0.8, linewidth=1.5))
    
    # Bright color palette for satellites (high visibility on satellite imagery)
    # RED for Indian satellites, other colors for rest
    colors = ['#ff0000', '#00ff00', '#00ffff', '#ff00ff', '#ffff00', 
              '#ff6600', '#ff0099', '#00ff99', '#9900ff', '#ff9900']
    
    # Plot satellite paths with high visibility
    for i, crossing in enumerate(crossings):
        entry_lon = crossing['entry_lon']
        entry_lat = crossing['entry_lat']
        exit_lon = crossing.get('exit_lon', entry_lon)
        exit_lat = crossing.get('exit_lat', entry_lat)
        
        # 🔴 RED for Indian satellites, cycle through colors for others
        is_indian = crossing.get('country') == 'India'
        if is_indian:
            color = '#ff0000'  # Bright red for Indian satellites
        else:
            color = colors[i % len(colors)]
        
        # Draw path with thick bright line and black outline for visibility
        ax.plot([entry_lon, exit_lon], [entry_lat, exit_lat], 
                color='black', linewidth=7, linestyle='-', alpha=0.8, zorder=7)
        ax.plot([entry_lon, exit_lon], [entry_lat, exit_lat], 
                color=color, linewidth=5, linestyle='-', alpha=1.0, zorder=8,
                label=f"{crossing['name'][:25]}")
        
        # Entry point (large triangle with black outline)
        ax.plot(entry_lon, entry_lat, '^', color=color, markersize=24, 
                markeredgecolor='black', markeredgewidth=3, zorder=9)
        
        # Exit point (large triangle with black outline)
        ax.plot(exit_lon, exit_lat, 'v', color=color, markersize=24,
                markeredgecolor='black', markeredgewidth=3, zorder=9)
        
        # Add satellite name near path midpoint with high contrast
        mid_lon = (entry_lon + exit_lon) / 2
        mid_lat = (entry_lat + exit_lat) / 2
        if len(crossings) <= 6:
            # Special formatting for Indian satellites
            if is_indian:
                label_text = f"🇮🇳 {crossing['name'][:20]}"
                label_color = '#ff0000'
            else:
                label_text = crossing['name'][:20]
                label_color = color
            
            ax.text(mid_lon, mid_lat, label_text, 
                   fontsize=10, color='white', weight='bold', zorder=12,
                   bbox=dict(boxstyle='round,pad=0.5', facecolor='black', 
                            edgecolor=label_color, alpha=0.9, linewidth=3))
    
    # Styling with high contrast for satellite imagery
    ax.set_xlabel('Longitude (°E)', fontsize=14, weight='bold', color='white',
                  bbox=dict(boxstyle='round,pad=0.5', facecolor='black', alpha=0.8))
    ax.set_ylabel('Latitude (°N)', fontsize=14, weight='bold', color='white',
                  bbox=dict(boxstyle='round,pad=0.5', facecolor='black', alpha=0.8))
    
    # Title with high contrast
    title_text = f'{country_name} Imagery Satellites Over Pakistan\nDate: {date_str}'
    ax.set_title(title_text, fontsize=20, weight='bold', pad=25, color='white',
                bbox=dict(boxstyle='round,pad=0.8', facecolor='black', 
                         edgecolor='white', alpha=0.9, linewidth=3))
    
    # Grid with bright color for visibility
    ax.grid(True, alpha=0.4, linestyle='--', linewidth=1.2, color='white')
    
    # Legend with high contrast
    if len(crossings) <= 8:
        legend = ax.legend(loc='upper left', fontsize=10, framealpha=0.95,
                          edgecolor='white', fancybox=True, shadow=True)
        legend.get_frame().set_facecolor('black')
        for text in legend.get_texts():
            text.set_color('white')
    else:
        summary_text = f'{len(crossings)} Satellite Crossings\n{len(set(c["name"] for c in crossings))} Unique Satellites'
        ax.text(0.02, 0.98, summary_text, transform=ax.transAxes, 
               fontsize=12, weight='bold', verticalalignment='top', color='white',
               bbox=dict(boxstyle='round,pad=0.8', facecolor='black', 
                        edgecolor='white', alpha=0.95, linewidth=2))
    
    # Legend box at bottom with high contrast
    legend_text = '▲ Entry Point  |  ▼ Exit Point  |  ━━ Satellite Path  |  ★ Capital  |  ● Cities'
    ax.text(0.5, 0.01, legend_text, transform=ax.transAxes, 
            fontsize=12, ha='center', weight='bold', color='white',
            bbox=dict(boxstyle='round,pad=0.8', facecolor='black', 
                     edgecolor='#00ff00', alpha=0.95, linewidth=3))
    
    # Add border frame with bright color
    for spine in ax.spines.values():
        spine.set_edgecolor('white')
        spine.set_linewidth(3)
    
    # Save figure
    plt.tight_layout()
    plt.savefig(output_path, dpi=200, bbox_inches='tight', facecolor='white')
    plt.close()
    
    return output_path


def create_coordinate_map(entry_lat, entry_lon, exit_lat, exit_lon, direction):
    """Create a detailed ASCII map of Pakistan showing entry/exit points and satellite path."""
    # Pakistan bounding box
    lat_min, lat_max = 23.5, 37.5
    lon_min, lon_max = 60.5, 77.5
    
    # Map dimensions (larger for better detail)
    width, height = 50, 25
    
    # Create empty map
    map_grid = [[' ' for _ in range(width)] for _ in range(height)]
    
    # Simplified Pakistan border coordinates (approximate outline)
    # Format: (lat, lon) - key border points
    pakistan_border = [
        # Southwest coast
        (24.0, 66.5), (24.5, 66.0), (25.0, 66.5), (25.5, 66.8),
        # Sindh-Balochistan coast
        (26.0, 66.5), (26.5, 66.0), (27.0, 65.5), (28.0, 64.5),
        # Western border (Iran/Afghanistan)
        (29.0, 63.5), (30.0, 62.5), (31.0, 62.0), (32.0, 61.5),
        (33.0, 61.0), (34.0, 61.5), (35.0, 62.0), (36.0, 63.0),
        # Northern border (Afghanistan/China)
        (36.5, 65.0), (37.0, 67.0), (37.0, 70.0), (36.5, 72.0),
        (36.0, 74.0), (35.5, 75.0), (35.0, 76.0),
        # Eastern border (India - Kashmir)
        (34.5, 76.5), (34.0, 76.0), (33.5, 75.5), (33.0, 75.0),
        # Punjab border
        (32.5, 75.5), (32.0, 75.0), (31.5, 75.5), (31.0, 75.0),
        (30.5, 74.5), (30.0, 73.5), (29.5, 73.0),
        # Sindh-India border
        (28.5, 71.0), (27.5, 70.0), (26.5, 69.5), (25.5, 69.0),
        (24.5, 68.5), (24.0, 68.0), (24.0, 66.5),  # back to start
    ]
    
    # Draw Pakistan border
    for i in range(len(pakistan_border) - 1):
        lat1, lon1 = pakistan_border[i]
        lat2, lon2 = pakistan_border[i + 1]
        
        x1 = int((lon1 - lon_min) / (lon_max - lon_min) * (width - 1))
        y1 = int((lat_max - lat1) / (lat_max - lat_min) * (height - 1))
        x2 = int((lon2 - lon_min) / (lon_max - lon_min) * (width - 1))
        y2 = int((lat_max - lat2) / (lat_max - lat_min) * (height - 1))
        
        # Draw line between points
        steps = max(abs(x2 - x1), abs(y2 - y1)) + 1
        for step in range(steps):
            t = step / max(steps - 1, 1)
            x = int(x1 + (x2 - x1) * t)
            y = int(y1 + (y2 - y1) * t)
            if 0 <= y < height and 0 <= x < width:
                map_grid[y][x] = '█'
    
    # Add major cities
    cities = {
        "ISB": (33.7, 73.1),   # Islamabad
        "LHR": (31.5, 74.3),   # Lahore
        "KHI": (24.9, 67.0),   # Karachi
        "QTA": (30.2, 67.0),   # Quetta
        "PSH": (34.0, 71.5),   # Peshawar
        "FSD": (31.4, 73.1),   # Faisalabad
        "MUL": (30.2, 71.5),   # Multan
    }
    
    for city, (lat, lon) in cities.items():
        x = int((lon - lon_min) / (lon_max - lon_min) * (width - 1))
        y = int((lat_max - lat) / (lat_max - lat_min) * (height - 1))
        if 0 <= y < height and 0 <= x < width:
            if map_grid[y][x] == ' ':
                map_grid[y][x] = '●'
    
    # Plot entry point
    entry_x = int((entry_lon - lon_min) / (lon_max - lon_min) * (width - 1))
    entry_y = int((lat_max - entry_lat) / (lat_max - lat_min) * (height - 1))
    
    # Plot exit point
    exit_x = int((exit_lon - lon_min) / (lon_max - lon_min) * (width - 1))
    exit_y = int((lat_max - exit_lat) / (lat_max - lat_min) * (height - 1))
    
    # Draw satellite path (dashed line)
    if 0 <= entry_y < height and 0 <= entry_x < width and 0 <= exit_y < height and 0 <= exit_x < width:
        steps = max(abs(exit_x - entry_x), abs(exit_y - entry_y)) + 1
        for step in range(steps):
            t = step / max(steps - 1, 1)
            x = int(entry_x + (exit_x - entry_x) * t)
            y = int(entry_y + (exit_y - entry_y) * t)
            if 0 <= y < height and 0 <= x < width:
                # Dashed line effect
                if step % 2 == 0:
                    map_grid[y][x] = '·'
                else:
                    map_grid[y][x] = '-' if abs(exit_x - entry_x) > abs(exit_y - entry_y) else '|'
    
    # Mark entry and exit points (overwrite path)
    if 0 <= entry_y < height and 0 <= entry_x < width:
        map_grid[entry_y][entry_x] = '▲'  # Entry
    if 0 <= exit_y < height and 0 <= exit_x < width:
        map_grid[exit_y][exit_x] = '▼'  # Exit
    
    # Convert to string
    map_str = '\n'.join([''.join(row) for row in map_grid])
    
    # Add legend
    map_str += f"\n\n   LEGEND:"
    map_str += f"\n   █ = Pakistan Border"
    map_str += f"\n   ▲ = Entry Point ({entry_lat:.2f}°N, {entry_lon:.2f}°E)"
    map_str += f"\n   ▼ = Exit Point (approx {exit_lat:.2f}°N, {exit_lon:.2f}°E)"
    map_str += f"\n   · - | = Satellite Path ({direction})"
    map_str += f"\n   ● = Major Cities (ISB=Islamabad, LHR=Lahore, KHI=Karachi, etc.)"
    
    return map_str


# ── Single Day Scanner ──────────────────────────────────────────────────────
def scan_single_day(target_date, tles, history):
    """Scan a single day and return results."""
    date_str = str(target_date)
    
    print(f"[*] Scanning {date_str}...")
    
    # Calculate crossings
    crossings = calculate_border_crossings(tles, target_date)
    
    # Detect anomalies
    anomalies = detect_anomalies(crossings, history)
    
    # Update history
    history[date_str] = {
        "total_crossings": len(crossings),
        "crossings": crossings,
        "anomalies": anomalies,
        "generated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    
    # Save anomalies
    if anomalies:
        all_anomalies = []
        if os.path.exists(ANOMALY_FILE):
            try:
                all_anomalies = json.load(open(ANOMALY_FILE, encoding='utf-8'))
            except:
                pass
        all_anomalies.extend([{**a, "date": date_str} for a in anomalies])
        json.dump(all_anomalies, open(ANOMALY_FILE, 'w', encoding='utf-8'), indent=2)
    
    # Generate report
    report_path = generate_report(crossings, date_str, history, anomalies)
    
    print(f"[+] {date_str}: {len(crossings)} crossings, {len(anomalies)} anomalies")
    
    return {
        "date": date_str,
        "crossings": len(crossings),
        "satellites": len(set(c['norad_id'] for c in crossings)),
        "anomalies": len(anomalies),
        "report": report_path,
    }


# ── Main Runner with Auto-Backfill ───────────────────────────────────────────
def run(target_date=None):
    """
    Main runner with automatic backfill of missing dates.
    - Always scans for YESTERDAY (not today)
    - Automatically fills in any missing dates since last scan
    - Starting baseline: April 26, 2026
    """
    # Load history
    history = {}
    if os.path.exists(HISTORY_FILE):
        try:
            history = json.load(open(HISTORY_FILE, encoding='utf-8'))
        except:
            pass
    
    # Determine target date (yesterday by default)
    if target_date is None:
        target_date = datetime.date.today() - timedelta(days=1)
    elif isinstance(target_date, str):
        target_date = datetime.date.fromisoformat(target_date)
    
    # Baseline start date
    BASELINE_DATE = datetime.date(2026, 4, 26)
    
    print(f"\n{'='*55}")
    print(f"  ATLAS PAKISTAN BORDER SATELLITE TRACKER")
    print(f"  Auto-Backfill System Active")
    print(f"{'='*55}\n")

    # ── Rolling backup of state BEFORE we touch anything ────────────────────
    try:
        import backup_manager
        backup_manager.snapshot()
    except Exception as e:
        print(f"[!] backup snapshot failed: {e}")
    
    # Find last scanned date
    if history:
        last_date_str = max(history.keys())
        last_date = datetime.date.fromisoformat(last_date_str)
        print(f"[*] Last scan: {last_date_str}")
    else:
        last_date = BASELINE_DATE - timedelta(days=1)
        print(f"[*] No previous scans found")
        print(f"[*] Starting from baseline: {BASELINE_DATE}")
    
    # Calculate missing dates
    missing_dates = []
    current = max(last_date + timedelta(days=1), BASELINE_DATE)
    
    # If target_date is before or equal to last_date, check if it exists
    if target_date <= last_date:
        if str(target_date) not in history:
            missing_dates.append(target_date)
    else:
        # Scan from day after last_date to target_date
        while current <= target_date:
            date_str = str(current)
            if date_str not in history:
                missing_dates.append(current)
            current += timedelta(days=1)
    
    if not missing_dates:
        print(f"[*] All dates up to {target_date} already scanned")
        print(f"[*] No backfill needed")
        return []
    
    # Check TLE age limit (skip dates older than 7 days from today)
    today = datetime.date.today()
    max_age_days = 7
    valid_dates = [d for d in missing_dates if (today - d).days <= max_age_days]
    skipped_dates = [d for d in missing_dates if (today - d).days > max_age_days]
    
    if skipped_dates:
        print(f"[!] Skipping {len(skipped_dates)} dates (TLE data too old):")
        for d in skipped_dates:
            print(f"    - {d} ({(today - d).days} days old)")
    
    if not valid_dates:
        print(f"[!] No valid dates to scan")
        return []
    
    print(f"\n[*] Backfilling {len(valid_dates)} missing date(s):")
    for d in valid_dates:
        print(f"    - {d}")
    print()
    
    # Fetch TLEs once for all dates
    print(f"[*] Fetching TLE data...")
    tles = fetch_tles()
    if not tles:
        print("[!] No TLE data available")
        return []
    
    # Scan each missing date
    results = []
    for i, scan_date in enumerate(valid_dates, 1):
        print(f"\n--- Scanning {i}/{len(valid_dates)}: {scan_date} ---")
        result = scan_single_day(scan_date, tles, history)
        results.append(result)
    
    # Save updated history
    json.dump(history, open(HISTORY_FILE, 'w', encoding='utf-8'), indent=2)

    # ── Save to ATLAS database ────────────────────────────────────────────────
    try:
        import sys
        sys.path.insert(0, os.path.dirname(BASE_DIR))
        from atlas_db import init_db, save_satellite_day
        init_db()
        for scan_date in valid_dates:
            date_str = str(scan_date)
            day_data = history.get(date_str, {})
            save_satellite_day(
                date_str,
                day_data.get("crossings", []),
                day_data.get("anomalies", []),
            )
    except Exception as e:
        print(f"[!] DB save error: {e}")
    # ─────────────────────────────────────────────────────────────────────────
    
    # ── Regenerate 15-day forecast (uses same TLE cache) ────────────────────
    try:
        import forecast_15day
        forecast_15day.run()
    except Exception as e:
        print(f"[!] forecast generation failed: {e}")

    # Print summary
    print(f"\n{'='*55}")
    print(f"  SCAN COMPLETE")
    print(f"{'='*55}")
    print(f"[+] Dates scanned: {len(results)}")
    print(f"[+] Total crossings: {sum(r['crossings'] for r in results)}")
    print(f"[+] Total anomalies: {sum(r['anomalies'] for r in results)}")
    print(f"\n[*] Daily Breakdown:")
    for r in results:
        anom_str = f" ⚠ {r['anomalies']} ANOMALIES" if r['anomalies'] > 0 else ""
        print(f"    {r['date']}: {r['crossings']} crossings, {r['satellites']} satellites{anom_str}")
    
    return results


if __name__ == "__main__":
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg.lower() == "yesterday":
            target = datetime.date.today() - timedelta(days=1)
            run(target)
        elif arg.lower() == "today":
            # Force scan today (not recommended, use for testing only)
            run(datetime.date.today())
        elif arg.lower() == "--force" and len(sys.argv) > 2:
            # Force rescan a date even if it exists
            target = datetime.date.fromisoformat(sys.argv[2])
            # Delete from history to force rescan
            history = {}
            if os.path.exists(HISTORY_FILE):
                try:
                    history = json.load(open(HISTORY_FILE, encoding='utf-8'))
                    if str(target) in history:
                        del history[str(target)]
                        json.dump(history, open(HISTORY_FILE, 'w', encoding='utf-8'), indent=2)
                        print(f"[*] Removed {target} from history, forcing rescan...")
                except:
                    pass
            run(target)
        else:
            # Run for specific date: python satellite_tracker_v2.py 2026-04-26
            run(arg)
    else:
        # Default: scan yesterday and backfill any missing dates
        run()
