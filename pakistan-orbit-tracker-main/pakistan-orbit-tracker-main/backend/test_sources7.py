import httpx

# Test what domains resolve and connect at all
import socket
domains = [
    "celestrak.org",
    "celestrak.com", 
    "raw.githubusercontent.com",
    "github.com",
    "api.wheretheiss.at",
    "db.satnogs.org",
    "google.com",
    "tle.ivanstanojevic.me",
]

print("=== DNS + TCP connectivity ===")
for d in domains:
    try:
        ip = socket.gethostbyname(d)
        # try TCP connect port 443
        s = socket.socket()
        s.settimeout(3)
        err = s.connect_ex((ip, 443))
        s.close()
        print(f"{'OK  ' if err==0 else 'TCP-FAIL'} {d} -> {ip}")
    except Exception as e:
        print(f"DNS-FAIL  {d}: {e}")

print()
print("=== raw.githubusercontent.com TLE files ===")
# Search for actual TLE files on GitHub
urls = [
    "https://raw.githubusercontent.com/Hopperpop/Sattrack-library/main/examples/tle_data/stations.txt",
    "https://raw.githubusercontent.com/Hopperpop/Sattrack-library/main/examples/tle_data/starlink.txt",
    "https://raw.githubusercontent.com/Hopperpop/Sattrack-library/main/examples/tle_data/gps-ops.txt",
    "https://raw.githubusercontent.com/Hopperpop/Sattrack-library/main/examples/tle_data/weather.txt",
    "https://raw.githubusercontent.com/Hopperpop/Sattrack-library/main/examples/tle_data/active.txt",
]
for url in urls:
    try:
        r = httpx.get(url, timeout=8)
        print(f"{r.status_code}  {len(r.content)}b  {url[-50:]}")
        if r.status_code == 200:
            print(f"  {r.text[:80].replace(chr(10),' | ')}")
    except Exception as e:
        print(f"FAIL  {e}  {url[-50:]}")
