import httpx

BASE = "https://raw.githubusercontent.com/satvisorcom/satvisor-data/master/celestrak/tle/"
slugs = ["stations", "starlink", "gps-ops", "weather", "active"]

for slug in slugs:
    url = BASE + slug + ".tle"
    r = httpx.get(url, timeout=15)
    lines = [l for l in r.text.splitlines() if l.strip()]
    sats = len(lines) // 3
    print(f"{r.status_code}  {len(r.content):>8}b  {sats:>5} sats  {slug}")
    if r.status_code == 200 and lines:
        print(f"  first: {lines[0]} | {lines[1][:40]} | {lines[2][:40]}")
