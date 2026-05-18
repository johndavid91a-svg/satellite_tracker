import httpx, json

# Starlink NORAD IDs from TLE
tle_r = httpx.get("http://127.0.0.1:8001/api/tle?category=starlink", timeout=30)
lines = [l.strip() for l in tle_r.text.splitlines() if l.strip()]
starlink_norads = []
for i in range(0, min(len(lines)-2, 9), 3):
    starlink_norads.append((lines[i], lines[i+1][2:7].strip()))

print("Sample Starlink NORAD IDs:", starlink_norads[:5])

# Test SatNOGS API per-satellite (it has more than the bulk catalog)
print("\n--- SatNOGS API per satellite ---")
for name, norad in starlink_norads[:3]:
    r = httpx.get(f"https://db.satnogs.org/api/satellites/?format=json&norad_cat_id={norad}", timeout=8)
    data = r.json()
    if data:
        sat = data[0]
        print(f"  {norad} {name}: countries={sat.get('countries')}, operator={sat.get('operator')}, status={sat.get('status')}")
    else:
        print(f"  {norad} {name}: NOT FOUND")

# Test space-track satcat via their public query (no auth for basic data)
print("\n--- space-track.org satcat (no auth) ---")
r = httpx.get(
    "https://www.space-track.org/basicspacedata/query/class/satcat/NORAD_CAT_ID/44714/format/json",
    timeout=8, follow_redirects=True
)
print(f"  status={r.status_code} len={len(r.content)}")
if r.status_code == 200:
    print(f"  {r.text[:200]}")

# Check SatNOGS full satellite list for Starlink
print("\n--- SatNOGS satellites with 'starlink' in name ---")
r2 = httpx.get(
    "https://db.satnogs.org/api/satellites/?format=json&status=alive&page_size=100",
    timeout=15
)
data2 = r2.json()
starlinks = [s for s in data2 if "STARLINK" in s.get("name","").upper()]
print(f"  Found {len(starlinks)} Starlink in first 100 alive sats")
if starlinks:
    print(f"  Sample: {json.dumps(starlinks[0], default=str)[:300]}")
