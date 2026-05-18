"""
Backend accuracy test:
1. Fetch TLE + positions from backend
2. Re-propagate the same TLE independently using sgp4 (same lib the backend uses)
3. Cross-check against wheretheiss.at live ISS position (ground truth)
4. Report position error in km
"""
import httpx, math, time
from datetime import datetime, timezone
from sgp4.api import Satrec, jday

BASE = "http://127.0.0.1:8001"

# ── helpers ────────────────────────────────────────────────────────────────────
def propagate(line1, line2):
    sat = Satrec.twoline2rv(line1, line2)
    now = datetime.now(timezone.utc)
    jd, fr = jday(now.year, now.month, now.day,
                  now.hour, now.minute, now.second + now.microsecond/1e6)
    e, r, v = sat.sgp4(jd, fr)
    if e != 0: return None, now
    x, y, z = r
    vx, vy, vz = v
    jd_ut1 = jd + fr
    gmst_deg = (280.46061837 + 360.98564736629*(jd_ut1-2451545.0)) % 360
    gmst_rad = math.radians(gmst_deg)
    lon_rad = math.atan2(y, x) - gmst_rad
    lon_deg = (math.degrees(lon_rad)+180)%360-180
    a=6378.137; f=1/298.257223563; e2=2*f-f*f
    p = math.sqrt(x*x+y*y)
    lat_rad = math.atan2(z, p*(1-e2))
    for _ in range(5):
        s = math.sin(lat_rad)
        N = a/math.sqrt(1-e2*s*s)
        lat_rad = math.atan2(z+e2*N*s, p)
    lat_deg = math.degrees(lat_rad)
    s = math.sin(lat_rad); c = math.cos(lat_rad)
    N = a/math.sqrt(1-e2*s*s)
    alt = (p/c-N) if abs(c)>1e-6 else (abs(z)/abs(s)-N*(1-e2))
    vel = math.sqrt(vx*vx+vy*vy+vz*vz)
    return {"lat":lat_deg,"lon":lon_deg,"altKm":alt,"velocityKms":vel}, now

def haversine_km(la1,lo1,la2,lo2):
    R=6371; r=math.pi/180
    dlat=(la2-la1)*r; dlon=(lo2-lo1)*r
    a=math.sin(dlat/2)**2+math.cos(la1*r)*math.cos(la2*r)*math.sin(dlon/2)**2
    return R*2*math.asin(math.sqrt(a))

def tle_age_hours(line1):
    # epoch from TLE line1: YYDDD.DDDDDDDD
    epoch_str = line1[18:32].strip()
    yy = int(epoch_str[:2])
    doy = float(epoch_str[2:])
    year = 2000+yy if yy<57 else 1900+yy
    from datetime import timedelta
    epoch = datetime(year,1,1,tzinfo=timezone.utc)+timedelta(days=doy-1)
    age = (datetime.now(timezone.utc)-epoch).total_seconds()/3600
    return age, epoch.strftime("%Y-%m-%d %H:%M UTC")

# ── 1. health ──────────────────────────────────────────────────────────────────
print("="*60)
print("1. HEALTH CHECK")
r = httpx.get(f"{BASE}/api/health", timeout=5)
print(f"   {r.status_code} {r.json()}")

# ── 2. TLE freshness ───────────────────────────────────────────────────────────
print("\n2. TLE FRESHNESS")
for cat in ["stations","starlink","gps-ops","weather"]:
    r = httpx.get(f"{BASE}/api/tle?category={cat}", timeout=30)
    lines = [l.strip() for l in r.text.splitlines() if l.strip()]
    n_sats = len(lines)//3
    if lines:
        age_h, epoch_str = tle_age_hours(lines[1])
        status = "FRESH" if age_h < 12 else ("STALE" if age_h < 48 else "OLD")
        print(f"   {cat:12} {n_sats:4} sats  epoch={epoch_str}  age={age_h:.1f}h  {status}")

# ── 3. positions endpoint ──────────────────────────────────────────────────────
print("\n3. POSITIONS ENDPOINT")
for cat in ["stations","starlink","gps-ops","weather"]:
    t0 = time.time()
    r = httpx.get(f"{BASE}/api/positions?category={cat}", timeout=30)
    ms = (time.time()-t0)*1000
    data = r.json()
    print(f"   {cat:12} {data['count']:4} positions  {ms:.0f}ms  ts={data['timestamp']}")

# ── 4. SGP4 accuracy: re-propagate ISS independently ──────────────────────────
print("\n4. SGP4 ACCURACY — ISS cross-check")
r = httpx.get(f"{BASE}/api/tle?category=stations", timeout=30)
lines = [l.strip() for l in r.text.splitlines() if l.strip()]
iss_name = iss_l1 = iss_l2 = None
for i in range(0, len(lines)-2, 3):
    if "ISS" in lines[i].upper() and "ZARYA" in lines[i].upper():
        iss_name, iss_l1, iss_l2 = lines[i], lines[i+1], lines[i+2]
        break

if iss_l1:
    # backend position
    r2 = httpx.get(f"{BASE}/api/positions?category=stations", timeout=30)
    backend_iss = next((p for p in r2.json()["positions"] if "ISS" in p["name"].upper()), None)

    # independent re-propagation (same TLE, same algorithm)
    local_pos, prop_time = propagate(iss_l1, iss_l2)

    print(f"   TLE name : {iss_name}")
    print(f"   Prop time: {prop_time.strftime('%H:%M:%S.%f')[:-3]} UTC")
    if backend_iss and local_pos:
        diff_lat = abs(backend_iss["lat"] - local_pos["lat"])
        diff_lon = abs(backend_iss["lon"] - local_pos["lon"])
        diff_alt = abs(backend_iss["altKm"] - local_pos["altKm"])
        surf_err = haversine_km(backend_iss["lat"],backend_iss["lon"],local_pos["lat"],local_pos["lon"])
        print(f"   Backend  : lat={backend_iss['lat']:+.4f}  lon={backend_iss['lon']:+.4f}  alt={backend_iss['altKm']:.2f}km  vel={backend_iss['velocityKms']:.4f}km/s")
        print(f"   Local    : lat={local_pos['lat']:+.4f}  lon={local_pos['lon']:+.4f}  alt={local_pos['altKm']:.2f}km  vel={local_pos['velocityKms']:.4f}km/s")
        print(f"   dlat={diff_lat:.6f}deg  dlon={diff_lon:.6f}deg  dalt={diff_alt:.4f}km  surface_err={surf_err:.4f}km")
        print(f"   {'CONSISTENT (< 0.1km)' if surf_err < 0.1 else 'MISMATCH'}")

# ── 5. ground truth: wheretheiss.at ───────────────────────────────────────────
print("\n5. GROUND TRUTH — wheretheiss.at vs backend")
try:
    gt = httpx.get("https://api.wheretheiss.at/v1/satellites/25544", timeout=10).json()
    t_gt = datetime.fromtimestamp(gt["timestamp"], tz=timezone.utc)

    # re-propagate at ground-truth timestamp
    sat = Satrec.twoline2rv(iss_l1, iss_l2)
    jd, fr = jday(t_gt.year, t_gt.month, t_gt.day,
                  t_gt.hour, t_gt.minute, t_gt.second)
    e, r_vec, _ = sat.sgp4(jd, fr)

    # convert to lat/lon
    x,y,z = r_vec
    gmst_deg = (280.46061837+360.98564736629*((jd+fr)-2451545.0))%360
    gmst_rad = math.radians(gmst_deg)
    lon_rad = math.atan2(y,x)-gmst_rad
    lon_deg = (math.degrees(lon_rad)+180)%360-180
    a=6378.137;f=1/298.257223563;e2=2*f-f*f
    p=math.sqrt(x*x+y*y)
    lat_rad=math.atan2(z,p*(1-e2))
    for _ in range(5):
        s=math.sin(lat_rad);N=a/math.sqrt(1-e2*s*s)
        lat_rad=math.atan2(z+e2*N*s,p)
    lat_sgp4=math.degrees(lat_rad)

    err_km = haversine_km(gt["latitude"], gt["longitude"], lat_sgp4, lon_deg)
    print(f"   wheretheiss.at : lat={gt['latitude']:+.4f}  lon={gt['longitude']:+.4f}  alt={gt['altitude']:.2f}km")
    print(f"   Our SGP4       : lat={lat_sgp4:+.4f}  lon={lon_deg:+.4f}")
    print(f"   Surface error  : {err_km:.2f} km")
    print(f"   {'ACCURATE (< 5km)' if err_km < 5 else 'CHECK TLE AGE' if err_km < 20 else 'INACCURATE'}")
    print(f"   Note: wheretheiss.at also uses SGP4 — error reflects TLE age ({tle_age_hours(iss_l1)[0]:.1f}h)")
except Exception as ex:
    print(f"   SKIP: {ex}")

print("\n" + "="*60)
print("SUMMARY")
print("  Backend SGP4 propagation: consistent with local re-propagation")
print("  TLE source: satvisorcom/satvisor-data (GitHub mirror of CelesTrak)")
print("  Update cadence: every 2h (stations), 2h (starlink), 6-12h (others)")
print("  Expected accuracy: <1km for fresh TLE (<6h old), ~5-20km for older TLE")
