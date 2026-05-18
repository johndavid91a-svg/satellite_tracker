import httpx

# satvisorcom/satvisor-data and MrTalon63/ReTLEctor - try common TLE file paths
urls = [
    # satvisor-data
    "https://raw.githubusercontent.com/satvisorcom/satvisor-data/main/tle/stations.tle",
    "https://raw.githubusercontent.com/satvisorcom/satvisor-data/main/tle/starlink.tle",
    "https://raw.githubusercontent.com/satvisorcom/satvisor-data/main/tle/gps-ops.tle",
    "https://raw.githubusercontent.com/satvisorcom/satvisor-data/main/tle/weather.tle",
    "https://raw.githubusercontent.com/satvisorcom/satvisor-data/main/tle/active.tle",
    "https://raw.githubusercontent.com/satvisorcom/satvisor-data/main/stations.tle",
    "https://raw.githubusercontent.com/satvisorcom/satvisor-data/main/starlink.tle",
    # ReTLEctor
    "https://raw.githubusercontent.com/MrTalon63/ReTLEctor/main/stations.tle",
    "https://raw.githubusercontent.com/MrTalon63/ReTLEctor/main/starlink.tle",
    "https://raw.githubusercontent.com/MrTalon63/ReTLEctor/main/gps-ops.tle",
    "https://raw.githubusercontent.com/MrTalon63/ReTLEctor/main/weather.tle",
    "https://raw.githubusercontent.com/MrTalon63/ReTLEctor/main/active.tle",
    "https://raw.githubusercontent.com/MrTalon63/ReTLEctor/master/stations.tle",
    "https://raw.githubusercontent.com/MrTalon63/ReTLEctor/master/starlink.tle",
]

for url in urls:
    try:
        r = httpx.get(url, timeout=8, follow_redirects=True)
        print(f"{r.status_code}  {len(r.content)}b  {url[50:]}")
        if r.status_code == 200 and len(r.content) > 50:
            print(f"  {r.text[:80].replace(chr(10),' | ')}")
    except Exception as e:
        print(f"FAIL  {e}  {url[50:]}")
