import httpx, json

# Load catalog
cat = httpx.get(
    "https://raw.githubusercontent.com/satvisorcom/satvisor-data/master/catalog/satnogs.json",
    timeout=15
).json()

# Load TLE for starlink to get NORAD IDs
tle_r = httpx.get("http://127.0.0.1:8001/api/tle?category=starlink", timeout=30)
lines = [l.strip() for l in tle_r.text.splitlines() if l.strip()]

# Extract NORAD IDs from TLE line1 (cols 2-7)
found = missing = 0
for i in range(0, min(len(lines)-2, 60), 3):
    l1 = lines[i+1]
    norad = l1[2:7].strip()
    name = lines[i]
    entry = cat.get(norad)
    if entry:
        found += 1
    else:
        missing += 1

total = found + missing
print(f"Starlink in catalog: {found}/{total} ({100*found//total}%)")

# Check stations
tle_r2 = httpx.get("http://127.0.0.1:8001/api/tle?category=stations", timeout=30)
lines2 = [l.strip() for l in tle_r2.text.splitlines() if l.strip()]
print("\nStations catalog lookup:")
for i in range(0, len(lines2)-2, 3):
    l1 = lines2[i+1]
    norad = l1[2:7].strip()
    name = lines2[i]
    entry = cat.get(norad)
    if entry:
        sat = entry["sat"]
        print(f"  NORAD {norad}  {name:30}  country={sat[5]}  status={sat[3]}  launched={sat[4]}")
    else:
        print(f"  NORAD {norad}  {name:30}  NOT IN CATALOG")

# Check Pakistan's 2 satellites
print("\nPakistan satellites in catalog:")
for norad, entry in cat.items():
    sat = entry.get("sat", [])
    if len(sat) > 5 and sat[5] and "PK" in str(sat[5]):
        print(f"  NORAD {norad}  name={sat[0]}  status={sat[3]}  launched={sat[4]}  website={sat[8]}")
