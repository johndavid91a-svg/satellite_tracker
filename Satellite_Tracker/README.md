# ATLAS Pakistan Border Satellite Tracker

## Auto-Backfill System

This tracker automatically maintains continuous daily satellite surveillance data starting from **April 26, 2026**.

### How It Works

1. **Always scans YESTERDAY** - When you run a scan today, it scans for yesterday's data
2. **Auto-detects missing dates** - Automatically finds and fills any gaps in the data
3. **Generates reports** - Creates a Word document for each scanned date
4. **Anomaly detection** - Compares against historical data to detect suspicious activity

### Usage

**From Dashboard:**
- Click "RUN SCAN" on the Satellite Tracker tab
- It will automatically scan yesterday and backfill any missing dates

**From Command Line:**
```bash
# Scan yesterday and backfill missing dates (default)
python satellite_tracker_v2.py

# Scan a specific date
python satellite_tracker_v2.py 2026-04-26

# Scan yesterday explicitly
python satellite_tracker_v2.py yesterday
```

### What Gets Tracked

- **60+ satellites** including:
  - Earth Observation (Landsat, Sentinel, WorldView, etc.)
  - Chinese reconnaissance (Gaofen, Yaogan series)
  - Indian satellites (Cartosat, RISAT, Resourcesat)
  - Weather satellites (NOAA, MetOp, FengYun)
  - Space stations (ISS, Tiangong)

- **Pakistan Border Region**: 23.5°N–37.5°N, 60.5°E–77.5°E

### Anomaly Detection

The system detects:
- **Long Duration**: Satellites taking 50%+ longer than historical average
- **Increased Frequency**: Satellites crossing more often than usual

### Files Generated

- `documents/Pakistan_Border_Surveillance_YYYY-MM-DD.docx` - Daily reports
- `satellite_history.json` - Complete historical database
- `anomalies.json` - All detected anomalies

### Data Retention

- **TLE Age Limit**: 7 days (older dates are skipped due to orbital data accuracy)
- **Baseline Start**: April 26, 2026
- **Continuous tracking**: From April 26, 2026 onwards

### Example Scenarios

**Scenario 1: Daily scanning**
- Today: April 27 → Scans April 26 ✓
- Tomorrow: April 28 → Scans April 27 ✓
- Next day: April 29 → Scans April 28 ✓

**Scenario 2: Missed 3 days**
- Last scan: April 26
- Today: April 30
- System automatically scans: April 27, 28, 29 (3 reports generated)

**Scenario 3: Too old**
- Last scan: April 20
- Today: April 30 (10 days gap)
- System scans: April 24-29 only (skips April 21-23 due to TLE age)

### Dashboard Stats

- **CROSSINGS**: Total border crossings detected
- **SATELLITES**: Unique satellites that crossed
- **ANOMALIES**: Suspicious activities detected
- **TRACKED**: Total satellites being monitored
