import httpx

tests = [
    # tle.ivanstanojevic.me with browser user-agent
    ("GET", "https://tle.ivanstanojevic.me/api/tle/25544", {"User-Agent": "Mozilla/5.0"}),
    ("GET", "https://tle.ivanstanojevic.me/api/tle/?search=ISS&page-size=5", {"User-Agent": "Mozilla/5.0"}),
    # satnogs
    ("GET", "https://db.satnogs.org/api/tle/?format=json&norad_cat_id=25544", {}),
    # n2yo
    ("GET", "https://api.n2yo.com/rest/v1/satellite/tle/25544&apiKey=DEMO", {}),
    # space-track (requires login, just check connectivity)
    ("GET", "https://www.space-track.org", {}),
]

for method, url, headers in tests:
    try:
        r = httpx.get(url, headers=headers, timeout=10, follow_redirects=True)
        print(f"{r.status_code}  {len(r.content)}b  {url[:70]}")
        if r.status_code == 200 and len(r.content) > 50:
            print(f"  preview: {r.text[:120]}")
    except Exception as e:
        print(f"FAIL  {type(e).__name__}: {str(e)[:60]}  {url[:70]}")
