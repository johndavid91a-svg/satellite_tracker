import httpx

r = httpx.get("http://127.0.0.1:8001/api/positions?category=stations", timeout=30)
print("Status:", r.status_code)
print("Body:", r.text)
