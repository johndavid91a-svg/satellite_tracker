import * as satellite from "satellite.js";
import { predictNextPass, type PassInfo } from "./passes";
export type { PassInfo } from "./passes";

export type Category = "hires-eo" | "stations" | "starlink" | "oneweb" | "gps-ops" | "glo-ops" | "galileo" | "beidou" | "weather" | "resource" | "military" | "geo" | "iridium-NEXT" | "active";

// CelesTrak multi-NORAD URL for curated Imagery + SAR + Military surveillance satellites
const HIRES_EO_NORAD_IDS = [
  // India optical
  41599,41948,42767,43111,44804,
  // India SAR
  51656,44233,44857,
  // USA optical
  32060,35946,40115,33331,
  // France optical + military
  38012,39019,43813,46070,49438,
  // Italy military SAR (COSMO-SkyMed)
  31598,32376,33053,36599,45026,49719,
  // Germany SAR
  31698,36605,
  // South Korea
  38338,40536,39227,
  // China optical + SAR
  40118,44703,43585,41384,
  // Spain
  40013,43215,
  // ESA SAR
  39634,
  // Israel military SAR
  32273,
  // Japan SAR
  39769,
].join(",");

export const CATEGORY_META: Record<Category, { label: string; color: string; url: string; max: number }> = {
  "hires-eo": {
    label: "Imagery & SAR Surveillance",
    color: "#22d3ee",
    url: `https://celestrak.org/NORAD/elements/gp.php?CATNR=${HIRES_EO_NORAD_IDS}&FORMAT=tle`,
    max: 40,
  },
  stations: {
    label: "Space Stations (ISS/CSS)",
    color: "#f97316",
    url: "https://celestrak.org/NORAD/elements/gp.php?GROUP=stations&FORMAT=tle",
    max: 50,
  },
  starlink: {
    label: "Starlink",
    color: "#60a5fa",
    url: "https://celestrak.org/NORAD/elements/gp.php?GROUP=starlink&FORMAT=tle",
    max: 7000,
  },
  oneweb: {
    label: "OneWeb",
    color: "#a78bfa",
    url: "https://celestrak.org/NORAD/elements/gp.php?GROUP=oneweb&FORMAT=tle",
    max: 700,
  },
  "gps-ops": {
    label: "GPS Operational",
    color: "#facc15",
    url: "https://celestrak.org/NORAD/elements/gp.php?GROUP=gps-ops&FORMAT=tle",
    max: 50,
  },
  "glo-ops": {
    label: "GLONASS",
    color: "#f472b6",
    url: "https://celestrak.org/NORAD/elements/gp.php?GROUP=glo-ops&FORMAT=tle",
    max: 50,
  },
  galileo: {
    label: "Galileo",
    color: "#34d399",
    url: "https://celestrak.org/NORAD/elements/gp.php?GROUP=galileo&FORMAT=tle",
    max: 50,
  },
  beidou: {
    label: "BeiDou",
    color: "#fb7185",
    url: "https://celestrak.org/NORAD/elements/gp.php?GROUP=beidou&FORMAT=tle",
    max: 60,
  },
  weather: {
    label: "Weather (NOAA)",
    color: "#38bdf8",
    url: "https://celestrak.org/NORAD/elements/gp.php?GROUP=weather&FORMAT=tle",
    max: 80,
  },
  resource: {
    label: "Earth Observation",
    color: "#4ade80",
    url: "https://celestrak.org/NORAD/elements/gp.php?GROUP=resource&FORMAT=tle",
    max: 200,
  },
  military: {
    label: "Military / Recon",
    color: "#ef4444",
    url: "https://celestrak.org/NORAD/elements/gp.php?GROUP=military&FORMAT=tle",
    max: 100,
  },
  geo: {
    label: "Geostationary",
    color: "#e879f9",
    url: "https://celestrak.org/NORAD/elements/gp.php?GROUP=geo&FORMAT=tle",
    max: 600,
  },
  "iridium-NEXT": {
    label: "Iridium NEXT",
    color: "#c084fc",
    url: "https://celestrak.org/NORAD/elements/gp.php?GROUP=iridium-NEXT&FORMAT=tle",
    max: 100,
  },
  active: {
    label: "Active (all ~15,000)",
    color: "hsl(280 90% 70%)",
    url: "https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle",
    max: 15000,
  },
};

export interface SatRecord {
  name: string;
  category: Category;
  satrec: satellite.SatRec;
}

export interface SatPosition {
  name: string;
  category: Category;
  lat: number;
  lon: number;
  altKm: number;
  velocityKms: number;
  orbit: [number, number][];
  trail: [number, number][];
  overPakistan: boolean;
  tiltRange: boolean;       // within ~300 km of Pakistan border but not overhead
  nextPass: PassInfo | null;
  satrec?: satellite.SatRec;
  resolution_m?: number;
  country?: string;
  operator?: string;
  norad?: string;
  sensor?: string;
  sensor_category?: "Optical" | "SAR" | "Military";
}

export const PAKISTAN_BOUNDS = {
  minLat: 23,
  maxLat: 37,
  minLon: 60,
  maxLon: 78,
} as const;

// ~300 km buffer in degrees (2.7° lat, 3.1° lon at ~30°N)
export const TILT_BUFFER = { lat: 2.7, lon: 3.1 } as const;

export function isOverPakistan(lat: number, lon: number) {
  return (
    lat >= PAKISTAN_BOUNDS.minLat &&
    lat <= PAKISTAN_BOUNDS.maxLat &&
    lon >= PAKISTAN_BOUNDS.minLon &&
    lon <= PAKISTAN_BOUNDS.maxLon
  );
}

export function isInTiltRange(lat: number, lon: number) {
  if (isOverPakistan(lat, lon)) return false;
  return (
    lat >= PAKISTAN_BOUNDS.minLat - TILT_BUFFER.lat &&
    lat <= PAKISTAN_BOUNDS.maxLat + TILT_BUFFER.lat &&
    lon >= PAKISTAN_BOUNDS.minLon - TILT_BUFFER.lon &&
    lon <= PAKISTAN_BOUNDS.maxLon + TILT_BUFFER.lon
  );
}

// Surface-imaging recon only. Excludes SDA / missile-warning / SIGINT — sats
// that pass over PK but don't image the ground (e.g. PRAETORIAN looks up, not down).
export function isImagingThreat(p: { sensor_category?: string }): boolean {
  return p.sensor_category === "Optical"
      || p.sensor_category === "SAR"
      || p.sensor_category === "Military";
}

function parseTLE(text: string, category: Category, max: number): SatRecord[] {
  const lines = text.split(/\r?\n/).filter((l) => l.trim().length > 0);
  const records: SatRecord[] = [];
  for (let i = 0; i + 2 < lines.length; i += 3) {
    const name = lines[i].trim();
    const l1 = lines[i + 1];
    const l2 = lines[i + 2];
    if (!l1.startsWith("1 ") || !l2.startsWith("2 ")) continue;
    try {
      const satrec = satellite.twoline2satrec(l1, l2);
      records.push({ name, category, satrec });
    } catch {
      /* skip bad rec */
    }
    if (records.length >= max) break;
  }
  return records;
}

const TLE_CACHE_KEY = "tle-cache-v1";
const TLE_TTL_MS = 6 * 60 * 60 * 1000; // 6h

interface CacheEntry {
  fetchedAt: number;
  text: string;
}

async function tryFetch(url: string): Promise<string> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const text = await res.text();
  if (!text || text.length < 100) throw new Error("Empty TLE response");
  return text;
}

async function fetchTLE(category: Category): Promise<string> {
  const meta = CATEGORY_META[category];
  const cacheRaw = localStorage.getItem(TLE_CACHE_KEY);
  const cache: Record<string, CacheEntry> = cacheRaw ? JSON.parse(cacheRaw) : {};
  const entry = cache[category];
  if (entry && Date.now() - entry.fetchedAt < TLE_TTL_MS) {
    return entry.text;
  }
  const sources = [
    `/api/tle?category=${category}`,
    `https://api.allorigins.win/raw?url=${encodeURIComponent(meta.url)}`,
  ];
  let lastErr: unknown = null;
  for (const url of sources) {
    try {
      const text = await tryFetch(url);
      cache[category] = { fetchedAt: Date.now(), text };
      try { localStorage.setItem(TLE_CACHE_KEY, JSON.stringify(cache)); } catch { /* quota */ }
      return text;
    } catch (e) {
      lastErr = e;
    }
  }
  if (entry) return entry.text;
  throw lastErr ?? new Error("All TLE sources failed");
}

// Live positions from backend SGP4 propagation
export interface BackendPosition {
  name: string;
  lat: number;
  lon: number;
  altKm: number;
  velocityKms: number;
}

export async function fetchBackendPositions(category: Category, pakistanOnly = false): Promise<BackendPosition[]> {
  if (category === "hires-eo") {
    const res = await fetch("/api/positions/hires-eo");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const all = data.positions as (BackendPosition & { over_pakistan: boolean; tilt_range: boolean; zone: string; resolution_m?: number; country?: string; operator?: string; norad?: string })[];
    // In pakistanOnly mode, include overhead AND tilt-range satellites
    return pakistanOnly ? all.filter(p => p.over_pakistan || p.tilt_range) : all;
  }
  const endpoint = pakistanOnly ? `/api/positions/pakistan` : `/api/positions`;
  const res = await fetch(`${endpoint}?category=${category}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();
  return data.positions as BackendPosition[];
}

export interface SatMetadata {
  norad: string;
  name: string;
  operator: string;
  country: string;
  country_name: string;
  status: string;
  launch_date: string | null;
  image: string | null;
  website: string | null;
  purpose: string;
  source: string;
  destination: string;
  catalog_source: string;
}

const metaCache = new Map<string, SatMetadata>();

export async function fetchSatMetadata(norad: string): Promise<SatMetadata> {
  if (metaCache.has(norad)) return metaCache.get(norad)!;
  const res = await fetch(`/api/satellite/${norad}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json() as SatMetadata;
  metaCache.set(norad, data);
  return data;
}

export async function loadSatellites(categories: Category[]): Promise<SatRecord[]> {
  const all: SatRecord[] = [];
  for (const c of categories) {
    try {
      const txt = await fetchTLE(c);
      all.push(...parseTLE(txt, c, CATEGORY_META[c].max));
    } catch (e) {
      console.warn("Failed to load category", c, e);
    }
  }
  return all;
}

export function propagateAt(satrec: satellite.SatRec, date: Date) {
  const pv = satellite.propagate(satrec, date);
  if (!pv.position || typeof pv.position === "boolean") return null;
  const gmst = satellite.gstime(date);
  const geo = satellite.eciToGeodetic(pv.position as satellite.EciVec3<number>, gmst);
  const lat = satellite.degreesLat(geo.latitude);
  const lon = satellite.degreesLong(geo.longitude);
  const altKm = geo.height;
  let velocityKms = 0;
  if (pv.velocity && typeof pv.velocity !== "boolean") {
    const v = pv.velocity as satellite.EciVec3<number>;
    velocityKms = Math.sqrt(v.x * v.x + v.y * v.y + v.z * v.z);
  }
  return { lat, lon, altKm, velocityKms };
}

export function computePosition(
  rec: SatRecord,
  date: Date,
  includePass = false,
  includeTrail = false,
): SatPosition | null {
  const now = propagateAt(rec.satrec, date);
  if (!now) return null;
  // Future ground track: 90 min, 2 min steps
  const orbit: [number, number][] = [];
  for (let m = 0; m <= 90; m += 2) {
    const t = new Date(date.getTime() + m * 60_000);
    const p = propagateAt(rec.satrec, t);
    if (p) orbit.push([p.lat, p.lon]);
  }
  // Past ground track: last 30 min, 1 min steps (only when needed — selected sat)
  const trail: [number, number][] = [];
  if (includeTrail) {
    for (let m = -30; m <= 0; m += 1) {
      const t = new Date(date.getTime() + m * 60_000);
      const p = propagateAt(rec.satrec, t);
      if (p) trail.push([p.lat, p.lon]);
    }
  }
  let nextPass: PassInfo | null = null;
  if (includePass) {
    try {
      nextPass = predictNextPass(rec.satrec, date, 24, 5);
    } catch {
      nextPass = null;
    }
  }
  return {
    name: rec.name,
    category: rec.category,
    lat: now.lat,
    lon: now.lon,
    altKm: now.altKm,
    velocityKms: now.velocityKms,
    orbit,
    trail,
    overPakistan: isOverPakistan(now.lat, now.lon),
    tiltRange: isInTiltRange(now.lat, now.lon),
    nextPass,
    satrec: rec.satrec,
  };
}
