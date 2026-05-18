import httpx

# Try fetching the repo tree via raw GitHub (no API needed)
# githubusercontent serves files, we need to guess paths

# Try common variations for both repos
prefixes = [
    "https://raw.githubusercontent.com/satvisorcom/satvisor-data/main/",
    "https://raw.githubusercontent.com/satvisorcom/satvisor-data/master/",
    "https://raw.githubusercontent.com/MrTalon63/ReTLEctor/main/",
    "https://raw.githubusercontent.com/MrTalon63/ReTLEctor/master/",
]

filenames = [
    "stations.txt", "starlink.txt", "gps-ops.txt", "weather.txt", "active.txt",
    "stations.tle", "starlink.tle", "gps-ops.tle", "weather.tle", "active.tle",
    "tle/stations.txt", "tle/starlink.txt",
    "data/stations.txt", "data/starlink.txt",
    "celestrak/stations.txt", "celestrak/starlink.txt",
    "NORAD/stations.txt",
    "README.md",  # to confirm repo exists
]

for prefix in prefixes:
    for fn in filenames:
        url = prefix + fn
        try:
            r = httpx.get(url, timeout=5)
            if r.status_code == 200:
                print(f"FOUND  {len(r.content)}b  {url}")
                print(f"  {r.text[:100].replace(chr(10),' | ')}")
        except Exception:
            pass
