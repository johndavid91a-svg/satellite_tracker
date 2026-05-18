import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { SatelliteMap } from "@/components/SatelliteMap";
import { Sidebar } from "@/components/Sidebar";
import {
  CATEGORY_META,
  computePosition,
  loadSatellites,
  fetchBackendPositions,
  isOverPakistan as isOverPakistanCheck,
  isImagingThreat,
  type Category,
  type SatPosition,
  type SatRecord,
  type PassInfo,
} from "@/lib/satellites";
import { predictNextPass, PK_OBSERVER } from "@/lib/passes";
import { toast } from "sonner";

const Index = () => {
  const [enabled, setEnabled] = useState<Record<Category, boolean>>({
    "hires-eo":    true,   // ≤1m resolution EO satellites — ON by default
    stations:      false,
    starlink:      false,
    oneweb:        false,
    "gps-ops":     false,
    "glo-ops":     false,
    galileo:       false,
    beidou:        false,
    weather:       false,
    resource:      false,
    military:      false,
    geo:           false,
    "iridium-NEXT": false,
    active:        false,
  });
  const [records, setRecords] = useState<SatRecord[]>([]);
  const [positions, setPositions] = useState<SatPosition[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [pakistanOnly, setPakistanOnly] = useState(true);
  const [showNonImaging, setShowNonImaging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [now, setNow] = useState(new Date());
  const [passes, setPasses] = useState<Record<string, PassInfo | null>>({});
  const [passProgress, setPassProgress] = useState({ done: 0, total: 0 });
  const tickRef = useRef<number | null>(null);

  // Load TLE data when categories change (needed for pass prediction + trail)
  useEffect(() => {
    const cats = (Object.keys(enabled) as Category[]).filter((c) => enabled[c]);
    if (cats.length === 0) {
      setRecords([]);
      setPasses({});
      return;
    }
    let cancelled = false;
    setLoading(true);
    loadSatellites(cats)
      .then((recs) => {
        if (cancelled) return;
        setRecords(recs);
        setPasses({});
        toast.success(`Loaded ${recs.length} satellites`, {
          description: cats.map((c) => CATEGORY_META[c].label).join(" · "),
        });
      })
      .catch((e) => {
        console.error(e);
        toast.error("Failed to fetch TLE data", { description: "Using cached data if available." });
      })
      .finally(() => !cancelled && setLoading(false));
    return () => { cancelled = true; };
  }, [enabled]);

  // Build a name→satrec lookup for fast access
  const recordMap = useMemo(() => {
    const m = new Map<string, SatRecord>();
    for (const r of records) m.set(r.name, r);
    return m;
  }, [records]);

  const selectedRef = useRef<string | null>(null);
  selectedRef.current = selected;

  // Merge backend live positions with browser SGP4 (for orbit/trail/pass)
  const buildPositions = useCallback(
    (backendMap: Map<string, { lat: number; lon: number; altKm: number; velocityKms: number }>, date: Date): SatPosition[] => {
      const out: SatPosition[] = [];
      const sel = selectedRef.current;

      // Satellites we have TLE records for
      for (const r of records) {
        // Skip if this satellite's category is disabled
        if (!enabled[r.category]) continue;
        // Also skip by name pattern if loaded from 'active' group but specific category is disabled
        const nameUp = r.name.toUpperCase();
        if (!enabled["starlink"]    && nameUp.includes("STARLINK"))   continue;
        if (!enabled["oneweb"]      && nameUp.includes("ONEWEB"))     continue;
        if (!enabled["gps-ops"]     && (nameUp.includes("GPS BIIR") || nameUp.includes("NAVSTAR"))) continue;
        if (!enabled["glo-ops"]     && nameUp.includes("GLONASS"))    continue;
        if (!enabled["galileo"]     && nameUp.includes("GALILEO"))    continue;
        if (!enabled["beidou"]      && (nameUp.includes("BEIDOU") || nameUp.includes("COMPASS"))) continue;
        if (!enabled["iridium-NEXT"] && nameUp.includes("IRIDIUM"))   continue;
        const live = backendMap.get(r.name);
        const p = computePosition(r, date, false, r.name === sel);
        if (!p) continue;
        // Override lat/lon/alt/velocity with backend data when available
        if (live) {
          p.lat = live.lat;
          p.lon = live.lon;
          p.altKm = live.altKm;
          p.velocityKms = live.velocityKms;
          p.overPakistan = (live as any).over_pakistan ?? isOverPakistanCheck(live.lat, live.lon);
          p.tiltRange    = (live as any).tilt_range ?? false;
          if ((live as any).resolution_m)     p.resolution_m    = (live as any).resolution_m;
          if ((live as any).country)          p.country         = (live as any).country;
          if ((live as any).operator)         p.operator        = (live as any).operator;
          if ((live as any).norad)            p.norad           = (live as any).norad;
          if ((live as any).sensor)           p.sensor          = (live as any).sensor;
          if ((live as any).sensor_category)  p.sensor_category = (live as any).sensor_category;
        }
        p.nextPass = passes[r.name] ?? null;
        out.push(p);
      }

      // Satellites from backend that have no TLE record yet (backend loaded faster)
      for (const [name, live] of backendMap) {
        if (recordMap.has(name)) continue;
        // Infer category from name so toggle filtering works correctly
        const nameUp = name.toUpperCase();
        let inferredCat: Category = "active";
        if (nameUp.includes("STARLINK"))   inferredCat = "starlink";
        else if (nameUp.includes("ONEWEB")) inferredCat = "oneweb";
        else if (nameUp.includes("KUIPER")) inferredCat = "active";
        else if (nameUp.includes("GPS") || nameUp.includes("NAVSTAR")) inferredCat = "gps-ops";
        else if (nameUp.includes("GLONASS") || nameUp.includes("COSMOS")) inferredCat = "glo-ops";
        else if (nameUp.includes("GALILEO")) inferredCat = "galileo";
        else if (nameUp.includes("BEIDOU") || nameUp.includes("COMPASS")) inferredCat = "beidou";
        else if (nameUp.includes("NOAA") || nameUp.includes("METEOR") || nameUp.includes("METOP")) inferredCat = "weather";
        else if (nameUp.includes("IRIDIUM")) inferredCat = "iridium-NEXT";
        // Skip if this inferred category is disabled
        if (!enabled[inferredCat]) continue;
        out.push({
          name,
          category: inferredCat,
          lat: live.lat,
          lon: live.lon,
          altKm: live.altKm,
          velocityKms: live.velocityKms,
          orbit: [],
          trail: [],
          overPakistan: (live as any).over_pakistan ?? isOverPakistanCheck(live.lat, live.lon),
          tiltRange:    (live as any).tilt_range ?? false,
          nextPass: null,
          resolution_m:    (live as any).resolution_m,
          country:         (live as any).country,
          operator:        (live as any).operator,
          norad:           (live as any).norad,
          sensor:          (live as any).sensor,
          sensor_category: (live as any).sensor_category,
        });
      }
      const visible = showNonImaging ? out : out.filter(isImagingThreat);
      return pakistanOnly
        ? visible.filter((p) => p.overPakistan || p.tiltRange)
        : visible;
    },
    [records, passes, recordMap, pakistanOnly, enabled, showNonImaging]
  );

  // Backend positions poll (every 5 s per enabled category)
  const backendMapRef = useRef<Map<string, { lat: number; lon: number; altKm: number; velocityKms: number }>>(new Map());
  const pakistanOnlyRef = useRef(pakistanOnly);
  pakistanOnlyRef.current = pakistanOnly;

  useEffect(() => {
    const cats = (Object.keys(enabled) as Category[]).filter((c) => enabled[c]);
    if (cats.length === 0) return;
    let cancelled = false;

    const poll = async () => {
      if (cancelled) return;
      const next = new Map<string, { lat: number; lon: number; altKm: number; velocityKms: number }>();
      await Promise.allSettled(
        cats.map(async (cat) => {
          try {
            const positions = await fetchBackendPositions(cat, pakistanOnlyRef.current);
            for (const p of positions) next.set(p.name, p);
          } catch {
            // backend unavailable — keep existing entries
          }
        })
      );
      if (!cancelled) backendMapRef.current = next;
    };

    poll();
    // Backend poll cadence — SGP4 is exact, so the backend is just a
    // ground-truth sync. 2s keeps it fresh without hammering the server.
    const id = window.setInterval(poll, 2000);
    return () => { cancelled = true; clearInterval(id); };
  }, [enabled, pakistanOnly]);

  // React state tick — drives badge counts ("OVER PK", "TRACKED") and the
  // selected-satellite popup. Marker MOTION on the map is handled by the
  // RAF loop in SatelliteMap which propagates SGP4 at every frame.
  // 1 s is plenty here — the visible counters don't need higher resolution.
  useEffect(() => {
    let running = true;
    const tick = () => {
      if (!running) return;
      const date = new Date();
      setPositions(buildPositions(backendMapRef.current, date));
      setNow(date);
      tickRef.current = window.setTimeout(tick, 1000) as unknown as number;
    };
    tick();
    return () => {
      running = false;
      if (tickRef.current) clearTimeout(tickRef.current);
    };
  }, [buildPositions]);

  // Background pass prediction in chunks (non-blocking)
  useEffect(() => {
    if (records.length === 0) return;
    let cancelled = false;
    setPassProgress({ done: 0, total: records.length });
    const fromDate = new Date();
    const next: Record<string, PassInfo | null> = {};
    let i = 0;
    const CHUNK = 8;

    const runChunk = () => {
      if (cancelled) return;
      const end = Math.min(i + CHUNK, records.length);
      for (; i < end; i++) {
        const r = records[i];
        try {
          next[r.name] = predictNextPass(r.satrec, fromDate, 24, 5);
        } catch {
          next[r.name] = null;
        }
      }
      setPassProgress({ done: i, total: records.length });
      if (i < records.length) {
        setTimeout(runChunk, 0); // yield to UI
      } else {
        setPasses({ ...next });
      }
    };
    runChunk();
    return () => {
      cancelled = true;
    };
  }, [records]);

  const toggle = (c: Category) => setEnabled((e) => ({ ...e, [c]: !e[c] }));

  const overPk = useMemo(() => positions.filter((p) => p.overPakistan).length, [positions]);

  // Optical vs SAR split for the top bar — operator reads two distinct
  // threat tracks: visible-light (need daylight) and radar (any time,
  // through cloud). "Military" platforms get bucketed by their sensor
  // string: SAR-X-band-Military -> SAR, Optical-Military -> Optical.
  const opticalTracked = useMemo(
    () => positions.filter((p) => {
      const sc = (p as any).sensor_category as string | undefined;
      const sn = String((p as any).sensor || "").toUpperCase();
      if (sc === "Optical") return true;
      if (sc === "Military" && !sn.includes("SAR")) return true;
      return false;
    }).length, [positions]);
  const sarTracked = useMemo(
    () => positions.filter((p) => {
      const sc = (p as any).sensor_category as string | undefined;
      const sn = String((p as any).sensor || "").toUpperCase();
      if (sc === "SAR") return true;
      if (sc === "Military" && sn.includes("SAR")) return true;
      return false;
    }).length, [positions]);
  const opticalOverPk = useMemo(
    () => positions.filter((p) => {
      if (!p.overPakistan) return false;
      const sc = (p as any).sensor_category as string | undefined;
      const sn = String((p as any).sensor || "").toUpperCase();
      return sc === "Optical" || (sc === "Military" && !sn.includes("SAR"));
    }).length, [positions]);
  const sarOverPk = useMemo(
    () => positions.filter((p) => {
      if (!p.overPakistan) return false;
      const sc = (p as any).sensor_category as string | undefined;
      const sn = String((p as any).sensor || "").toUpperCase();
      return sc === "SAR" || (sc === "Military" && sn.includes("SAR"));
    }).length, [positions]);

  const passesComputed = passProgress.done >= passProgress.total && passProgress.total > 0;

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-background">
      <div className="w-[340px] shrink-0 p-3">
        <Sidebar
          positions={positions}
          enabled={enabled}
          onToggle={toggle}
          selected={selected}
          onSelect={setSelected}
          pakistanOnly={pakistanOnly}
          onTogglePakistanOnly={setPakistanOnly}
          showNonImaging={showNonImaging}
          onToggleShowNonImaging={setShowNonImaging}
          loading={loading}
          lastUpdate={now}
          passProgress={passProgress}
        />
      </div>

      <main className="relative flex-1 p-3 pl-0">
        <div className="panel scanline relative h-full w-full overflow-hidden">
          <div className="pointer-events-none absolute inset-x-0 top-0 z-[500] flex items-start justify-between px-4 py-2 text-[10px] uppercase tracking-widest">
            <div className="rounded bg-background/70 px-2 py-1 font-mono text-primary backdrop-blur">
              ◉ LIVE · {(() => { const pkt = new Date(now.getTime() + 5*3600*1000); return pkt.toUTCString().slice(17, 25); })()} PKT
            </div>
            {/* Optical (top row) / SAR (bottom row) split — operator-requested
                separation so the two threat tracks read at-a-glance. */}
            <div className="flex flex-col items-end gap-1">
              <div className="flex gap-2">
                <Badge label="OPTICAL" mono="#22d3ee" />
                <Badge label={`${opticalTracked} TRACKED`}  mono="#22d3ee" />
                <Badge label={`${opticalOverPk} OVER PK`}   mono="#22d3ee" accent />
              </div>
              <div className="flex gap-2">
                <Badge label="SAR"     mono="#a855f7" />
                <Badge label={`${sarTracked} TRACKED`}      mono="#a855f7" />
                <Badge label={`${sarOverPk} OVER PK`}       mono="#a855f7" accent />
              </div>
              {!passesComputed && passProgress.total > 0 && (
                <div className="flex gap-2">
                  <Badge label={`PASSES ${passProgress.done}/${passProgress.total}`} />
                </div>
              )}
            </div>
          </div>

          <Corner pos="tl" />
          <Corner pos="tr" />
          <Corner pos="bl" />
          <Corner pos="br" />

          <SatelliteMap
            positions={positions}
            selected={selected}
            onSelect={setSelected}
            showOrbits={true}
            now={now}
          />

          <div className="pointer-events-none absolute inset-x-0 bottom-0 z-[500] flex justify-between px-4 py-2 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
            <span>SGP4 · Observer: {PK_OBSERVER.name} {PK_OBSERVER.latDeg.toFixed(2)}°N {PK_OBSERVER.lonDeg.toFixed(2)}°E</span>
            <span>Pakistan AOI · 23–37°N · 60–78°E</span>
          </div>
        </div>
      </main>
    </div>
  );
};

const Badge = ({ label, accent, mono }: { label: string; accent?: boolean; mono?: string }) => {
  // When `mono` is supplied we override the standard primary/accent palette
  // with a single per-track colour (cyan for Optical, violet for SAR) so the
  // two rows of stats stay visually distinct.
  if (mono) {
    const style: React.CSSProperties = accent
      ? { borderColor: mono, background: `${mono}22`, color: mono, boxShadow: `0 0 8px ${mono}55` }
      : { borderColor: `${mono}88`, background: "rgba(0,0,0,0.5)", color: mono };
    return (
      <div className="rounded border px-2 py-1 font-mono backdrop-blur" style={style}>
        {label}
      </div>
    );
  }
  return (
    <div
      className={`rounded border px-2 py-1 font-mono backdrop-blur ${
        accent
          ? "border-accent/60 bg-accent/10 text-accent shadow-glow-accent"
          : "border-primary/40 bg-background/70 text-primary"
      }`}
    >
      {label}
    </div>
  );
};

const Corner = ({ pos }: { pos: "tl" | "tr" | "bl" | "br" }) => {
  const map: Record<string, string> = {
    tl: "top-2 left-2 border-t-2 border-l-2",
    tr: "top-2 right-2 border-t-2 border-r-2",
    bl: "bottom-2 left-2 border-b-2 border-l-2",
    br: "bottom-2 right-2 border-b-2 border-r-2",
  };
  return (
    <div
      className={`pointer-events-none absolute z-[600] h-4 w-4 border-primary/60 ${map[pos]}`}
    />
  );
};

export default Index;
