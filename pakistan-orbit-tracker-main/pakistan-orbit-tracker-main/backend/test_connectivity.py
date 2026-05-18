import httpx

urls = [
    "https://celestrak.org/NORAD/elements/gp.php?GROUP=stations&FORMAT=tle",
    "https://celestrak.com/NORAD/elements/gp.php?GROUP=stations&FORMAT=tle",
    "https://api.allorigins.win/raw?url=https%3A%2F%2Fcelestrak.org%2FNORAD%2Felements%2Fgp.php%3FGROUP%3Dstations%26FORMAT%3Dtle",
    "https://tle.ivanstanojevic.me/api/tle/?search=ISS",
]

for u in urls:
    try:
        r = httpx.get(u, timeout=10, follow_redirects=True)
        print(f"OK  {r.status_code}  len={len(r.text)}  {u[:60]}")
    except Exception as e:
        print(f"FAIL  {type(e).__name__}: {e}  {u[:60]}")
