import httpx

sources = [
    # CelesTrak via different IPs / CDN
    "https://celestrak.org/NORAD/elements/gp.php?GROUP=stations&FORMAT=tle",
    # CelesTrak JSON API (different endpoint)
    "https://celestrak.org/NORAD/elements/gp.php?GROUP=stations&FORMAT=json",
    # CelesTrak via www subdomain
    "https://www.celestrak.org/NORAD/elements/gp.php?GROUP=stations&FORMAT=tle",
    # keeptrack.space mirrors celestrak
    "https://keeptrack.space/tle/stations.txt",
    # stuffin.space
    "https://stuffin.space/api/tle/stations",
    # open-notify ISS only
    "http://api.open-notify.org/iss-now.json",
    # wheretheiss.at
    "https://api.wheretheiss.at/v1/satellites/25544",
    # TLE from github raw (cached copies)
    "https://raw.githubusercontent.com/treyhunner/whereami/master/iss.tle",
]

for url in sources:
    try:
        r = httpx.get(url, timeout=8, follow_redirects=True,
                      headers={"User-Agent": "Mozilla/5.0"})
        print(f"{r.status_code}  {len(r.content)}b  {url[:80]}")
        if r.status_code == 200 and len(r.content) > 10:
            print(f"  {r.text[:100]}")
    except Exception as e:
        print(f"FAIL  {type(e).__name__}: {str(e)[:50]}  {url[:80]}")
