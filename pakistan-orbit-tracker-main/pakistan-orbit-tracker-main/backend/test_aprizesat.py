import httpx, json, time

BASE = "http://127.0.0.1:8001"

# warm TLE cache
print("Warming cache...")
for cat in ["active", "stations", "starlink"]:
    httpx.get(f"{BASE}/api/tle?category={cat}", timeout=30)
time.sleep(1)

# find APRIZESAT 5
print("\nSearching for APRIZESAT 5 in TLE data...")
r = httpx.get(f"{BASE}/api/tle?category=active", timeout=30)
lines = [l.strip() for l in r.text.splitlines() if l.strip()]
norad = None
for i in range(0, len(lines)-2, 3):
    if "APRIZE" in lines[i].upper():
        norad = lines[i+1][2:7].strip()
        print(f"  Found: {lines[i]}  NORAD={norad}")
        print(f"  L1: {lines[i+1]}")

if not norad:
    print("  NOT FOUND in active.tle — checking satnogs catalog directly...")
    r2 = httpx.get(
        "https://raw.githubusercontent.com/satvisorcom/satvisor-data/master/catalog/satnogs.json",
        timeout=15
    )
    cat = r2.json()
    for nid, entry in cat.items():
        sat = entry.get("sat", [])
        if sat and "APRIZE" in str(sat[0]).upper():
            print(f"  Catalog: NORAD={nid}  name={sat[0]}  country={sat[5]}  status={sat[3]}")
            norad = nid
    if not norad:
        print("  Not in catalog either. Trying known NORAD IDs for APRIZESAT...")
        for nid in ["39430", "39431", "39432", "39433", "39434", "40014", "40015"]:
            r3 = httpx.get(f"{BASE}/api/satellite/{nid}", timeout=10)
            if r3.status_code == 200:
                d = r3.json()
                if "APRIZE" in d.get("name","").upper() or d.get("name") != nid:
                    print(f"  NORAD {nid}: {d}")
else:
    print(f"\nTesting /api/satellite/{norad}...")
    r3 = httpx.get(f"{BASE}/api/satellite/{norad}", timeout=15)
    print(f"  Status: {r3.status_code}")
    print(json.dumps(r3.json(), indent=2))
