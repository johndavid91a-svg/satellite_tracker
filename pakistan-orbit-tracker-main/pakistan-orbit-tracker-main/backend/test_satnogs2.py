import httpx, re

r = httpx.get("https://db.satnogs.org/api/tle/?format=json&page=1&page_size=2000", timeout=30)
print("Status:", r.status_code, "bytes:", len(r.content))
data = r.json()
print("Total records:", len(data))

# Check name patterns
patterns = {
    "stations": ["ISS", "ZARYA", "TIANHE", "CSS", "TIANGONG"],
    "starlink":  ["STARLINK"],
    "gps-ops":   ["GPS", "NAVSTAR"],
    "weather":   ["NOAA", "METEOR", "METOP", "GOES"],
    "active":    [],  # catch-all
}

for cat, pats in patterns.items():
    if not pats:
        continue
    matches = [d for d in data if any(p in d["tle0"].upper() for p in pats)]
    print(f"{cat}: {len(matches)} matches — e.g. {[m['tle0'] for m in matches[:3]]}")
