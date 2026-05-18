import httpx

tests = [
    # SatNOGS bulk by transmitter mode / type
    "https://db.satnogs.org/api/tle/?format=json&norad_cat_id=25544",
    # ISS + stations (known NORAD IDs)
    "https://db.satnogs.org/api/tle/?format=json&norad_cat_id=25544&norad_cat_id=48274",
    # All TLEs paginated
    "https://db.satnogs.org/api/tle/?format=json&page=1&page_size=20",
    # Satellites endpoint for filtering
    "https://db.satnogs.org/api/satellites/?format=json&status=alive&page_size=5",
]

for url in tests:
    try:
        r = httpx.get(url, timeout=15, follow_redirects=True)
        print(f"{r.status_code}  {len(r.content)}b  {url[:80]}")
        if r.status_code == 200:
            import json
            data = r.json()
            if isinstance(data, list):
                print(f"  list of {len(data)}, first keys: {list(data[0].keys()) if data else 'empty'}")
            elif isinstance(data, dict):
                print(f"  dict keys: {list(data.keys())[:6]}")
    except Exception as e:
        print(f"FAIL  {e}  {url[:80]}")
