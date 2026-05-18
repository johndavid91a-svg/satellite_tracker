import httpx, json

BASE = "http://127.0.0.1:8001"

# First warm up TLE cache so name lookup works
print("Warming TLE cache...")
for cat in ["stations", "starlink", "gps-ops", "weather"]:
    httpx.get(f"{BASE}/api/tle?category={cat}", timeout=30)

print("\n=== /api/satellite/{norad} ===\n")
test_norads = [
    ("25544",  "ISS (ZARYA)"),
    ("48274",  "CSS (TIANHE)"),
    ("44714",  "STARLINK-1008"),
    ("24876",  "GPS BIIR-2"),
    ("28654",  "NOAA 18"),
    ("39432",  "ICUBE-1 (Pakistan)"),
    ("43530",  "PRSS 1 (Pakistan)"),
]

for norad, label in test_norads:
    r = httpx.get(f"{BASE}/api/satellite/{norad}", timeout=15)
    if r.status_code == 200:
        d = r.json()
        print(f"[{norad}] {label}")
        print(f"  Country     : {d.get('country_name')} ({d.get('country')})")
        print(f"  Operator    : {d.get('operator')}")
        print(f"  Purpose     : {d.get('purpose')}")
        print(f"  Source      : {d.get('source')}")
        print(f"  Destination : {d.get('destination')}")
        print(f"  Status      : {d.get('status')}")
        print(f"  Launched    : {d.get('launch_date')}")
        print(f"  Data source : {d.get('catalog_source')}")
        print()
    else:
        print(f"[{norad}] {label} -> ERROR {r.status_code}")

print("=== /api/metadata?category=stations ===\n")
r2 = httpx.get(f"{BASE}/api/metadata?category=stations", timeout=30)
data = r2.json()
print(f"Returned {len(data)} entries")
for name, meta in list(data.items())[:5]:
    print(f"  {name:30} country={meta.get('country_name'):25} operator={meta.get('operator')}")
