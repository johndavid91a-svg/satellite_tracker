import httpx

tests = [
    # CelesTrak via jsDelivr (npm package mirror)
    "https://cdn.jsdelivr.net/npm/tle.js/examples/tle-data.txt",
    # raw github - look for actual TLE files in public repos
    "https://raw.githubusercontent.com/nicholasamorim/python-sgp4/master/sgp4/SGP4-VER.TLE",
    "https://raw.githubusercontent.com/skyfielders/python-skyfield/master/ci/iss.tle",
    # space-track.org public TLE (no auth needed for some)
    "https://www.space-track.org/basicspacedata/query/class/gp/NORAD_CAT_ID/25544/format/tle",
    # Heavens-above
    "https://heavens-above.com/tle.aspx?satid=25544",
    # CelesTrak via Cloudflare/different DNS
    "https://celestrak.com/NORAD/elements/gp.php?GROUP=stations&FORMAT=tle",
    # Try IP directly (bypass DNS block)
    "https://216.218.240.197/NORAD/elements/gp.php?GROUP=stations&FORMAT=tle",
]

for url in tests:
    try:
        r = httpx.get(url, timeout=8, follow_redirects=True,
                      headers={"User-Agent": "Mozilla/5.0",
                               "Host": "celestrak.org" if "216.218" in url else ""})
        ct = r.headers.get("content-type", "")
        print(f"{r.status_code}  {len(r.content)}b  {url[:80]}")
        if r.status_code == 200 and len(r.content) > 50:
            print(f"  {r.text[:120].replace(chr(10), ' | ')}")
    except Exception as e:
        print(f"FAIL  {type(e).__name__}: {str(e)[:60]}  {url[:80]}")
