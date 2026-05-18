# Visual Satellite Path Maps - Complete Guide

## Overview
The satellite tracker generates **visual maps with Google Maps satellite imagery** showing all satellite paths overlaid on actual satellite photos of Pakistan.

## Features

### 1. Google Maps Satellite Imagery Background
- **Real satellite imagery** from Esri World Imagery provider
- **High-resolution** terrain and geographic features visible
- **Actual ground view** of Pakistan's landscape
- Major cities, rivers, mountains clearly visible
- **Professional quality** suitable for intelligence briefings

### 2. Satellite Paths
- **Entry points** marked with ▲ (large triangles)
- **Exit points** marked with ▼ (large triangles)
- **Solid bright lines** showing satellite trajectory across Pakistan
- **Color-coded** paths (different bright color for each satellite)
- **High contrast** - Black outlines on bright colors for visibility
- **Satellite names** labeled on paths

### 3. One Map Per Country
Separate visual maps are generated for each country with imagery satellites:
- 🇮🇳 **India** - CARTOSAT, RESOURCESAT, RISAT series
- 🇨🇳 **China** - Gaofen, Yaogan series
- 🇺🇸 **USA** - Landsat, WorldView series

### 4. Map Details
Each map shows:
- **Google Maps satellite imagery** as background
- **All crossings** for that country on one map
- **Entry/exit coordinates** for each satellite
- **Path trajectories** showing direction of travel
- **Major cities** marked with bright yellow dots (Islamabad as red star)
- **Legend** explaining symbols
- **Date** of surveillance
- **High-resolution** (200 DPI) for printing

## Report Structure

### For Each Country with Imagery Satellites:

1. **Country Header** (with flag emoji)
   - Example: "🇮🇳 INDIAN IMAGERY SATELLITES"

2. **Visual Map** (full-page image)
   - Shows ALL satellite paths for that country
   - Pakistan outline with cities
   - Color-coded paths with entry/exit points

3. **Summary Table**
   - Satellite name
   - Type (Earth Observation, Radar/SAR)
   - Entry time
   - Duration over Pakistan
   - Entry coordinates
   - Direction of travel

## Example: April 27, 2026

### India (8 crossings)
- **Map**: `map_India_2026-04-27.png` (352 KB)
- **Satellites**: CARTOSAT-2, CARTOSAT-3, RESOURCESAT-2, RESOURCESAT-2A
- **All 8 paths** shown on one map with different colors

### China (4 crossings)
- **Map**: `map_China_2026-04-27.png` (286 KB)
- **Satellites**: Gaofen-1, Gaofen-3, Yaogan-14, Yaogan-26
- **All 4 paths** overlaid on Pakistan map

### USA (2 crossings)
- **Map**: `map_USA_2026-04-27.png` (278 KB)
- **Satellites**: Landsat-8, Landsat-9
- **Both paths** shown together

## Map Legend

```
▲ = Entry Point (where satellite entered Pakistani airspace)
▼ = Exit Point (where satellite exited Pakistani airspace)
- - = Satellite Path (dashed line showing trajectory)
● = Major Cities
```

## Color Coding

Each satellite gets a unique bright color optimized for visibility on satellite imagery:
- Red (#ff0000)
- Green (#00ff00)
- Cyan (#00ffff)
- Magenta (#ff00ff)
- Yellow (#ffff00)
- Orange (#ff6600)
- Pink (#ff0099)
- Aqua (#00ff99)
- Purple (#9900ff)
- Gold (#ff9900)

All paths have **black outlines** for maximum contrast against the satellite imagery background.

## Technical Details

### Map Generation
- **Library**: Matplotlib + Contextily (Python)
- **Basemap**: Esri World Imagery (Google Maps quality satellite imagery)
- **Resolution**: 200 DPI (high quality for printing)
- **Size**: 16x12 inches
- **Format**: PNG images
- **Location**: `documents/map_[Country]_[Date].png`
- **Zoom Level**: 6 (optimal balance between detail and coverage)

### Satellite Imagery Provider
- **Source**: Esri World Imagery via Contextily
- **Quality**: High-resolution satellite photos
- **Coverage**: Global, including Pakistan
- **Updates**: Regularly updated imagery
- **Attribution**: Not required for internal use

### Pakistan Coverage Area
- **Longitude**: 60.5°E to 77.5°E
- **Latitude**: 23.5°N to 37.8°N
- **Coordinate System**: EPSG:4326 (WGS84)

## Benefits

### 1. Visual Intelligence
- **See patterns** - Multiple satellites from same country
- **Identify clusters** - Concentrated surveillance areas
- **Track routes** - Common entry/exit points

### 2. Strategic Analysis
- **Border security** - Which borders are most crossed
- **City coverage** - Which cities are under surveillance
- **Frequency patterns** - Daily, weekly trends

### 3. Reporting
- **Professional presentation** - Visual maps for briefings
- **Easy understanding** - Non-technical stakeholders
- **Evidence documentation** - Clear visual proof

## Files Generated

For each scan date, the following files are created:

### Report Document
- `Pakistan_Border_Surveillance_YYYY-MM-DD.docx`
- Contains all maps embedded
- Typical size: 500 KB - 1 MB (with maps)

### Map Images
- `map_India_YYYY-MM-DD.png`
- `map_China_YYYY-MM-DD.png`
- `map_USA_YYYY-MM-DD.png`
- `map_Europe_YYYY-MM-DD.png` (if applicable)
- `map_France_YYYY-MM-DD.png` (if applicable)

## Usage

Maps are automatically generated when you run:
```bash
python satellite_tracker_v2.py
```

Or from the dashboard: Click "RUN SCAN" on Satellite Tracker tab

## Example Analysis

### April 27, 2026 Findings:

**Indian Activity (High)**
- 8 crossings by 4 satellites
- All Earth Observation type
- Entry points: Eastern border (Punjab/Rajasthan sector)
- Pattern: Regular surveillance passes

**Chinese Activity (Moderate)**
- 4 crossings by reconnaissance satellites
- Mix of optical and radar imaging
- Entry points: Northern and western borders
- Pattern: Strategic monitoring

**US Activity (Low)**
- 2 crossings by Landsat satellites
- Earth observation (civilian)
- Entry points: Various
- Pattern: Routine environmental monitoring

## Security Implications

The visual maps help identify:
1. **Surveillance intensity** - Number of overlapping paths
2. **Target areas** - Paths converging on specific regions
3. **Coordination** - Multiple satellites from same country
4. **Timing patterns** - When surveillance occurs

## Future Enhancements

Potential additions:
- Heat maps showing most-surveilled areas
- Time-lapse animations of satellite movements
- 3D visualization with altitude
- Comparison maps (day-to-day changes)
