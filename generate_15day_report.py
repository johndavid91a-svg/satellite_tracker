"""
Generate a comprehensive 15-day satellite surveillance report
"""
import json
import os
import sys
from datetime import datetime, timedelta
from collections import Counter

# Resolve paths from this script's location so the report works no matter
# where the project is moved. SCRIPT_DIR is the project root; the data lives
# in the Satellite_Tracker subfolder and the output goes into documents/.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.join(SCRIPT_DIR, "Satellite_Tracker")
HISTORY_FILE = os.path.join(BASE_DIR, "satellite_history.json")
ANOMALY_FILE = os.path.join(BASE_DIR, "anomalies.json")

OUTPUT_DIR = os.path.join(SCRIPT_DIR, "Satellite_Tracker", "documents")
os.makedirs(OUTPUT_DIR, exist_ok=True)
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "Pakistan_15Day_Surveillance_Report.docx")

if not os.path.isfile(HISTORY_FILE):
    print(f"[!] satellite_history.json not found at: {HISTORY_FILE}")
    print(f"[!] Run a daily scan first (Satellite_Tracker/satellite_tracker_v2.py).")
    sys.exit(1)

print("[*] Loading satellite history data...")
with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
    history = json.load(f)

print("[*] Loading anomaly data...")
if os.path.isfile(ANOMALY_FILE):
    with open(ANOMALY_FILE, 'r', encoding='utf-8') as f:
        all_anomalies = json.load(f)
else:
    print(f"[!] anomalies.json missing — continuing with empty anomaly set.")
    all_anomalies = []

# Get all dates and sort them
all_dates = sorted(history.keys())
print(f"[+] Found {len(all_dates)} days of data: {all_dates[0]} to {all_dates[-1]}")

# Get last 15 days
last_15_dates = all_dates[-15:] if len(all_dates) >= 15 else all_dates
print(f"[+] Processing last {len(last_15_dates)} days: {last_15_dates[0]} to {last_15_dates[-1]}")

# Filter anomalies for last 15 days
period_anomalies = [a for a in all_anomalies if a.get('date') in last_15_dates]
print(f"[+] Found {len(period_anomalies)} anomalies in the last {len(last_15_dates)} days")

# Aggregate statistics
total_crossings = 0
all_satellites = set()
country_counts = Counter()
type_counts = Counter()
owner_counts = Counter()
anomaly_types = Counter()
anomaly_satellites = Counter()
anomaly_severity = Counter()
daily_stats = []

for date in last_15_dates:
    day_data = history[date]
    crossings = day_data.get('crossings', [])
    total_crossings += len(crossings)
    
    day_sats = set()
    day_countries = Counter()
    day_types = Counter()
    
    for crossing in crossings:
        sat_id = crossing['norad_id']
        all_satellites.add(sat_id)
        day_sats.add(sat_id)
        
        country = crossing.get('country', 'Unknown')
        sat_type = crossing.get('type', 'Unknown')
        owner = crossing.get('owner', 'Unknown')
        
        country_counts[country] += 1
        type_counts[sat_type] += 1
        owner_counts[owner] += 1
        day_countries[country] += 1
        day_types[sat_type] += 1
    
    # Count anomalies for this day
    day_anomalies = [a for a in period_anomalies if a.get('date') == date]
    
    daily_stats.append({
        'date': date,
        'crossings': len(crossings),
        'unique_sats': len(day_sats),
        'anomalies': len(day_anomalies),
        'top_country': day_countries.most_common(1)[0] if day_countries else ('N/A', 0),
        'top_type': day_types.most_common(1)[0] if day_types else ('N/A', 0)
    })

# Analyze anomalies
for anomaly in period_anomalies:
    anomaly_types[anomaly.get('type', 'Unknown')] += 1
    anomaly_satellites[anomaly.get('satellite', 'Unknown')] += 1
    anomaly_severity[anomaly.get('severity', 'Unknown')] += 1

print(f"[+] Total crossings: {total_crossings}")
print(f"[+] Unique satellites: {len(all_satellites)}")
print(f"[+] Total anomalies: {len(period_anomalies)}")

# Create Word document
try:
    from docx import Document
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.style import WD_STYLE_TYPE
except ImportError:
    print("[!] python-docx not installed. Installing...")
    import subprocess
    subprocess.check_call(['pip', 'install', 'python-docx'])
    from docx import Document
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH

print("[*] Creating Word document...")
doc = Document()

# Title
title = doc.add_heading("PAKISTAN AIRSPACE SURVEILLANCE", 0)
title.alignment = WD_ALIGN_PARAGRAPH.CENTER
title.runs[0].font.color.rgb = RGBColor(0, 51, 102)

subtitle = doc.add_paragraph(f"15-Day Comprehensive Report")
subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
subtitle.runs[0].bold = True
subtitle.runs[0].font.size = Pt(14)

date_range = doc.add_paragraph(f"Period: {last_15_dates[0]} to {last_15_dates[-1]}")
date_range.alignment = WD_ALIGN_PARAGRAPH.CENTER
date_range.runs[0].font.size = Pt(12)

generated = doc.add_paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
generated.alignment = WD_ALIGN_PARAGRAPH.CENTER
generated.runs[0].font.size = Pt(10)
generated.runs[0].italic = True

doc.add_paragraph("_" * 80)

# Executive Summary
doc.add_heading("EXECUTIVE SUMMARY", 1)
summary_para = doc.add_paragraph()
summary_para.add_run(f"Total Border Crossings: ").bold = True
summary_para.add_run(f"{total_crossings:,}\n")
summary_para.add_run(f"Unique Satellites Tracked: ").bold = True
summary_para.add_run(f"{len(all_satellites)}\n")
summary_para.add_run(f"Average Crossings per Day: ").bold = True
summary_para.add_run(f"{total_crossings / len(last_15_dates):.1f}\n")
summary_para.add_run(f"Monitoring Period: ").bold = True
summary_para.add_run(f"{len(last_15_dates)} days\n")
summary_para.add_run(f"Total Anomalies Detected: ").bold = True
summary_para.add_run(f"{len(period_anomalies)}\n")
summary_para.add_run(f"High Severity Anomalies: ").bold = True
high_severity = sum(1 for a in period_anomalies if a.get('severity') == 'HIGH')
summary_para.add_run(f"{high_severity}\n")

# Daily Statistics Table
doc.add_heading("DAILY STATISTICS", 1)
table = doc.add_table(rows=1, cols=6)
table.style = 'Light Grid Accent 1'
hdr_cells = table.rows[0].cells
hdr_cells[0].text = 'Date'
hdr_cells[1].text = 'Crossings'
hdr_cells[2].text = 'Unique Sats'
hdr_cells[3].text = 'Anomalies'
hdr_cells[4].text = 'Top Country'
hdr_cells[5].text = 'Top Type'

for stat in daily_stats:
    row_cells = table.add_row().cells
    row_cells[0].text = stat['date']
    row_cells[1].text = str(stat['crossings'])
    row_cells[2].text = str(stat['unique_sats'])
    row_cells[3].text = str(stat['anomalies'])
    row_cells[4].text = f"{stat['top_country'][0]} ({stat['top_country'][1]})"
    row_cells[5].text = f"{stat['top_type'][0]} ({stat['top_type'][1]})"

# Country Analysis
doc.add_page_break()
doc.add_heading("COUNTRY-WISE ANALYSIS", 1)
doc.add_paragraph(f"Satellite crossings by country of origin over {len(last_15_dates)} days:")

country_table = doc.add_table(rows=1, cols=3)
country_table.style = 'Light Grid Accent 1'
hdr = country_table.rows[0].cells
hdr[0].text = 'Country'
hdr[1].text = 'Total Crossings'
hdr[2].text = 'Percentage'

for country, count in country_counts.most_common():
    row = country_table.add_row().cells
    row[0].text = country
    row[1].text = str(count)
    row[2].text = f"{(count/total_crossings*100):.1f}%"

# Satellite Type Analysis
doc.add_heading("SATELLITE TYPE ANALYSIS", 1)
doc.add_paragraph(f"Breakdown by satellite mission type:")

type_table = doc.add_table(rows=1, cols=3)
type_table.style = 'Light Grid Accent 1'
hdr = type_table.rows[0].cells
hdr[0].text = 'Type'
hdr[1].text = 'Total Crossings'
hdr[2].text = 'Percentage'

for sat_type, count in type_counts.most_common():
    row = type_table.add_row().cells
    row[0].text = sat_type
    row[1].text = str(count)
    row[2].text = f"{(count/total_crossings*100):.1f}%"

# Anomaly Analysis Section
doc.add_page_break()
doc.add_heading("⚠️ ANOMALY DETECTION ANALYSIS", 1)

anomaly_summary = doc.add_paragraph()
anomaly_summary.add_run(f"Total Anomalies Detected: ").bold = True
anomaly_summary.add_run(f"{len(period_anomalies)}\n")
anomaly_summary.add_run(f"High Severity: ").bold = True
anomaly_summary.add_run(f"{anomaly_severity.get('HIGH', 0)} | ")
anomaly_summary.add_run(f"Medium Severity: ").bold = True
anomaly_summary.add_run(f"{anomaly_severity.get('MEDIUM', 0)}\n\n")

doc.add_paragraph("Anomalies indicate unusual satellite behavior such as longer-than-normal crossing durations or increased crossing frequency, which may warrant further investigation.")

# Anomaly by Type
doc.add_heading("Anomaly Types", 2)
anomaly_type_table = doc.add_table(rows=1, cols=3)
anomaly_type_table.style = 'Light Grid Accent 1'
hdr = anomaly_type_table.rows[0].cells
hdr[0].text = 'Anomaly Type'
hdr[1].text = 'Count'
hdr[2].text = 'Percentage'

for anom_type, count in anomaly_types.most_common():
    row = anomaly_type_table.add_row().cells
    row[0].text = anom_type.replace('_', ' ').title()
    row[1].text = str(count)
    row[2].text = f"{(count/len(period_anomalies)*100):.1f}%"

# Satellites with Most Anomalies
doc.add_heading("Satellites with Most Anomalies", 2)
sat_anomaly_table = doc.add_table(rows=1, cols=2)
sat_anomaly_table.style = 'Light Grid Accent 1'
hdr = sat_anomaly_table.rows[0].cells
hdr[0].text = 'Satellite'
hdr[1].text = 'Anomaly Count'

for sat, count in anomaly_satellites.most_common(10):
    row = sat_anomaly_table.add_row().cells
    row[0].text = sat
    row[1].text = str(count)

# Detailed Anomaly List
doc.add_heading("Detailed Anomaly Records", 2)
doc.add_paragraph(f"Complete list of all {len(period_anomalies)} anomalies detected during the monitoring period:")

for i, anomaly in enumerate(period_anomalies, 1):
    para = doc.add_paragraph(style='List Number')
    
    # Severity indicator
    severity = anomaly.get('severity', 'UNKNOWN')
    severity_symbol = "🔴" if severity == "HIGH" else "🟡"
    
    para.add_run(f"{severity_symbol} [{severity}] ").bold = True
    para.add_run(f"{anomaly.get('satellite', 'Unknown')} ")
    para.add_run(f"({anomaly.get('owner', 'Unknown')}) - ").italic = True
    para.add_run(f"{anomaly.get('type', 'Unknown').replace('_', ' ').title()}\n")
    
    details_para = doc.add_paragraph(style='List Bullet 2')
    details_para.add_run(f"Date: {anomaly.get('date', 'Unknown')} | ")
    details_para.add_run(f"{anomaly.get('details', 'No details available')}")
    
    crossing = anomaly.get('crossing', {})
    if crossing:
        time_para = doc.add_paragraph(style='List Bullet 2')
        time_para.add_run(f"Time: {crossing.get('entry_time', 'N/A')} to {crossing.get('exit_time', 'N/A')}")

# Operator Analysis
doc.add_page_break()
doc.add_heading("OPERATOR ANALYSIS", 1)
doc.add_paragraph(f"Top 15 satellite operators by crossing frequency:")

operator_table = doc.add_table(rows=1, cols=3)
operator_table.style = 'Light Grid Accent 1'
hdr = operator_table.rows[0].cells
hdr[0].text = 'Operator'
hdr[1].text = 'Total Crossings'
hdr[2].text = 'Percentage'

for owner, count in owner_counts.most_common(15):
    row = operator_table.add_row().cells
    row[0].text = owner
    row[1].text = str(count)
    row[2].text = f"{(count/total_crossings*100):.1f}%"

# Key Findings
doc.add_page_break()
doc.add_heading("KEY FINDINGS", 1)

findings = doc.add_paragraph()
findings.add_run("1. Most Active Country: ").bold = True
top_country = country_counts.most_common(1)[0]
findings.add_run(f"{top_country[0]} with {top_country[1]} crossings ({top_country[1]/total_crossings*100:.1f}%)\n\n")

findings.add_run("2. Most Common Satellite Type: ").bold = True
top_type = type_counts.most_common(1)[0]
findings.add_run(f"{top_type[0]} with {top_type[1]} crossings ({top_type[1]/total_crossings*100:.1f}%)\n\n")

findings.add_run("3. Most Active Operator: ").bold = True
top_operator = owner_counts.most_common(1)[0]
findings.add_run(f"{top_operator[0]} with {top_operator[1]} crossings ({top_operator[1]/total_crossings*100:.1f}%)\n\n")

findings.add_run("4. Busiest Day: ").bold = True
busiest_day = max(daily_stats, key=lambda x: x['crossings'])
findings.add_run(f"{busiest_day['date']} with {busiest_day['crossings']} crossings\n\n")

findings.add_run("5. Quietest Day: ").bold = True
quietest_day = min(daily_stats, key=lambda x: x['crossings'])
findings.add_run(f"{quietest_day['date']} with {quietest_day['crossings']} crossings\n\n")

findings.add_run("6. Total Anomalies: ").bold = True
findings.add_run(f"{len(period_anomalies)} detected ({high_severity} high severity, {anomaly_severity.get('MEDIUM', 0)} medium severity)\n\n")

findings.add_run("7. Most Common Anomaly: ").bold = True
if anomaly_types:
    top_anomaly = anomaly_types.most_common(1)[0]
    findings.add_run(f"{top_anomaly[0].replace('_', ' ').title()} ({top_anomaly[1]} occurrences)\n\n")

findings.add_run("8. Satellite with Most Anomalies: ").bold = True
if anomaly_satellites:
    top_anom_sat = anomaly_satellites.most_common(1)[0]
    findings.add_run(f"{top_anom_sat[0]} with {top_anom_sat[1]} anomalies\n\n")

# Detailed Daily Breakdown
doc.add_page_break()
doc.add_heading("DETAILED DAILY BREAKDOWN", 1)

for date in last_15_dates:
    day_data = history[date]
    crossings = day_data.get('crossings', [])
    
    doc.add_heading(f"{date} ({len(crossings)} crossings)", 2)
    
    # Group by satellite
    sat_crossings = {}
    for crossing in crossings:
        sat_name = crossing['name']
        if sat_name not in sat_crossings:
            sat_crossings[sat_name] = []
        sat_crossings[sat_name].append(crossing)
    
    for sat_name, sat_crosses in sorted(sat_crossings.items()):
        para = doc.add_paragraph(style='List Bullet')
        para.add_run(f"{sat_name}").bold = True
        first_cross = sat_crosses[0]
        para.add_run(f" ({first_cross['country']}, {first_cross['type']}) - {len(sat_crosses)} crossing(s)")

# Footer
doc.add_page_break()
doc.add_heading("REPORT INFORMATION", 1)
info = doc.add_paragraph()
info.add_run("System: ").bold = True
info.add_run("ATLAS - Pakistan Border Satellite Surveillance\n")
info.add_run("Data Source: ").bold = True
info.add_run("SatNOGS Database + CelesTrak TLE Data\n")
info.add_run("Coverage: ").bold = True
info.add_run("Pakistan Airspace (60°E-77°E, 23°N-37°N)\n")
info.add_run("Tracking Method: ").bold = True
info.add_run("SGP4 Orbital Propagation\n")
info.add_run("Report Generated: ").bold = True
info.add_run(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

# Save document
print(f"[*] Saving document to: {OUTPUT_FILE}")
doc.save(OUTPUT_FILE)
print(f"[+] Report saved successfully!")
print(f"[+] Location: {OUTPUT_FILE}")
print(f"\n[✓] COMPLETE - 15-Day Report Generated")
