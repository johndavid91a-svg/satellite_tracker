import httpx, json

headers = {"User-Agent": "Mozilla/5.0", "Authorization": ""}

# Check satvisor-data repo contents
for repo, path in [
    ("satvisorcom/satvisor-data", ""),
    ("MrTalon63/ReTLEctor", ""),
]:
    r = httpx.get(f"https://api.github.com/repos/{repo}/contents/{path}",
                  timeout=8, headers=headers)
    print(f"\n=== {repo} ===  status={r.status_code}")
    if r.status_code == 200:
        for f in r.json():
            print(f"  {f['type']:4}  {f['name']}")
