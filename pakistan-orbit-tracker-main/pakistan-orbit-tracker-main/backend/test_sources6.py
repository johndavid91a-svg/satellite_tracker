import httpx

tests = [
    # GitHub raw - find actual TLE repos
    "https://raw.githubusercontent.com/treyhunner/whereami/master/iss.tle",
    "https://raw.githubusercontent.com/mourner/suncalc/master/test/iss.tle",
    # CelesTrak via corsproxy (server-side, no CORS issue)
    "https://corsproxy.io/?https://celestrak.org/NORAD/elements/gp.php?GROUP=stations&FORMAT=tle",
    # allorigins
    "https://api.allorigins.win/raw?url=https%3A%2F%2Fcelestrak.org%2FNORAD%2Felements%2Fgp.php%3FGROUP%3Dstations%26FORMAT%3Dtle",
    # thingproxy
    "https://thingproxy.freeboard.io/fetch/https://celestrak.org/NORAD/elements/gp.php?GROUP=stations&FORMAT=tle",
    # codetabs proxy
    "https://api.codetabs.com/v1/proxy?quest=https://celestrak.org/NORAD/elements/gp.php?GROUP=stations&FORMAT=tle",
]

for url in tests:
    try:
        r = httpx.get(url, timeout=10, follow_redirects=True,
                      headers={"User-Agent": "Mozilla/5.0"})
        print(f"{r.status_code}  {len(r.content)}b  {url[:80]}")
        if r.status_code == 200 and len(r.content) > 50:
            print(f"  {r.text[:120].replace(chr(10), ' | ')}")
    except Exception as e:
        print(f"FAIL  {type(e).__name__}: {str(e)[:60]}  {url[:80]}")
