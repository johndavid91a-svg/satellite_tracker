import httpx, json

r = httpx.get(
    "https://raw.githubusercontent.com/satvisorcom/satvisor-data/master/catalog/satnogs.json",
    timeout=15
)
data = r.json()
print(f"Total entries: {len(data)}")

# Check ISS (25544) and a few others
for norad in ["25544", "44714", "24876", "28654"]:
    entry = data.get(norad)
    if entry:
        sat = entry.get("sat", [])
        print(f"\nNORAD {norad}:")
        print(f"  raw sat array: {sat}")
        print(f"  tx count: {len(entry.get('tx',[]))}")
    else:
        print(f"\nNORAD {norad}: NOT FOUND")

# Print the sat array field meanings by checking a few entries
print("\n--- sat array structure (index: value) ---")
sample = data.get("25544", {}).get("sat", [])
labels = ["name","sat_id","alt_names","status","launch_date","country","operator","image","website"]
for i, (label, val) in enumerate(zip(labels, sample)):
    print(f"  [{i}] {label}: {val}")

# Check country code coverage
countries = {}
for norad, entry in data.items():
    sat = entry.get("sat", [])
    if len(sat) > 5:
        cc = sat[5]
        if cc:
            countries[cc] = countries.get(cc, 0) + 1

print(f"\nCountry codes found: {len(countries)}")
print(f"Top 10: {sorted(countries.items(), key=lambda x:-x[1])[:10]}")
print(f"Pakistan (PK): {countries.get('PK', 0)} satellites")
