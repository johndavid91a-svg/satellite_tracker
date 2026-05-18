import httpx, json, time

BASE = "http://127.0.0.1:8001"

def is_over_pk(lat, lon):
    return 23 <= lat <= 37 and 60 <= lon <= 78

# 1. warm TLE cache for all categories
print("=== 1. WARMING TLE CACHE ===")
for cat in ["stations", "starlink", "gps-ops", "weather", "active"]:
    r = httpx.get(f"{BASE}/api/tle?category={cat}", timeout=30)
    lines = [l.strip() for l in r.text.splitlines() if l.strip()]
    print(f"  {cat:12} {len(lines)//3} sats  status={r.status_code}")
time.sleep(1)

# 2. find all satellites over Pakistan
print("\n=== 2. SATELLITES OVER PAKISTAN RIGHT NOW ===")
over_pk = []
for cat in ["stations", "starlink", "gps-ops", "weather", "active"]:
    r = httpx.get(f"{BASE}/api/positions?category={cat}", timeout=30)
    data = r.json()
    pk = [p for p in data["positions"] if is_over_pk(p["lat"], p["lon"])]
    for p in pk:
        over_pk.append((cat, p))
    if pk:
        for p in pk:
            print(f"  [{cat}] {p['name']:35} lat={p['lat']:+.2f} lon={p['lon']:+.2f} alt={p['altKm']:.0f}km")
    else:
        print(f"  [{cat}] none over Pakistan")

print(f"\n  TOTAL: {len(over_pk)} satellites over Pakistan")

# 3. test metadata for each satellite over Pakistan
print("\n=== 3. METADATA FOR EACH SATELLITE OVER PAKISTAN ===")

# build norad lookup from TLE cache
norad_map = {}
for cat in ["stations", "starlink", "gps-ops", "weather", "active"]:
    r = httpx.get(f"{BASE}/api/tle?category={cat}", timeout=30)
    lines = [l.strip() for l in r.text.splitlines() if l.strip()]
    for i in range(0, len(lines)-2, 3):
        if lines[i+1].startswith("1 "):
            norad = lines[i+1][2:7].strip()
            norad_map[lines[i]] = norad

for cat, p in over_pk:
    name = p["name"]
    norad = norad_map.get(name, "?")
    print(f"\n  [{cat}] {name}  NORAD={norad}")

    if norad == "?":
        print(f"    ERROR: NORAD not found in TLE cache")
        continue

    r = httpx.get(f"{BASE}/api/satellite/{norad}", timeout=15)
    if r.status_code != 200:
        print(f"    ERROR: /api/satellite/{norad} returned {r.status_code}")
        print(f"    Body: {r.text[:200]}")
        continue

    d = r.json()
    print(f"    Country     : {d.get('country_name')} ({d.get('country')})")
    print(f"    Operator    : {d.get('operator')}")
    print(f"    Purpose     : {d.get('purpose')}")
    print(f"    Source      : {d.get('source')}")
    print(f"    Destination : {d.get('destination')}")
    print(f"    Status      : {d.get('status')}")
    print(f"    Launched    : {d.get('launch_date')}")
    print(f"    Catalog src : {d.get('catalog_source')}")
    if d.get('website'):
        print(f"    Website     : {d.get('website')}")

# 4. diagnose why "Loading..." appears — test the satrec.satnum path
print("\n=== 4. DIAGNOSING 'Loading...' ISSUE ===")
print("  The frontend extracts NORAD via: (p as any).satrec?.satnum")
print("  This only works for satellites loaded via loadSatellites() (TLE path)")
print("  Satellites coming ONLY from backend /api/positions have no satrec attached")
print()

# check which over-PK sats have satrec vs not
for cat, p in over_pk:
    name = p["name"]
    norad = norad_map.get(name, None)
    has_norad = norad is not None
    print(f"  {name:35} norad_in_tle={has_norad}  norad={norad}")

print("\n=== 5. METADATA ENDPOINT HEALTH ===")
r = httpx.get(f"{BASE}/api/health", timeout=5)
print(f"  /api/health: {r.status_code} {r.json()}")

# test a known good NORAD
for norad, label in [("25544","ISS"), ("44714","STARLINK-1008"), ("39432","ICUBE-1 PK")]:
    r = httpx.get(f"{BASE}/api/satellite/{norad}", timeout=10)
    d = r.json() if r.status_code == 200 else {}
    print(f"  /api/satellite/{norad} ({label}): {r.status_code}  country={d.get('country_name','?')}  operator={d.get('operator','?')}")
