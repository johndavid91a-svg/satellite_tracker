import httpx

tests = [
    # wheretheiss - list all satellites
    "https://api.wheretheiss.at/v1/satellites",
    # n2yo live position (needs API key but check connectivity)
    "https://api.n2yo.com/rest/v1/satellite/positions/25544/41.702/-76.014/0/2/&apiKey=DEMO",
    # stuffin.space TLE endpoint
    "https://stuffin.space/api/tle/active",
    "https://stuffin.space/api/tle/starlink",
    "https://stuffin.space/api/tle/gps",
    "https://stuffin.space/api/tle/weather",
]

for url in tests:
    try:
        r = httpx.get(url, timeout=10, follow_redirects=True,
                      headers={"User-Agent": "Mozilla/5.0"})
        ct = r.headers.get("content-type", "")
        print(f"{r.status_code}  {len(r.content)}b  ct={ct[:30]}  {url[:80]}")
        if r.status_code == 200 and "json" in ct:
            print(f"  {r.text[:150]}")
        elif r.status_code == 200 and len(r.content) < 500:
            print(f"  {r.text[:150]}")
    except Exception as e:
        print(f"FAIL  {type(e).__name__}: {str(e)[:50]}  {url[:80]}")
