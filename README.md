<<<<<<< HEAD
# satellite_tracker
=======
# 🛰️ Space Tracker - Pakistan Airspace Surveillance System

A satellite surveillance system focused on **high-resolution Earth-observation satellites**
(panchromatic GSD ≤ 1 m) that cross Pakistan's airspace. Rocket launches are tracked
alongside; the historical mixed-category tracker is preserved.

## 📋 Overview

**Space Tracker** provides:
- Real-time tracking of sub-metre EO satellites over Pakistan airspace
- **15-day forecast** of overflights + **daily-refreshed "blind windows"** (when nothing is overhead) — see [docs/forecast_15day.md](docs/forecast_15day.md)
- Indian (ISRO) satellites highlighted in red across all surfaces
- Daily TLE refresh from CelesTrak (`gp.php`)
- Rolling 30-day backups of state
- Rocket launch monitoring worldwide
- Interactive web-based visualisation
- Word + JSON reports

## 🚀 Features

### 0. **15-Day HiRes EO Forecast** *(new — FEAT-001)*
- Daily-refreshed prediction of every ≤ 1 m EO satellite passing over Pakistan over the next 15 days
- Per-day **blind windows** (UTC intervals when no satellite is overhead)
- Output: Word doc + `forecast_15day.json` + Tk dashboard tab + `/api/forecast`
- See [`docs/forecast_15day.md`](docs/forecast_15day.md) for the full design + JSON contract
- Run manually from the **15-Day Forecast** tab, or schedule `Satellite_Tracker/Run Daily Forecast.bat` in Windows Task Scheduler

### 1. **Satellite Border Surveillance** *(legacy day-by-day scan, still supported)*
- Curated catalog of 65 sub-metre EO satellites (was: 50+ mixed categories)
- Real-time position calculation (sgp4 lib when installed, fallback Kepler propagator)
- Automated anomaly detection (long duration, increased frequency)
- Daily comprehensive reports in Word format
- Historical data tracking and analysis
- **Rolling 30-day backups** of `satellite_history.json`, `anomalies.json`, `forecast_15day.json`, and `documents/`

### 2. **Rocket Launch Tracking**
- Monitors upcoming and recent launches worldwide
- Highlights launches from specific countries (India, Pakistan, etc.)
- Detailed launch information and status
- Automated report generation

### 3. **Interactive Web Interface**
- Pakistan Orbit Tracker (React + Vite frontend)
- Real-time satellite visualization
- Multiple satellite categories (ISS, Starlink, Weather, etc.)
- FastAPI backend for TLE data

## 📁 Project Structure

```
Space_Tracker/
├── Satellite_Tracker/          # Satellite surveillance module
│   ├── satellite_tracker_v2.py # Main tracking script
│   ├── documents/              # Generated daily reports
│   ├── satellite_history.json  # Historical crossing data
│   ├── anomalies.json          # Detected anomalies
│   └── *.html                  # Interactive maps
│
├── Rocket_Launches/            # Rocket launch tracking module
│   ├── launch_tracker.py       # Launch monitoring script
│   └── documents/              # Launch reports
│
├── pakistan-orbit-tracker-main/ # Web-based tracker
│   ├── backend/                # FastAPI backend
│   │   └── main.py            # API endpoints
│   ├── src/                    # React frontend
│   └── public/                 # Static assets
│
├── space_tracker_app.py        # Main GUI application
├── generate_15day_report.py    # Report generator
└── Launch Space Tracker.bat    # Windows launcher
```

## 🛠️ Installation

### Prerequisites
- Python 3.8+
- Node.js 16+ (for web interface)
- Git

### Python Dependencies
```bash
cd Satellite_Tracker
pip install -r requirements.txt
```

Key packages:
- `sgp4` - Satellite orbit propagation
- `requests` - API calls
- `python-docx` - Report generation
- `matplotlib` - Visualization
- `fastapi` - Backend API
- `uvicorn` - ASGI server

### Frontend Setup
```bash
cd pakistan-orbit-tracker-main/pakistan-orbit-tracker-main
npm install
```

## 🚀 Usage

### Option 1: GUI Application (Recommended)
```bash
python space_tracker_app.py
```
Or double-click `Launch Space Tracker.bat`

### Option 2: Command Line

**Satellite Tracking:**
```bash
cd Satellite_Tracker
python satellite_tracker_v2.py
```

**Rocket Launch Tracking:**
```bash
cd Rocket_Launches
python launch_tracker.py
```

**Web Interface:**
```bash
# Terminal 1 - Backend
cd pakistan-orbit-tracker-main/pakistan-orbit-tracker-main/backend
uvicorn main:app --reload --host 127.0.0.1 --port 8000

# Terminal 2 - Frontend
cd pakistan-orbit-tracker-main/pakistan-orbit-tracker-main
npm run dev
```

### Generate 15-Day Report
```bash
python generate_15day_report.py
```
Report will be saved to Desktop as `Pakistan_15Day_Surveillance_Report.docx`

## 📊 Data Sources

- **TLE Data**: SatNOGS Database + CelesTrak
- **Satellite Metadata**: SatNOGS API
- **Rocket Launches**: Launch Library 2 API
- **Border Data**: PakData GISData (GeoJSON)

## 🔍 Anomaly Detection

The system automatically detects:
- **Long Duration**: Satellites staying in airspace longer than normal (>50% above average)
- **Increased Frequency**: Satellites crossing more often than usual (>100% increase)

Severity Levels:
- 🔴 **HIGH**: Significant deviation from normal patterns
- 🟡 **MEDIUM**: Moderate deviation requiring monitoring

## 📈 Reports

### Daily Reports Include:
- Total border crossings
- Unique satellites tracked
- Country-wise analysis
- Satellite type breakdown
- Anomaly detection results
- Detailed crossing logs

### 15-Day Comprehensive Report:
- Executive summary
- Daily statistics table
- Country and operator analysis
- Complete anomaly records
- Key findings and insights

## 🌍 Coverage Area

**Pakistan Airspace:**
- Longitude: 60°E to 77°E
- Latitude: 23°N to 37°N

## 🛰️ Tracked Satellites

Categories include:
- Space Stations (ISS, Tiangong)
- Weather Satellites (NOAA, METOP, Fengyun)
- Earth Observation (Landsat, Sentinel, Cartosat)
- Navigation (GPS, GLONASS, Galileo, BeiDou)
- Reconnaissance (Yaogan, Gaofen)
- Communications (Geostationary)

## 📝 License

This project is for educational and research purposes.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit pull requests.

## 📧 Contact

For questions or support, please open an issue on GitHub.

## 🙏 Acknowledgments

- CelesTrak for TLE data
- SatNOGS for satellite database
- Launch Library 2 for launch data
- PakData for GeoJSON border data

---

**Last Updated:** May 2026  
**Version:** 2.0  
**Status:** Active Development
>>>>>>> 5c53713 (Initial commit: ATLAS satellite tracker)
