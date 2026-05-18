import httpx

def is_over_pk(lat, lon):
    return 23 <= lat <= 37 and 60 <= lon <= 78

BASE = "http://127.0.0.1:8001"
all_over_pk = []

for cat in ["stations", "starlink", "gps-ops", "weather", "active"]:
    r = httpx.get(f"{BASE}/api/positions?category={cat}", timeout=30)
    if r.status_code != 200:
        print(f"{cat}: ERROR {r.status_code}")
        continue
    data = r.json()
    over_pk = [p for p in data["positions"] if is_over_pk(p["lat"], p["lon"])]
    all_over_pk.extend([(cat, p) for p in over_pk])
    print(f"{cat:12} total={data['count']:4}  over_pk={len(over_pk)}")
    for p in over_pk:
        print(f"  {p['name']:35} lat={p['lat']:+.2f}  lon={p['lon']:+.2f}  alt={p['altKm']:.0f}km")

print()
print(f"TOTAL over Pakistan right now: {len(all_over_pk)}")
