import httpx, json

tests = [
    # SatNOGS - satellite metadata including country, operator
    "https://db.satnogs.org/api/satellites/?format=json&norad_cat_id=25544",
    # SatNOGS all satellites metadata
    "https://db.satnogs.org/api/satellites/?format=json&page_size=5",
    # satvisor catalog (they have a satnogs.json catalog)
    "https://raw.githubusercontent.com/satvisorcom/satvisor-data/master/catalog/satnogs.json",
    # UCS satellite database (Union of Concerned Scientists)
    "https://raw.githubusercontent.com/nicholasmr/satdb/main/satdb.json",
    # celestrak satcat (satellite catalog with country codes)
    "https://celestrak.org/pub/satcat.csv",
    # satvisor stdmag catalog
    "https://raw.githubusercontent.com/satvisorcom/satvisor-data/master/catalog/stdmag.json",
]

for url in tests:
    try:
        r = httpx.get(url, timeout=12, follow_redirects=True)
        ct = r.headers.get("content-type","")
        print(f"{r.status_code}  {len(r.content):>9}b  {url[:80]}")
        if r.status_code == 200 and len(r.content) > 50:
            if "json" in ct:
                data = r.json()
                if isinstance(data, list) and data:
                    print(f"  list[{len(data)}]  keys: {list(data[0].keys())[:8]}")
                    print(f"  sample: {json.dumps(data[0], default=str)[:200]}")
                elif isinstance(data, dict):
                    print(f"  dict keys: {list(data.keys())[:8]}")
            else:
                print(f"  preview: {r.text[:150].replace(chr(10),' | ')}")
    except Exception as e:
        print(f"FAIL  {type(e).__name__}: {str(e)[:60]}  {url[:80]}")
