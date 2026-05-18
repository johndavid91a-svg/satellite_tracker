import * as satellite from "satellite.js";

// Default observer over Pakistan: Islamabad
export const PK_OBSERVER = {
  name: "Islamabad",
  latDeg: 33.6844,
  lonDeg: 73.0479,
  heightKm: 0.54,
};

const observerGd = {
  latitude: satellite.degreesToRadians(PK_OBSERVER.latDeg),
  longitude: satellite.degreesToRadians(PK_OBSERVER.lonDeg),
  height: PK_OBSERVER.heightKm,
};

export interface PassInfo {
  aos: Date;          // Acquisition of Signal (rise above horizon)
  los: Date;          // Loss of Signal (set below horizon)
  maxElDeg: number;   // Max elevation during pass
  maxElTime: Date;
  durationSec: number;
}

const RAD2DEG = 180 / Math.PI;

function lookAngles(satrec: satellite.SatRec, date: Date) {
  const pv = satellite.propagate(satrec, date);
  if (!pv.position || typeof pv.position === "boolean") return null;
  const gmst = satellite.gstime(date);
  const ecf = satellite.eciToEcf(pv.position as satellite.EciVec3<number>, gmst);
  const look = satellite.ecfToLookAngles(observerGd, ecf);
  return {
    elevationDeg: look.elevation * RAD2DEG,
    azimuthDeg: look.azimuth * RAD2DEG,
    rangeKm: look.rangeSat,
  };
}

/**
 * Predict the next pass over the Pakistan observer within `horizonHours`.
 * Coarse scan at 30s steps; refines AOS/LOS to ~1s via bisection.
 * Returns null if no pass is found.
 */
export function predictNextPass(
  satrec: satellite.SatRec,
  fromDate: Date,
  horizonHours = 24,
  minMaxElDeg = 5,
): PassInfo | null {
  const stepSec = 30;
  const totalSteps = Math.floor((horizonHours * 3600) / stepSec);
  let prevEl: number | null = null;
  let prevTime = fromDate;

  for (let i = 0; i <= totalSteps; i++) {
    const t = new Date(fromDate.getTime() + i * stepSec * 1000);
    const la = lookAngles(satrec, t);
    if (!la) {
      prevEl = null;
      prevTime = t;
      continue;
    }
    const el = la.elevationDeg;

    if (prevEl !== null && prevEl < 0 && el >= 0) {
      // Rising: refine AOS by bisection between prevTime and t
      const aos = bisectHorizon(satrec, prevTime, t, true);
      // Walk forward to find LOS
      let maxEl = el;
      let maxElTime = t;
      let setPrevEl = el;
      let setPrevTime = t;
      for (let j = i + 1; j <= totalSteps; j++) {
        const tj = new Date(fromDate.getTime() + j * stepSec * 1000);
        const laj = lookAngles(satrec, tj);
        if (!laj) break;
        if (laj.elevationDeg > maxEl) {
          maxEl = laj.elevationDeg;
          maxElTime = tj;
        }
        if (laj.elevationDeg < 0 && setPrevEl >= 0) {
          const los = bisectHorizon(satrec, setPrevTime, tj, false);
          if (maxEl < minMaxElDeg) {
            // skip low-quality pass, continue search after LOS
            return predictNextPass(satrec, los, horizonHours - (los.getTime() - fromDate.getTime()) / 3600000, minMaxElDeg);
          }
          // Refine max elevation around maxElTime
          const refinedMax = refineMaxEl(satrec, new Date(maxElTime.getTime() - stepSec * 1000), new Date(maxElTime.getTime() + stepSec * 1000));
          return {
            aos,
            los,
            maxElDeg: refinedMax.elDeg,
            maxElTime: refinedMax.time,
            durationSec: Math.round((los.getTime() - aos.getTime()) / 1000),
          };
        }
        setPrevEl = laj.elevationDeg;
        setPrevTime = tj;
      }
      return null; // pass didn't end within horizon
    }

    prevEl = el;
    prevTime = t;
  }
  return null;
}

function bisectHorizon(satrec: satellite.SatRec, t0: Date, t1: Date, rising: boolean): Date {
  let lo = t0.getTime();
  let hi = t1.getTime();
  for (let i = 0; i < 16; i++) {
    const mid = (lo + hi) / 2;
    const la = lookAngles(satrec, new Date(mid));
    if (!la) return new Date(mid);
    const above = la.elevationDeg >= 0;
    if (rising) {
      if (above) hi = mid;
      else lo = mid;
    } else {
      if (above) lo = mid;
      else hi = mid;
    }
  }
  return new Date((lo + hi) / 2);
}

function refineMaxEl(satrec: satellite.SatRec, t0: Date, t1: Date) {
  // Golden-section-ish: sample 10 points between t0 and t1
  let bestEl = -90;
  let bestTime = t0;
  const steps = 30;
  for (let i = 0; i <= steps; i++) {
    const t = new Date(t0.getTime() + ((t1.getTime() - t0.getTime()) * i) / steps);
    const la = lookAngles(satrec, t);
    if (la && la.elevationDeg > bestEl) {
      bestEl = la.elevationDeg;
      bestTime = t;
    }
  }
  return { elDeg: bestEl, time: bestTime };
}

export function formatPassTime(d: Date): string {
  // Display in PKT (UTC+5)
  const pkt = new Date(d.getTime() + 5 * 3600 * 1000);
  const hh = String(pkt.getUTCHours()).padStart(2, "0");
  const mm = String(pkt.getUTCMinutes()).padStart(2, "0");
  return `${hh}:${mm} PKT`;
}

export function formatCountdown(target: Date, from: Date): string {
  const diff = Math.max(0, Math.round((target.getTime() - from.getTime()) / 1000));
  const h = Math.floor(diff / 3600);
  const m = Math.floor((diff % 3600) / 60);
  const s = diff % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}
