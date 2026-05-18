import httpx

tests = [
    # GitHub raw TLE mirrors
    "https://raw.githubusercontent.com/shashwatak/satellite-js/develop/test/sgp4-full-validation-data.json",
    "https://raw.githubusercontent.com/dsuarezv/satellite-tracker/master/Assets/tle-data/active.txt",
    "https://raw.githubusercontent.com/onurozuduru/satellite-tracker/master/tle_data/stations.txt",
    # jsDelivr CDN (mirrors npm packages)
    "https://cdn.jsdelivr.net/gh/Bill-Gray/tles@master/stations.tle",
    "https://cdn.jsdelivr.net/gh/Bill-Gray/tles@master/starlink.tle",
    "https://cdn.jsdelivr.net/gh/Bill-Gray/tles@master/gps_ops.tle",
    "https://cdn.jsdelivr.net/gh/Bill-Gray/tles@master/weather.tle",
    "https://cdn.jsdelivr.net/gh/Bill-Gray/tles@master/active.tle",
]

for url in tests:
    try:
        r = httpx.get(url, timeout=10, follow_redirects=True,
                      headers={"User-Agent": "Mozilla/5.0"})
        ct = r.headers.get("content-type", "")
        print(f"{r.status_code}  {len(r.content)}b  {url[:80]}")
        if r.status_code == 200 and len(r.content) > 50:
            preview = r.text[:120].replace('\n', ' | ')
            print(f"  {preview}")
    except Exception as e:
        print(f"FAIL  {type(e).__name__}: {str(e)[:50]}  {url[:80]}")
