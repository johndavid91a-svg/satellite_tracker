"""
ATLAS Rocket Launch Tracker
Fetches upcoming and recent rocket launches from Launch Library 2 API (free, no key needed).
Generates a Word document report with launch details.
"""
import os, sys, json, requests
from datetime import datetime, timezone

if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOCS_DIR = os.path.join(BASE_DIR, "documents")
os.makedirs(DOCS_DIR, exist_ok=True)

# Launch Library 2 API — free, no key required
LL2_BASE     = "https://ll.thespacedevs.com/2.2.0"
UPCOMING_URL = f"{LL2_BASE}/launch/upcoming/?limit=50&mode=detailed&format=json"
RECENT_URL   = f"{LL2_BASE}/launch/previous/?limit=30&mode=detailed&format=json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 ATLAS/1.0",
    "Accept": "application/json",
}

# Country flags for known agencies
COUNTRY_FLAGS = {
    "USA": "🇺🇸", "United States": "🇺🇸",
    "China": "🇨🇳", "CHN": "🇨🇳",
    "Russia": "🇷🇺", "RUS": "🇷🇺",
    "India": "🇮🇳", "IND": "🇮🇳",
    "Europe": "🇪🇺", "France": "🇫🇷",
    "Japan": "🇯🇵", "JPN": "🇯🇵",
    "Israel": "🇮🇱", "ISR": "🇮🇱",
    "Iran": "🇮🇷", "IRN": "🇮🇷",
    "North Korea": "🇰🇵", "PRK": "🇰🇵",
    "South Korea": "🇰🇷", "KOR": "🇰🇷",
    "New Zealand": "🇳🇿",
    "United Kingdom": "🇬🇧",
}

STATUS_COLORS = {
    "Go":           ("✅", "GO"),
    "TBD":          ("🕐", "TBD"),
    "Success":      ("✅", "SUCCESS"),
    "Failure":      ("❌", "FAILURE"),
    "Partial Failure": ("⚠️", "PARTIAL"),
    "Hold":         ("⏸️", "HOLD"),
    "In Flight":    ("🚀", "IN FLIGHT"),
}

def fetch_launches(url, label):
    print(f"[*] Fetching {label}...")
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code == 200:
            data = r.json()
            results = data.get("results", [])
            print(f"[+] {label}: {len(results)} launches")
            return results
        else:
            print(f"[!] {label}: HTTP {r.status_code}")
            return []
    except Exception as e:
        print(f"[!] {label} error: {e}")
        return []

def parse_launch(launch):
    """Extract key fields from a launch object."""
    name     = launch.get("name", "Unknown")
    status   = launch.get("status", {}).get("name", "Unknown")
    status_abbrev = launch.get("status", {}).get("abbrev", "")
    status_desc = launch.get("status", {}).get("description", "")
    net      = launch.get("net", "")  # NET = No Earlier Than date
    window_s = launch.get("window_start", "")
    window_e = launch.get("window_end", "")

    # Format date
    net_fmt = ""
    if net:
        try:
            dt = datetime.fromisoformat(net.replace("Z", "+00:00"))
            net_fmt = dt.strftime("%Y-%m-%d %H:%M UTC")
        except (ValueError, TypeError):
            net_fmt = net[:19]

    # Agency - Enhanced details
    agency = ""
    agency_type = ""
    country = ""
    flag = "🚀"
    lsp = launch.get("launch_service_provider", {})
    if lsp:
        agency  = lsp.get("name", "")
        agency_type = lsp.get("type", "")
        country = lsp.get("country_code", "")
        flag    = COUNTRY_FLAGS.get(country, COUNTRY_FLAGS.get(agency, "🚀"))

    # Rocket - Enhanced details
    rocket_name = ""
    rocket_family = ""
    rocket_variant = ""
    rocket_config = {}
    rocket = launch.get("rocket", {})
    if rocket:
        cfg = rocket.get("configuration", {})
        rocket_name = cfg.get("full_name", cfg.get("name", ""))
        rocket_family = cfg.get("family", "")
        rocket_variant = cfg.get("variant", "")
        rocket_config = {
            "reusable": cfg.get("reusable", False),
            "maiden_flight": cfg.get("maiden_flight", ""),
            "successful_launches": cfg.get("successful_launches", 0),
            "failed_launches": cfg.get("failed_launches", 0),
            "total_launch_count": cfg.get("total_launch_count", 0),
        }

    # Mission - Enhanced details
    mission_name = ""
    mission_desc = ""
    mission_type = ""
    orbit = ""
    mission = launch.get("mission", {})
    if mission:
        mission_name = mission.get("name", "")
        mission_desc = mission.get("description", "")
        mission_type = mission.get("type", "")
        orbit_obj = mission.get("orbit", {})
        if orbit_obj:
            orbit = orbit_obj.get("name", "")

    # Pad / location - Enhanced details
    pad_name = ""
    pad_latitude = ""
    pad_longitude = ""
    location = ""
    location_country = ""
    pad = launch.get("pad", {})
    if pad:
        pad_name = pad.get("name", "")
        pad_latitude = pad.get("latitude", "")
        pad_longitude = pad.get("longitude", "")
        loc = pad.get("location", {})
        location = loc.get("name", "")
        location_country = loc.get("country_code", "")

    # Probability
    prob = launch.get("probability", None)
    
    # Hold reason
    hold_reason = launch.get("holdreason", "")
    fail_reason = launch.get("failreason", "")
    
    # Webcast
    webcast_live = launch.get("webcast_live", False)
    
    # Image
    image_url = launch.get("image", "")

    # Status icon
    icon, status_short = STATUS_COLORS.get(status, ("🚀", status))

    return {
        "name":         name,
        "status":       status,
        "status_short": status_short,
        "status_abbrev": status_abbrev,
        "status_desc":  status_desc,
        "icon":         icon,
        "net":          net_fmt,
        "window_start": window_s[:19].replace("T", " ") if window_s else "",
        "window_end":   window_e[:19].replace("T", " ") if window_e else "",
        "agency":       agency,
        "agency_type":  agency_type,
        "country":      country,
        "flag":         flag,
        "rocket":       rocket_name,
        "rocket_family": rocket_family,
        "rocket_variant": rocket_variant,
        "rocket_config": rocket_config,
        "mission_name": mission_name,
        "mission_desc": mission_desc[:500] if mission_desc else "",
        "mission_type": mission_type,
        "orbit":        orbit,
        "pad":          pad_name,
        "pad_latitude": pad_latitude,
        "pad_longitude": pad_longitude,
        "location":     location,
        "location_country": location_country,
        "probability":  prob,
        "hold_reason":  hold_reason,
        "fail_reason":  fail_reason,
        "webcast_live": webcast_live,
        "image_url":    image_url,
        "id":           launch.get("id", ""),
        "url":          launch.get("url", ""),
        "vid_urls":     [v.get("url","") for v in launch.get("vid_urls", [])[:3]],
    }

def generate_report(upcoming, recent):
    from docx import Document
    from docx.shared import RGBColor, Pt, Cm
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    doc = Document()
    # A4 margins
    sec = doc.sections[0]
    sec.page_width    = Cm(21.0)
    sec.page_height   = Cm(29.7)
    sec.left_margin   = Cm(2.0)
    sec.right_margin  = Cm(2.0)
    sec.top_margin    = Cm(2.5)
    sec.bottom_margin = Cm(2.5)

    now = datetime.now()

    # Title
    t = doc.add_heading("🚀 ATLAS — Global Rocket Launch Tracker", 0)
    t.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph(f"Generated: {now.strftime('%Y-%m-%d %H:%M:%S')}").alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph("")

    # Summary
    summary = doc.add_table(rows=3, cols=2)
    summary.style = "Table Grid"
    for r, (lbl, val) in enumerate([
        ("Upcoming Launches", str(len(upcoming))),
        ("Recent Launches",   str(len(recent))),
        ("Data Source",       "Launch Library 2 (thespacedevs.com)"),
    ]):
        summary.cell(r, 0).text = lbl
        summary.cell(r, 1).text = val
        summary.cell(r, 0).paragraphs[0].runs[0].bold = True
    doc.add_paragraph("")
    
    # Indian launches summary section
    indian_upcoming = [l for l in upcoming if l['country'] in ['IND', 'India'] or 'India' in l['agency']]
    indian_recent = [l for l in recent if l['country'] in ['IND', 'India'] or 'India' in l['agency']]
    
    if indian_upcoming or indian_recent:
        h = doc.add_heading("⭐ 🇮🇳 INDIAN LAUNCHES — PRIORITY TRACKING ⭐", level=1)
        h.runs[0].font.color.rgb = RGBColor(0xFF, 0x66, 0x00)
        h.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(f"Upcoming: {len(indian_upcoming)} | Recent: {len(indian_recent)}")
        run.bold = True
        run.font.size = Pt(12)
        run.font.color.rgb = RGBColor(0xFF, 0x99, 0x33)
        
        if indian_upcoming:
            doc.add_heading("Upcoming Indian Launches", level=2)
            for launch in indian_upcoming:
                write_launch(doc, launch, is_upcoming=True)
        
        if indian_recent:
            doc.add_heading("Recent Indian Launches", level=2)
            for launch in indian_recent:
                write_launch(doc, launch, is_upcoming=False)
        
        doc.add_paragraph("")
        p = doc.add_paragraph()
        run = p.add_run()
        br = OxmlElement('w:br')
        br.set(qn('w:type'), 'page')
        run._r.append(br)

    def write_launch(doc, launch, is_upcoming):
        # Highlight Indian launches with special color
        is_indian = launch['country'] in ['IND', 'India'] or 'India' in launch['agency']
        
        if is_indian:
            color = RGBColor(0xFF, 0x99, 0x33)  # Orange for Indian launches
        else:
            color = RGBColor(0x00, 0x80, 0x00) if is_upcoming else RGBColor(0x1F, 0x77, 0xB4)
        
        p = doc.add_paragraph()
        
        # Add special marker for Indian launches
        if is_indian:
            marker = p.add_run("⭐ INDIA ⭐ ")
            marker.bold = True
            marker.font.size = Pt(12)
            marker.font.color.rgb = RGBColor(0xFF, 0x66, 0x00)
        
        run = p.add_run(f"{launch['icon']} {launch['flag']} {launch['name']}")
        run.bold = True
        run.font.size = Pt(11)
        run.font.color.rgb = color

        rows = [
            ("Status",       f"{launch['status']} ({launch['status_short']})"),
            ("Launch Date",  launch["net"] or "TBD"),
            ("Window Start", launch["window_start"] or "—"),
            ("Window End",   launch["window_end"] or "—"),
            ("Agency",       f"{launch['agency']} ({launch['country']})"),
            ("Agency Type",  launch["agency_type"] or "—"),
            ("Rocket",       launch["rocket"]),
            ("Rocket Family", launch["rocket_family"] or "—"),
            ("Rocket Variant", launch["rocket_variant"] or "—"),
            ("Mission",      launch["mission_name"]),
            ("Mission Type", launch["mission_type"]),
            ("Orbit",        launch["orbit"] or "—"),
            ("Launch Site",  f"{launch['pad']}, {launch['location']}"),
            ("Coordinates",  f"{launch['pad_latitude']}, {launch['pad_longitude']}" if launch['pad_latitude'] else "—"),
        ]
        
        # Add special highlight row for Indian launches
        if is_indian:
            rows.insert(0, ("🇮🇳 INDIAN LAUNCH", "⭐ PRIORITY TRACKING ⭐"))
        
        # Add rocket statistics if available
        if launch["rocket_config"].get("total_launch_count", 0) > 0:
            rc = launch["rocket_config"]
            rows.append(("Rocket Stats", f"Total: {rc['total_launch_count']} | Success: {rc['successful_launches']} | Failed: {rc['failed_launches']}"))
            if rc.get("reusable"):
                rows.append(("Reusable", "Yes ♻️"))
            if rc.get("maiden_flight"):
                rows.append(("Maiden Flight", rc["maiden_flight"]))
        
        if launch["probability"] is not None:
            rows.append(("Go Probability", f"{launch['probability']}%"))
        
        if launch["webcast_live"]:
            rows.append(("Webcast", "🔴 LIVE"))
        
        if launch["hold_reason"]:
            rows.append(("Hold Reason", launch["hold_reason"]))
        
        if launch["fail_reason"]:
            rows.append(("Failure Reason", launch["fail_reason"]))
        
        if launch["vid_urls"]:
            for idx, url in enumerate(launch["vid_urls"], 1):
                rows.append((f"Stream {idx}", url))
        
        if launch["url"]:
            rows.append(("More Info", launch["url"]))

        tbl = doc.add_table(rows=len(rows), cols=2)
        tbl.style = "Light Grid"
        for i, (lbl, val) in enumerate(rows):
            tbl.cell(i, 0).text = lbl
            tbl.cell(i, 1).text = str(val) if val else "—"
            tbl.cell(i, 0).paragraphs[0].runs[0].bold = True
            tbl.cell(i, 0).paragraphs[0].runs[0].font.size = Pt(9)
            tbl.cell(i, 1).paragraphs[0].runs[0].font.size = Pt(9)
            
            # Highlight Indian launch row with orange background
            if is_indian and i == 0:
                tbl.cell(i, 0).paragraphs[0].runs[0].font.color.rgb = RGBColor(0xFF, 0x66, 0x00)
                tbl.cell(i, 1).paragraphs[0].runs[0].font.color.rgb = RGBColor(0xFF, 0x66, 0x00)
                tbl.cell(i, 0).paragraphs[0].runs[0].font.size = Pt(10)
                tbl.cell(i, 1).paragraphs[0].runs[0].font.size = Pt(10)

        if launch["mission_desc"]:
            doc.add_paragraph(f"   {launch['mission_desc']}", style="Body Text").runs[0].font.size = Pt(9)
        doc.add_paragraph("")

    # Upcoming launches
    h = doc.add_heading(f"UPCOMING LAUNCHES ({len(upcoming)})", level=1)
    h.runs[0].font.color.rgb = RGBColor(0x00, 0x80, 0x00)
    for launch in upcoming:
        write_launch(doc, launch, is_upcoming=True)

    # Page break
    p = doc.add_paragraph()
    run = p.add_run()
    br = OxmlElement('w:br')
    br.set(qn('w:type'), 'page')
    run._r.append(br)

    # Recent launches
    h = doc.add_heading(f"RECENT LAUNCHES ({len(recent)})", level=1)
    h.runs[0].font.color.rgb = RGBColor(0x1F, 0x77, 0xB4)
    for launch in recent:
        write_launch(doc, launch, is_upcoming=False)

    # Quick overview table
    p = doc.add_paragraph()
    run = p.add_run()
    br = OxmlElement('w:br')
    br.set(qn('w:type'), 'page')
    run._r.append(br)

    doc.add_heading("QUICK OVERVIEW — ALL LAUNCHES", 0).alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph("")

    all_launches = [("UPCOMING", l) for l in upcoming] + [("RECENT", l) for l in recent]
    cols = ["#", "Type", "Flag", "Launch Name", "Agency", "Rocket", "Date", "Status", "Mission Type", "Orbit", "Location"]
    tbl = doc.add_table(rows=1 + len(all_launches), cols=len(cols))
    tbl.style = "Table Grid"
    for i, h in enumerate(cols):
        tbl.rows[0].cells[i].text = h
        tbl.rows[0].cells[i].paragraphs[0].runs[0].bold = True
        tbl.rows[0].cells[i].paragraphs[0].runs[0].font.size = Pt(8)

    for i, (ltype, launch) in enumerate(all_launches, 1):
        row = tbl.rows[i].cells
        row[0].text = str(i)
        row[1].text = ltype
        row[2].text = launch["flag"]
        row[3].text = launch["name"][:50]
        row[4].text = launch["agency"][:25]
        row[5].text = launch["rocket"][:20]
        row[6].text = launch["net"][:16]
        row[7].text = launch["status_short"]
        row[8].text = launch["mission_type"][:20]
        row[9].text = launch["orbit"][:15]
        row[10].text = launch["location"][:25]
        for cell in row:
            for para in cell.paragraphs:
                for run in para.runs:
                    run.font.size = Pt(7)

    filename = f"Rocket_Launches_{now.strftime('%Y%m%d_%H%M%S')}.docx"
    filepath = os.path.join(DOCS_DIR, filename)
    doc.save(filepath)
    return filepath

def run():
    print(f"\n{'='*55}")
    print("  ATLAS ROCKET LAUNCH TRACKER")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*55}\n")

    upcoming_raw = fetch_launches(UPCOMING_URL, "Upcoming Launches")
    recent_raw   = fetch_launches(RECENT_URL,   "Recent Launches")

    upcoming = [parse_launch(l) for l in upcoming_raw]
    recent   = [parse_launch(l) for l in recent_raw]

    # Sort to prioritize Indian launches at the top
    def is_indian_launch(launch):
        return launch['country'] in ['IND', 'India'] or 'India' in launch['agency']
    
    upcoming.sort(key=lambda x: (not is_indian_launch(x), x['net']))
    recent.sort(key=lambda x: (not is_indian_launch(x), x['net']), reverse=True)

    # ── Save to ATLAS database ────────────────────────────────────────────────
    try:
        import sys
        sys.path.insert(0, os.path.dirname(BASE_DIR))
        from atlas_db import init_db, save_launches, get_launch_stats
        init_db()
        new_count, status_changes = save_launches(upcoming, recent)
        if status_changes > 0:
            print(f"\n[!] {status_changes} LAUNCH STATUS CHANGES DETECTED!")
        db_stats = get_launch_stats()
        print(f"[DB] Total in database: {db_stats['total_launches']} launches")
    except Exception as e:
        print(f"[!] DB save error: {e}")
        new_count, status_changes = 0, 0
    # ─────────────────────────────────────────────────────────────────────────

    # Print summary to console
    print(f"\n{'='*55}")
    print(f"  UPCOMING LAUNCHES ({len(upcoming)})")
    print(f"{'='*55}")
    for l in upcoming[:20]:
        is_indian = l['country'] in ['IND', 'India'] or 'India' in l['agency']
        prefix = "⭐🇮🇳" if is_indian else "  "
        print(f"{prefix} {l['icon']} {l['flag']} {l['net']:<20} {l['name'][:45]}")
        print(f"     Agency: {l['agency']}  |  Rocket: {l['rocket']}  |  Status: {l['status_short']}")
        if l['mission_type']:
            print(f"     Mission: {l['mission_name']}  |  Type: {l['mission_type']}")
        if l['orbit']:
            print(f"     Orbit: {l['orbit']}  |  Site: {l['location']}")
        if l['probability'] is not None:
            print(f"     Go Probability: {l['probability']}%")
        if l['rocket_config'].get('total_launch_count', 0) > 0:
            rc = l['rocket_config']
            print(f"     Rocket History: {rc['successful_launches']}/{rc['total_launch_count']} successful")
        if is_indian:
            print(f"     ⚡ INDIAN LAUNCH - PRIORITY TRACKING ⚡")
        print()

    print(f"\n{'='*55}")
    print(f"  RECENT LAUNCHES ({len(recent)})")
    print(f"{'='*55}")
    for l in recent[:10]:
        is_indian = l['country'] in ['IND', 'India'] or 'India' in l['agency']
        prefix = "⭐🇮🇳" if is_indian else "  "
        print(f"{prefix} {l['icon']} {l['flag']} {l['net']:<20} {l['name'][:45]}")
        print(f"     Agency: {l['agency']}  |  Rocket: {l['rocket']}  |  Status: {l['status_short']}")
        if l['mission_type']:
            print(f"     Mission: {l['mission_name']}  |  Type: {l['mission_type']}")
        if l['orbit']:
            print(f"     Orbit: {l['orbit']}  |  Site: {l['location']}")
        if l['fail_reason']:
            print(f"     ❌ Failure Reason: {l['fail_reason']}")
        if is_indian:
            print(f"     ⚡ INDIAN LAUNCH - PRIORITY TRACKING ⚡")
        print()

    print(f"\n[*] Generating report...")
    report_path = generate_report(upcoming, recent)
    print(f"[+] Report saved: {report_path}")
    
    # Count Indian launches
    indian_upcoming = sum(1 for l in upcoming if l['country'] in ['IND', 'India'] or 'India' in l['agency'])
    indian_recent = sum(1 for l in recent if l['country'] in ['IND', 'India'] or 'India' in l['agency'])
    
    print(f"\n[+] Total upcoming : {len(upcoming)}")
    print(f"[+] Total recent   : {len(recent)}")
    print(f"[+] 🇮🇳 Indian upcoming : {indian_upcoming}")
    print(f"[+] 🇮🇳 Indian recent   : {indian_recent}")
    if status_changes > 0:
        print(f"[!] Status changes : {status_changes} (check DB for details)")
    print(f"{'='*55}")

if __name__ == "__main__":
    run()
