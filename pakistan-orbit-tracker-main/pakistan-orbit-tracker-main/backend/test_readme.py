import httpx

for url in [
    "https://raw.githubusercontent.com/satvisorcom/satvisor-data/master/README.md",
    "https://raw.githubusercontent.com/MrTalon63/ReTLEctor/master/README.md",
]:
    r = httpx.get(url, timeout=8)
    print(f"=== {url.split('/')[-3]} ===")
    print(r.text)
    print()
