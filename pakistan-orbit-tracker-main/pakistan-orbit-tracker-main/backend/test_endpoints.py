import httpx

urls = [
    "http://127.0.0.1:8001/api/health",
    "http://127.0.0.1:8001/api/categories",
    "http://127.0.0.1:8001/api/tle?category=stations",
    "http://127.0.0.1:8001/api/positions?category=stations",
]

for u in urls:
    try:
        r = httpx.get(u, timeout=20.0)
        print(u, "->", r.status_code, "len=" + str(len(r.text) if r.text is not None else None))
        if u.endswith("health"):
            print("  ", r.json())
        elif u.endswith("categories"):
            print("  ", list(r.json().keys()))
        elif "tle" in u:
            print("  sample:", r.text.splitlines()[:3])
    except Exception as exc:
        print(u, "FAILED", exc)
