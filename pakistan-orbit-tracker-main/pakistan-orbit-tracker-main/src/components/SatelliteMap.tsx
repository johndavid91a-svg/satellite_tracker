import { useEffect, useRef, useState, useMemo } from "react";
import {
  MapContainer, TileLayer, Polyline, Polygon, useMap, useMapEvents,
} from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import {
  CATEGORY_META, PAKISTAN_BOUNDS, TILT_BUFFER, propagateAt,
  type SatPosition, type SatMetadata, fetchSatMetadata,
} from "@/lib/satellites";
import type * as satellite from "satellite.js";
import { formatCountdown, formatPassTime } from "@/lib/passes";

/* ── constants ──────────────────────────────────────────────────────────────── */
const PK_CENTER: [number, number] = [30.3753, 69.3451];
const PK_BOUNDS = L.latLngBounds(
  [PAKISTAN_BOUNDS.minLat - 3, PAKISTAN_BOUNDS.minLon - 3],
  [PAKISTAN_BOUNDS.maxLat + 3, PAKISTAN_BOUNDS.maxLon + 3],
);
const PAKISTAN_POLY: [number, number][] = [
  [PAKISTAN_BOUNDS.minLat, PAKISTAN_BOUNDS.minLon],
  [PAKISTAN_BOUNDS.minLat, PAKISTAN_BOUNDS.maxLon],
  [PAKISTAN_BOUNDS.maxLat, PAKISTAN_BOUNDS.maxLon],
  [PAKISTAN_BOUNDS.maxLat, PAKISTAN_BOUNDS.minLon],
];
// ~300 km buffer around Pakistan border
const TILT_POLY: [number, number][] = [
  [PAKISTAN_BOUNDS.minLat - TILT_BUFFER.lat, PAKISTAN_BOUNDS.minLon - TILT_BUFFER.lon],
  [PAKISTAN_BOUNDS.minLat - TILT_BUFFER.lat, PAKISTAN_BOUNDS.maxLon + TILT_BUFFER.lon],
  [PAKISTAN_BOUNDS.maxLat + TILT_BUFFER.lat, PAKISTAN_BOUNDS.maxLon + TILT_BUFFER.lon],
  [PAKISTAN_BOUNDS.maxLat + TILT_BUFFER.lat, PAKISTAN_BOUNDS.minLon - TILT_BUFFER.lon],
];
const TICK_MS = 200; // SGP4 update interval — short enough to feel continuous

/* ── helpers ────────────────────────────────────────────────────────────────── */
function lerp(a: number, b: number, t: number) { return a + (b - a) * t; }

function bearing(la1: number, lo1: number, la2: number, lo2: number) {
  const r = Math.PI / 180;
  const f1 = la1 * r, f2 = la2 * r, dl = (lo2 - lo1) * r;
  return ((Math.atan2(Math.sin(dl) * Math.cos(f2),
    Math.cos(f1) * Math.sin(f2) - Math.sin(f1) * Math.cos(f2) * Math.cos(dl))
    * 180 / Math.PI) + 360) % 360;
}
const DIRS = ["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"];
const dir = (d: number) => DIRS[Math.round(d / 22.5) % 16];
const fLat = (v: number) => `${Math.abs(v).toFixed(4)}° ${v >= 0 ? "N" : "S"}`;
const fLon = (v: number) => `${Math.abs(v).toFixed(4)}° ${v >= 0 ? "E" : "W"}`;

function flagEmoji(cc: string): string {
  return cc.split(",").map(c => {
    c = c.trim();
    if (c.length !== 2) return c;
    const o = 0x1F1E6 - 65;
    return String.fromCodePoint(c.charCodeAt(0) + o) + String.fromCodePoint(c.charCodeAt(1) + o);
  }).join(" ");
}

function splitOrbit(pts: [number, number][]): [number, number][][] {
  const out: [number, number][][] = []; let cur: [number, number][] = [];
  for (const p of pts) {
    if (cur.length && Math.abs(p[1] - cur[cur.length - 1][1]) > 180) { out.push(cur); cur = []; }
    cur.push(p);
  }
  if (cur.length) out.push(cur);
  return out;
}

/* ── smooth fly-to ──────────────────────────────────────────────────────────── */
function FlyTo({ target }: { target: SatPosition | null }) {
  const map = useMap();
  const prev = useRef<string | null>(null);
  useEffect(() => {
    if (!target || target.name === prev.current) return;
    prev.current = target.name;
    setTimeout(() => {
      map.flyTo([target.lat, target.lon], Math.max(map.getZoom(), 7), {
        duration: 1.2, easeLinearity: 0.2,
      });
    }, 80);
  }, [target, map]);
  return null;
}

function MapClickHandler({ onDeselect }: { onDeselect: () => void }) {
  useMapEvents({ click: onDeselect });
  return null;
}

/* ── imperative smooth markers layer ───────────────────────────────────────── */
// Each satellite gets one L.marker with a directional arrow icon.
// Each frame we propagate SGP4 at real-time for satellites that have a
// satrec, giving continuous 60 fps motion with zero interpolation lag.
// Satellites without a satrec (backend-only) fall back to lerp.
interface MarkerState {
  marker: L.Marker;
  popup: L.Popup;
  satrec?: satellite.SatRec;
  fromLat: number; fromLon: number;
  toLat: number;   toLon: number;
  updatedAt: number;
  // Per-satellite tilt-standoff overlay (only for sub-metre optical/SAR
  // sats per FEAT-003). The "light" is rendered as a stack of concentric
  // translucent circles (inner-bright -> outer-faint) to fake a radial
  // gradient that fades from the satellite out to its standoff radius,
  // plus a thin dashed boundary so the exact km is still readable.
  // glowLayers includes the boundary circle too; all of them follow the
  // satellite in the RAF loop and get destroyed together on removal.
  glowLayers:  L.Circle[];
  tiltTooltip: L.Tooltip | null;
  standoffKm:  number    | null;
  isSubMeter:  boolean;
}

function SmoothMarkers({
  positions, selected, onSelect, now, onReplay,
}: {
  positions: SatPosition[];
  selected: string | null;
  onSelect: (name: string | null) => void;
  now: Date;
  onReplay: (trail: [number, number][], color: string) => void;
}) {
  const map = useMap();
  const stateRef = useRef<Map<string, MarkerState>>(new Map());
  const rafRef = useRef<number | null>(null);
  const posRef = useRef<SatPosition[]>([]);
  const selectedRef = useRef<string | null>(null);
  const nowRef = useRef<Date>(now);
  const onSelectRef = useRef(onSelect);
  const onReplayRef = useRef(onReplay);

  // keep refs current without re-running effects
  posRef.current = positions;
  selectedRef.current = selected;
  nowRef.current = now;
  onSelectRef.current = onSelect;
  onReplayRef.current = onReplay;

  // ── sync markers when positions array changes (new sats / removed sats) ──
  useEffect(() => {
    const existing = stateRef.current;
    const names = new Set(positions.map(p => p.name));

    // remove stale markers (plus their tilt-coverage glow stack / tooltip)
    for (const [name, s] of existing) {
      if (!names.has(name)) {
        s.marker.remove();
        s.popup.remove();
        for (const c of s.glowLayers) c.remove();
        s.tiltTooltip?.remove();
        existing.delete(name);
      }
    }

    // add / update markers
    const ts = performance.now();
    for (const p of positions) {
      const baseColor = (p as any).sensor_category === "Military" ? "#ef4444"
        : (p as any).sensor_category === "SAR" ? "#a855f7"
        : CATEGORY_META[p.category].color;
      const color = p.tiltRange ? "#f59e0b" : baseColor;
      const isSel = p.name === selected;
      // Calculate heading from orbit track
      const hdg = p.orbit[1] ? bearing(p.lat, p.lon, p.orbit[1][0], p.orbit[1][1]) : 0;

      // Satellite realistic icon — white/silver body with gold solar panels, rotated by heading
      const makeSatIcon = (sel: boolean, heading: number) => {
        const s = sel ? 28 : 18;
        const glow = sel ? `filter:drop-shadow(0 0 4px rgba(255,255,255,0.8)) drop-shadow(0 0 8px rgba(200,200,255,0.5));` : `filter:drop-shadow(0 0 1px rgba(255,255,255,0.4));`;
        // Realistic satellite SVG — silver/white body + gold solar panels
        const svg = `<svg viewBox="0 0 48 24" width="${s * 2}" height="${s}" xmlns="http://www.w3.org/2000/svg">
          <!-- Left solar panel -->
          <rect x="0" y="8" width="14" height="8" rx="1" fill="#c8a84b" stroke="#a07830" stroke-width="0.5"/>
          <line x1="2" y1="8" x2="2" y2="16" stroke="#a07830" stroke-width="0.4" opacity="0.6"/>
          <line x1="5" y1="8" x2="5" y2="16" stroke="#a07830" stroke-width="0.4" opacity="0.6"/>
          <line x1="8" y1="8" x2="8" y2="16" stroke="#a07830" stroke-width="0.4" opacity="0.6"/>
          <line x1="11" y1="8" x2="11" y2="16" stroke="#a07830" stroke-width="0.4" opacity="0.6"/>
          <!-- Left panel connector -->
          <rect x="14" y="11" width="3" height="2" fill="#888" stroke="#666" stroke-width="0.3"/>
          <!-- Main body -->
          <rect x="17" y="6" width="14" height="12" rx="2" fill="#d0d0d0" stroke="#999" stroke-width="0.5"/>
          <rect x="18" y="7" width="12" height="10" rx="1.5" fill="#e8e8e8"/>
          <!-- Body detail lines -->
          <line x1="21" y1="7" x2="21" y2="17" stroke="#bbb" stroke-width="0.4" opacity="0.7"/>
          <line x1="24" y1="7" x2="24" y2="17" stroke="#bbb" stroke-width="0.4" opacity="0.7"/>
          <line x1="27" y1="7" x2="27" y2="17" stroke="#bbb" stroke-width="0.4" opacity="0.7"/>
          <!-- Antenna -->
          <line x1="24" y1="6" x2="24" y2="2" stroke="#ccc" stroke-width="0.8"/>
          <circle cx="24" cy="1.5" r="1.2" fill="#ddd" stroke="#aaa" stroke-width="0.4"/>
          <!-- Right panel connector -->
          <rect x="31" y="11" width="3" height="2" fill="#888" stroke="#666" stroke-width="0.3"/>
          <!-- Right solar panel -->
          <rect x="34" y="8" width="14" height="8" rx="1" fill="#c8a84b" stroke="#a07830" stroke-width="0.5"/>
          <line x1="36" y1="8" x2="36" y2="16" stroke="#a07830" stroke-width="0.4" opacity="0.6"/>
          <line x1="39" y1="8" x2="39" y2="16" stroke="#a07830" stroke-width="0.4" opacity="0.6"/>
          <line x1="42" y1="8" x2="42" y2="16" stroke="#a07830" stroke-width="0.4" opacity="0.6"/>
          <line x1="45" y1="8" x2="45" y2="16" stroke="#a07830" stroke-width="0.4" opacity="0.6"/>
          ${sel ? `<rect x="15" y="4" width="18" height="16" rx="3" fill="none" stroke="white" stroke-width="1.2" opacity="0.9"/>` : ''}
        </svg>`;
        return L.divIcon({
          className: "",
          html: `<div style="width:${s * 2}px;height:${s}px;transform:rotate(${heading}deg);transform-origin:center;${glow}">${svg}</div>`,
          iconSize: [s * 2, s],
          iconAnchor: [s, s / 2],
        });
      };

      if (!existing.has(p.name)) {
        const icon = makeSatIcon(isSel, hdg);
        const marker = L.marker([p.lat, p.lon], {
          icon,
          bubblingMouseEvents: false,
          zIndexOffset: isSel ? 1000 : 0,
        }).addTo(map);

        const popup = L.popup({
          autoPan: true,
          autoPanPadding: [30, 30],
          closeButton: false,
          className: "pk-popup",
          maxWidth: 310,
          minWidth: 270,
        });

        marker.bindPopup(popup);

        marker.on("click", (e) => {
          L.DomEvent.stopPropagation(e);
          const name = p.name;
          const isSel = selectedRef.current === name;
          onSelectRef.current(isSel ? null : name);
          if (!isSel) {
            renderPopup(popup, posRef.current.find(x => x.name === name)!, color, nowRef, onReplayRef, map);
            marker.openPopup();
          }
        });

        // ── Per-sat tilt-coverage LIGHT for ≤1 m optical / SAR / military ──
        // Render the standoff radius as a stack of concentric circles to
        // fake a radial-gradient glow that fades from the satellite out to
        // its standoff_km boundary. Pure SVG, no CSS filters — keeps it
        // GPU-cheap and predictable across Chrome/Firefox/WebKit.
        const resM     = (p as any).resolution_m as number | undefined;
        const tiltDeg  = (p as any).max_tilt_deg as number | undefined;
        const soKm     = (p as any).tilt_standoff_km as number | undefined;
        const sensorC  = (p as any).sensor_category as string | undefined;
        const isSubMeter = !!(resM !== undefined && resM <= 1.0
                           && sensorC && ["Optical","SAR","Military"].includes(sensorC));

        const glowLayers: L.Circle[] = [];
        let tiltTooltip: L.Tooltip | null = null;
        if (isSubMeter && soKm && soKm > 0 && tiltDeg !== undefined) {
          const rMeters = soKm * 1000;
          // 4-layer radial-gradient illusion:
          //   inner (r=0.30) — bright core, "the sensor is here"
          //   warm  (r=0.55) — mid-distance falloff
          //   halo  (r=0.85) — soft outer shoulder
          //   edge  (r=1.00) — thin dashed boundary at exact standoff_km
          //
          // Order matters: add OUTER first so inner layers paint on top.
          glowLayers.push(L.circle([p.lat, p.lon], {
            radius: rMeters * 0.85,
            stroke: false, color,
            fillColor: color, fillOpacity: 0.035,
            interactive: false,
          }).addTo(map));
          glowLayers.push(L.circle([p.lat, p.lon], {
            radius: rMeters * 0.55,
            stroke: false, color,
            fillColor: color, fillOpacity: 0.06,
            interactive: false,
          }).addTo(map));
          glowLayers.push(L.circle([p.lat, p.lon], {
            radius: rMeters * 0.30,
            stroke: false, color,
            fillColor: color, fillOpacity: 0.11,
            interactive: false,
          }).addTo(map));
          // Boundary at exact standoff km — dashed, no fill so it sits
          // on top of the glow without dimming it.
          glowLayers.push(L.circle([p.lat, p.lon], {
            radius: rMeters,
            color, weight: 1.1, opacity: 0.75,
            fill: false,
            dashArray: "3 6",
            interactive: false,
          }).addTo(map));

          // Permanent tooltip anchored to the marker that shows tilt + standoff.
          tiltTooltip = L.tooltip({
            permanent: true,
            direction: "right",
            offset: [12, 0],
            className: "pk-tilt-tip",
            opacity: 0.9,
          }).setContent(
            `<span style="font:600 9px ui-monospace,monospace;color:${color};` +
            `background:rgba(0,0,0,0.55);padding:1px 5px;border-radius:3px;` +
            `border:1px solid ${color}44">T ${tiltDeg}° · ${Math.round(soKm)} km</span>`
          );
          marker.bindTooltip(tiltTooltip);
        }

        existing.set(p.name, {
          marker, popup,
          satrec: p.satrec,
          fromLat: p.lat, fromLon: p.lon,
          toLat: p.lat, toLon: p.lon,
          updatedAt: ts,
          glowLayers, tiltTooltip,
          standoffKm: soKm ?? null,
          isSubMeter,
        });
      } else {
        // update interpolation targets (used only for satellites without a satrec)
        const s = existing.get(p.name)!;
        const cur = s.marker.getLatLng();
        s.satrec = p.satrec ?? s.satrec;
        s.fromLat = cur.lat;
        s.fromLon = cur.lng;
        s.toLat = p.lat;
        s.toLon = p.lon;
        s.updatedAt = ts;

        // update icon with new heading and selection state
        s.marker.setIcon(makeSatIcon(isSel, hdg));
        s.marker.setZIndexOffset(isSel ? 1000 : 0);

        // refresh open popup content
        if (s.marker.isPopupOpen()) {
          renderPopup(s.popup, p, color, nowRef, onReplayRef, map);
        }
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [positions, selected]);

  // ── RAF loop: propagate SGP4 at real-time, 60 fps ──
  // For every marker that has a satrec we compute the exact orbital
  // position at `new Date()` each frame — zero interpolation, zero lag.
  // Markers without a satrec (backend-only) fall back to linear lerp
  // between the last two ticks. The per-sat tilt-coverage circle (if any)
  // tracks the marker so the standoff radius always orbits with the sat.
  useEffect(() => {
    const tick = () => {
      const wallNow = new Date();
      const perfNow = performance.now();
      for (const s of stateRef.current.values()) {
        let ll: L.LatLngExpression | null = null;
        if (s.satrec) {
          const p = propagateAt(s.satrec, wallNow);
          if (p) {
            ll = [p.lat, p.lon];
            s.marker.setLatLng(ll);
          }
        }
        if (ll === null) {
          // fall back to linear interpolation between the last two ticks
          const elapsed = perfNow - s.updatedAt;
          const t = Math.min(elapsed / TICK_MS, 1);
          ll = [lerp(s.fromLat, s.toLat, t), lerp(s.fromLon, s.toLon, t)];
          s.marker.setLatLng(ll);
        }
        for (const c of s.glowLayers) c.setLatLng(ll);
      }
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => { if (rafRef.current) cancelAnimationFrame(rafRef.current); };
  }, []);

  // ── pulse ring + amplified standoff "spotlight" for selected satellite ──
  // The always-on glow stack on every ≤1m sat is intentionally subtle so
  // 35 of them don't drown the map. When the user picks one, we layer
  // brighter circles on top: a punchy core + a solid bright boundary so
  // the selected sat's footprint visually pops above its neighbours.
  const pulseRef  = useRef<L.Marker | null>(null);
  const selGlowRef = useRef<L.Circle[]>([]);
  useEffect(() => {
    pulseRef.current?.remove(); pulseRef.current = null;
    for (const c of selGlowRef.current) c.remove();
    selGlowRef.current = [];
    if (!selected) return;
    const p = positions.find(x => x.name === selected);
    if (!p) return;
    const color = (p as any).sensor_category === "Military" ? "#ef4444"
              : (p as any).sensor_category === "SAR"      ? "#a855f7"
              : CATEGORY_META[p.category].color;
    const icon = L.divIcon({
      className: "",
      html: `<span class="pk-pulse" style="--c:${color}"></span>`,
      iconSize: [44, 44], iconAnchor: [22, 22],
    });
    pulseRef.current = L.marker([p.lat, p.lon], { icon, interactive: false, zIndexOffset: -100 }).addTo(map);

    // Selected-sat spotlight: brighter glow on top of the base stack.
    const standoffKm = (p as any).tilt_standoff_km as number | undefined;
    if (standoffKm && standoffKm > 0) {
      const rMeters = standoffKm * 1000;
      // Bright core (overlays the base inner glow)
      selGlowRef.current.push(L.circle([p.lat, p.lon], {
        radius: rMeters * 0.30, stroke: false, color,
        fillColor: color, fillOpacity: 0.18,
        interactive: false,
      }).addTo(map));
      // Solid bright boundary at exact standoff km
      selGlowRef.current.push(L.circle([p.lat, p.lon], {
        radius: rMeters,
        color, weight: 2, opacity: 1,
        fillColor: color, fillOpacity: 0.06,
        dashArray: "5 4",
        interactive: false,
      }).addTo(map));
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected, positions, map]);

  // update pulse ring + selected-sat spotlight every frame via the same RAF loop
  useEffect(() => {
    const tick = () => {
      if (selectedRef.current) {
        const s = stateRef.current.get(selectedRef.current);
        if (s) {
          const ll = s.marker.getLatLng();
          if (pulseRef.current) pulseRef.current.setLatLng(ll);
          for (const c of selGlowRef.current) c.setLatLng(ll);
        }
      }
      requestAnimationFrame(tick);
    };
    const id = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(id);
  }, []);

  return null;
}

/* ── popup content renderer (imperative, no React) ─────────────────────────── */
function renderPopup(
  popup: L.Popup,
  p: SatPosition,
  color: string,
  nowRef: React.MutableRefObject<Date>,
  onReplayRef: React.MutableRefObject<(trail: [number, number][], color: string) => void>,
  map: L.Map,
) {
  const now = nowRef.current;
  const hdg = p.orbit[1] ? bearing(p.lat, p.lon, p.orbit[1][0], p.orbit[1][1]) : null;
  const period = p.altKm > 0
    ? (2 * Math.PI * Math.sqrt(Math.pow(6371 + p.altKm, 3) / 398600.4418)) / 60 : null;
  const norad = String((p as any).satrec?.satnum ?? "").trim();

  const row = (label: string, value: string, accent = false, dim = false) =>
    `<span style="color:${color}88;font-size:10px">${label}</span>
     <span style="font-size:11px;font-weight:${accent ? 700 : 400};color:${accent ? color : dim ? "rgba(255,255,255,0.4)" : "rgba(255,255,255,0.85)"}">${value}</span>`;

  const section = (title: string) =>
    `<div style="font-size:9px;text-transform:uppercase;letter-spacing:.1em;color:${color};border-bottom:1px solid ${color}33;margin-top:10px;margin-bottom:4px;padding-bottom:2px">${title}</div>`;

  const grid = (rows: string) =>
    `<div style="display:grid;grid-template-columns:90px 1fr;gap:2px 10px;margin-bottom:2px">${rows}</div>`;

  const passHtml = p.nextPass
    ? section("Next Pass · Islamabad") + grid(
        row("AOS", formatPassTime(p.nextPass.aos)) +
        row("LOS", formatPassTime(p.nextPass.los)) +
        row("Max Elev", `${p.nextPass.maxElDeg.toFixed(1)}°`, true) +
        row("Duration", `${Math.floor(p.nextPass.durationSec / 60)}m ${p.nextPass.durationSec % 60}s`) +
        row("In", formatCountdown(p.nextPass.aos, now))
      )
    : `<div style="font-size:10px;opacity:.45;font-style:italic;margin-top:6px">No pass over Islamabad in next 24h</div>`;

  const trailBtn = p.trail.length > 1
    ? `<button id="pk-trail-btn" style="width:100%;margin-top:8px;padding:5px 0;background:transparent;border:1px solid ${color}55;color:${color};border-radius:4px;font-size:10px;text-transform:uppercase;letter-spacing:.08em;font-weight:700;cursor:pointer">✈ Fly to trail · Replay</button>`
    : "";

  const html = `
    <div style="min-width:270px;font-family:ui-monospace,monospace;color:rgba(255,255,255,.85)">
      <div style="border-bottom:1px solid ${color}44;padding-bottom:8px;margin-bottom:4px">
        <div style="display:flex;justify-content:space-between;align-items:flex-start">
          <div>
            <div style="font-weight:700;font-size:13px;color:${color}">${p.name}</div>
            <div id="pk-meta-country" style="font-size:11px;margin-top:2px;opacity:.85">Loading…</div>
          </div>
          <div style="display:flex;gap:4px;align-items:center;margin-left:8px">
            <div style="font-size:9px;text-transform:uppercase;padding:3px 7px;border-radius:4px;background:${color}18;color:${color};border:1px solid ${color}44;font-weight:700">${p.overPakistan ? "⚑ OVER PK" : p.tiltRange ? "◎ TILT RANGE ~300km" : "✦ IN VIEW"}</div>
            <div style="font-size:9px;text-transform:uppercase;padding:3px 7px;border-radius:4px;background:${ (p as any).sensor_category === "Military" ? "#ef444418" : (p as any).sensor_category === "SAR" ? "#a855f718" : "#22d3ee18"};color:${ (p as any).sensor_category === "Military" ? "#ef4444" : (p as any).sensor_category === "SAR" ? "#a855f7" : "#22d3ee"};border:1px solid ${ (p as any).sensor_category === "Military" ? "#ef444444" : (p as any).sensor_category === "SAR" ? "#a855f744" : "#22d3ee44"};font-weight:700">${ (p as any).sensor_category === "Military" ? "⬛ MILITARY" : (p as any).sensor_category === "SAR" ? "📡 SAR" : "🔭 OPTICAL"}</div>
          </div>
        </div>
      </div>
      <div id="pk-meta-body"></div>
      ${section("Live Position")}
      ${grid(
        row("Latitude", fLat(p.lat)) +
        row("Longitude", fLon(p.lon)) +
        row("Altitude", `${p.altKm.toFixed(1)} km`, true) +
        row("Velocity", `${p.velocityKms.toFixed(3)} km/s`) +
        (hdg !== null ? row("Heading", `${hdg.toFixed(1)}° ${dir(hdg)}`) : "") +
        (period !== null ? row("Orb. Period", `${period.toFixed(1)} min`) : "")
      )}
      ${ (p as any).max_tilt_deg !== undefined && (p as any).max_tilt_deg !== null
        ? section("Imaging Capability") + grid(
            row("Nominal Alt", `${(p as any).altitude_km} km`) +
            row("Max Tilt", `${(p as any).max_tilt_deg}°`, true) +
            row("Standoff", `${(p as any).tilt_standoff_km} km`, true) +
            row("Coverage", `${((p as any).sensor_category === "SAR" || (p as any).sensor_category === "Military" && String((p as any).sensor || "").toLowerCase().includes("sar")) ? "side-looking SAR" : "agile optical"}`, false, true)
          )
        : ""
      }
      ${passHtml}
      ${trailBtn}
    </div>`;

  popup.setContent(html);

  // attach trail button handler after DOM is set
  popup.once("add", () => {
    const btn = document.getElementById("pk-trail-btn");
    if (btn) {
      btn.onclick = (e) => {
        e.stopPropagation();
        const pts: [number, number][] = [...p.trail, [p.lat, p.lon]];
        map.flyToBounds(L.latLngBounds(pts.map(([a, o]) => L.latLng(a, o))),
          { padding: [40, 40], duration: 1.2, easeLinearity: 0.2, maxZoom: 9 });
        onReplayRef.current([...p.trail, [p.lat, p.lon]], color);
      };
    }
  });

  // async load metadata and patch into popup DOM
  if (norad) {
    fetchSatMetadata(norad).then(meta => {
      const countryEl = document.getElementById("pk-meta-country");
      const bodyEl = document.getElementById("pk-meta-body");
      if (countryEl) countryEl.textContent = `${flagEmoji(meta.country)} ${meta.country_name}`;
      if (bodyEl) {
        bodyEl.innerHTML = `
          <div style="font-size:9px;text-transform:uppercase;letter-spacing:.1em;color:${color};border-bottom:1px solid ${color}33;margin-top:4px;margin-bottom:4px;padding-bottom:2px">Satellite Identity</div>
          ${grid(
            row("Country", meta.country_name) +
            row("Operator", meta.operator) +
            row("Purpose", meta.purpose) +
            row("Source", meta.source) +
            row("Destination", meta.destination, true) +
            row("Status", meta.status) +
            ((p as any).sensor_category ? row("Sensor Type", (p as any).sensor_category, (p as any).sensor_category !== "Optical") : "") +
            ((p as any).sensor ? row("Sensor", (p as any).sensor) : "") +
            ((p as any).resolution_m !== undefined ? row("Resolution", `${(p as any).resolution_m} m GSD`, true) : "") +
            (meta.launch_date ? row("Launched", meta.launch_date) : "") +
            (norad ? row("NORAD ID", norad, false, true) : "") +
            row("Data Source", meta.catalog_source, false, true)
          )}
          ${meta.website ? `<a href="${meta.website}" target="_blank" rel="noreferrer" style="font-size:9px;color:${color}bb;display:block;margin-top:2px">${meta.website.replace(/^https?:\/\//, "").slice(0, 45)}</a>` : ""}`;
      }
    }).catch(() => {
      const el = document.getElementById("pk-meta-country");
      if (el) el.textContent = p.category;
    });
  }
}

/* ── trail replay (still React-based, only shown occasionally) ──────────────── */
function TrailReplayLayer({ trail, color, onDone }: {
  trail: [number, number][]; color: string; onDone: () => void;
}) {
  const map = useMap();
  const markerRef = useRef<L.CircleMarker | null>(null);
  const outerRef = useRef<L.CircleMarker | null>(null);
  const raf = useRef<number | null>(null);

  useEffect(() => {
    if (trail.length < 2) { onDone(); return; }
    const inner = L.circleMarker(trail[0], { radius: 4, color, fillColor: color, fillOpacity: 1, weight: 2 }).addTo(map);
    const outer = L.circleMarker(trail[0], { radius: 11, color, fillColor: color, fillOpacity: 0.18, weight: 2 }).addTo(map);
    markerRef.current = inner;
    outerRef.current = outer;

    const start = performance.now();
    const segs = trail.length - 1;
    const tick = (now: number) => {
      const k = Math.min(1, (now - start) / 4000);
      const ease = k < 0.5 ? 4*k*k*k : 1 - Math.pow(-2*k+2,3)/2;
      const f = ease * segs;
      const i = Math.min(segs - 1, Math.floor(f));
      const t = f - i;
      const [a1,o1] = trail[i], [a2,o2] = trail[i+1];
      const pos: [number,number] = [a1+(a2-a1)*t, o1+(o2-o1)*t];
      inner.setLatLng(pos);
      outer.setLatLng(pos);
      if (k < 1) raf.current = requestAnimationFrame(tick); else onDone();
    };
    raf.current = requestAnimationFrame(tick);
    return () => {
      if (raf.current) cancelAnimationFrame(raf.current);
      inner.remove(); outer.remove();
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [trail]);

  return null;
}

/* ── main ───────────────────────────────────────────────────────────────────── */
interface Props {
  positions: SatPosition[];
  selected: string | null;
  onSelect: (name: string | null) => void;
  showOrbits: boolean;
  now: Date;
}

export const SatelliteMap = ({ positions, selected, onSelect, showOrbits, now }: Props) => {
  const selectedSat = useMemo(
    () => positions.find(p => p.name === selected) ?? null,
    [positions, selected],
  );
  const [replay, setReplay] = useState<{ trail: [number,number][]; color: string; key: number } | null>(null);

  return (
    <div className="relative h-full w-full">
    {/* Sensor type legend */}
    <div className="pointer-events-none absolute bottom-8 right-2 z-[500] flex flex-col gap-1 text-[9px] font-mono uppercase tracking-widest">
      {([
        { label: "Optical", color: "#22d3ee", icon: "🔭" },
        { label: "SAR (all-weather)", color: "#a855f7", icon: "📡" },
        { label: "Military", color: "#ef4444", icon: "⬛" },
        { label: "Tilt-range ~300km", color: "#f59e0b", icon: "◎" },
      ] as const).map(({ label, color, icon }) => (
        <div key={label} className="flex items-center gap-1 rounded px-2 py-0.5 backdrop-blur" style={{ background: `${color}18`, border: `1px solid ${color}44`, color }}>
          <span>{icon}</span><span>{label}</span>
        </div>
      ))}
    </div>
    <MapContainer
      center={PK_CENTER}
      zoom={6}
      minZoom={5}
      maxZoom={10}
      maxBounds={PK_BOUNDS}
      maxBoundsViscosity={0.9}
      zoomSnap={0.5}
      zoomDelta={0.5}
      wheelPxPerZoomLevel={80}
      markerZoomAnimation
      zoomAnimation
      fadeAnimation
      className="h-full w-full pk-map"
      style={{ background: "#0a0f1a" }}
    >
      <MapClickHandler onDeselect={() => onSelect(null)} />
      <FlyTo target={selectedSat} />

      <TileLayer
        url="https://{s}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}{r}.png"
        attribution='&copy; <a href="https://carto.com/">CARTO</a>'
        subdomains="abcd" maxZoom={10} keepBuffer={4}
      />
      <TileLayer
        url="https://{s}.basemaps.cartocdn.com/dark_only_labels/{z}/{x}/{y}{r}.png"
        subdomains="abcd" maxZoom={10} pane="shadowPane"
      />

      {/* 300 km tilt-range buffer ring */}
      <Polygon
        positions={TILT_POLY}
        pathOptions={{ color:"#f59e0b", weight:1, opacity:0.5, fillColor:"#f59e0b", fillOpacity:0.03, dashArray:"4 6" }}
      />
      {/* Pakistan border box */}
      <Polygon
        positions={PAKISTAN_POLY}
        pathOptions={{ color:"#22ff88", weight:1.5, opacity:0.8, fillColor:"#22ff88", fillOpacity:0.05, dashArray:"6 4" }}
      />

      {/* orbit ground track — only for selected satellite */}
      {selected && positions.filter(p => p.name === selected).map(p => {
        const color = CATEGORY_META[p.category].color;
        return splitOrbit(p.orbit).map((seg, i) => (
          <Polyline key={`${p.name}-o${i}`} positions={seg}
            pathOptions={{ color, weight: 2, opacity: 0.9 }} />
        ));
      })}

      {/* past trail */}
      {selectedSat && selectedSat.trail.length > 1 && splitOrbit(selectedSat.trail).map((seg, i) => (
        <Polyline key={`trail-${i}`} positions={seg}
          pathOptions={{ color: CATEGORY_META[selectedSat.category].color, weight:2.5, opacity:0.85, dashArray:"3 7", lineCap:"round" }} />
      ))}

      {/* smooth imperative markers — RAF interpolated */}
      <SmoothMarkers
        positions={positions}
        selected={selected}
        onSelect={onSelect}
        now={now}
        onReplay={(trail, color) => setReplay({ trail, color, key: Date.now() })}
      />

      {replay && (
        <TrailReplayLayer key={replay.key} trail={replay.trail} color={replay.color}
          onDone={() => setReplay(null)} />
      )}
    </MapContainer>
    </div>
  );
};
