# Indian Satellite Tracking - Enhanced Features

## Overview
The satellite tracker now includes special highlighting and detailed tracking of Indian satellites crossing Pakistani airspace, with focus on imagery/reconnaissance satellites.

## Enhanced Report Features

### 1. Executive Summary
- **Indian Satellites Detected**: Shows total crossings and unique Indian satellites
- **Indian Imagery Satellites**: Separate count for reconnaissance/observation satellites
- Highlighted in **orange color** for easy identification

### 2. Indian Satellite Activity Section (🇮🇳)
Dedicated section showing:
- **All Indian satellites** detected during the day
- **Satellite type** (Earth Observation, Radar/SAR, etc.)
- **Number of crossings** per satellite
- **Primary purpose** with detailed descriptions:
  - **CARTOSAT**: High-resolution Earth imaging for cartography, urban planning, and military reconnaissance
  - **RESOURCESAT**: Natural resource monitoring, agriculture, forestry, and land use mapping
  - **RISAT**: All-weather Radar imaging (SAR) for surveillance, disaster monitoring, and military applications

### 3. Indian Imagery Satellites - Detailed Border Crossings (📷)
For each Indian reconnaissance/imagery satellite:

#### Detailed Information:
- Entry time (UTC)
- **Entry point coordinates** (latitude/longitude)
- Exit time (UTC)
- **Duration over Pakistan** (minutes)
- **Maximum altitude** (km)
- **Direction of travel** (N→S, S→N, E→W, W→E)
- Owner/Operator (ISRO)

#### Border Region Description:
- Identifies which border region the satellite entered from:
  - Northwest (Afghanistan/China border)
  - Northeast (China/Kashmir border)
  - East (Indian border - Punjab/Rajasthan sector)
  - West (Iran/Afghanistan border)
  - South (Arabian Sea/Indian Ocean)

#### Visual Map:
- **ASCII map of Pakistan** with actual border outline
- **Entry point** marked with ▲
- **Exit point** marked with ▼
- **Satellite path** shown with dashed line (· - |)
- **Major cities** marked with ●
- **Legend** explaining all symbols

### 4. Country Breakdown
- Indian satellites **highlighted in orange and bold**
- Easy comparison with other countries

### 5. Full Crossing List
- Indian satellites **highlighted in orange and bold** in the main table
- Quick visual identification among all satellites

## Example Indian Satellites Tracked

### April 27, 2026 Detection:
- **8 Indian satellite crossings** detected
- **3 unique satellites**: CARTOSAT-2, CARTOSAT-3, RESOURCESAT-2, RESOURCESAT-2A
- **All Earth Observation** type (high-resolution imaging capability)

### Sample Crossing Details:
**CARTOSAT-3** (Earth Observation)
- Entry: 04:36 UTC at 26.32°N, 76.92°E
- Entered from: East (Indian border - Punjab/Rajasthan sector)
- Direction: Traveling across Pakistan
- Duration: 1 minute
- Purpose: High-resolution Earth imaging for cartography and military reconnaissance

## Map Visualization

The ASCII map shows:
```
█ = Pakistan Border (actual outline)
▲ = Entry Point (with coordinates)
▼ = Exit Point (with coordinates)
· - | = Satellite Path (dashed line showing trajectory)
● = Major Cities (ISB, LHR, KHI, QTA, PSH, FSD, MUL)
```

## Security Implications

### High-Resolution Imaging Satellites:
- **CARTOSAT series**: 0.25-1m resolution - can identify vehicles, buildings, infrastructure
- **RESOURCESAT series**: 5-56m resolution - monitors agriculture, resources, land use
- **RISAT series**: All-weather radar imaging - works day/night, through clouds

### Monitoring Recommendations:
1. Track frequency of passes over sensitive areas
2. Monitor duration anomalies (longer than usual = potential detailed imaging)
3. Correlate with ground activities or events
4. Note clustering of multiple satellites over same region

## Anomaly Detection

The system automatically detects:
- **Long Duration**: Indian satellites taking 50%+ longer than historical average
- **Increased Frequency**: More passes than usual (potential surveillance campaign)

## Files Generated

Each daily report includes:
- Complete Indian satellite activity summary
- Detailed border crossing maps for imagery satellites
- Purpose and capability descriptions
- Entry/exit coordinates and trajectories

## Usage

Reports are automatically generated with Indian satellite highlighting when you run:
```bash
python satellite_tracker_v2.py
```

Or from the dashboard: Click "RUN SCAN" on Satellite Tracker tab
