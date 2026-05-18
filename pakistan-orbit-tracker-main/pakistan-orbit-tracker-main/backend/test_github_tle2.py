import httpx, json

# Get the search results
r = httpx.get("https://api.github.com/search/repositories?q=celestrak+tle+mirror&sort=updated",
              timeout=8, headers={"User-Agent": "Mozilla/5.0"})
data = r.json()
for item in data.get("items", []):
    print(item["full_name"], "-", item.get("description","")[:60])

print()

# Also try tle.ivanstanojevic.me with a proper Accept header (it was 403 before)
for ua in [
    "python-httpx/0.27",
    "curl/7.88.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "satellite-tracker/1.0",
]:
    r2 = httpx.get("https://tle.ivanstanojevic.me/api/tle/25544",
                   timeout=8, headers={"User-Agent": ua})
    print(f"ivanstanojevic ua={ua[:30]} -> {r2.status_code} {len(r2.content)}b")
    if r2.status_code == 200:
        print(" ", r2.text[:100])
        break
