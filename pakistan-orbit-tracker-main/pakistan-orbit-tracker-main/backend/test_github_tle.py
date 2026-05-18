import httpx

# Known GitHub repos that cache/mirror CelesTrak TLE data
candidates = [
    # space-data org
    "https://raw.githubusercontent.com/space-data/tle/main/stations.txt",
    "https://raw.githubusercontent.com/space-data/tle/main/starlink.txt",
    # celestrak-mirror
    "https://raw.githubusercontent.com/celestrak/celestrak/main/NORAD/elements/stations.txt",
    # tle-data repos
    "https://raw.githubusercontent.com/tle-data/tle-data/main/stations.tle",
    "https://raw.githubusercontent.com/tle-data/tle-data/main/starlink.tle",
    # joshuaferrara
    "https://raw.githubusercontent.com/joshuaferrara/go-satellite/master/tle_test.txt",
    # open-source satellite trackers
    "https://raw.githubusercontent.com/dsuarezv/satellite-tracker/master/Assets/tle-data/stations.txt",
    "https://raw.githubusercontent.com/dsuarezv/satellite-tracker/master/Assets/tle-data/starlink.txt",
    # Use GitHub API to search for TLE files
    "https://api.github.com/search/repositories?q=celestrak+tle+mirror&sort=updated",
]

for url in candidates:
    try:
        r = httpx.get(url, timeout=8, follow_redirects=True,
                      headers={"User-Agent": "Mozilla/5.0"})
        print(f"{r.status_code}  {len(r.content)}b  {url[50:]}")
        if r.status_code == 200 and len(r.content) > 100:
            print(f"  {r.text[:100].replace(chr(10),' | ')}")
    except Exception as e:
        print(f"FAIL  {e}  {url[50:]}")
