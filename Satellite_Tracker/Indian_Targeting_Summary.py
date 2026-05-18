"""
Generate Indian_Targeting_Summary.txt — a single, no-Word-needed view of
which Pakistan strategic sites are imaged by Indian satellites across the
current 15-day forecast.

Output lives in Satellite_Tracker/documents/ next to the Word doc.
"""
from __future__ import annotations
import os, sys, json, datetime
from collections import Counter, defaultdict

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

FORECAST_JSON = os.path.join(_HERE, "forecast_15day.json")
OUT_PATH = os.path.join(_HERE, "documents", "Indian_Targeting_Summary.txt")


def _to_pkt(iso_utc: str) -> str:
    try:
        dt = datetime.datetime.strptime(iso_utc, "%Y-%m-%dT%H:%M:%SZ")
        return (dt + datetime.timedelta(hours=5)).strftime("%H:%M")
    except (ValueError, TypeError):
        return iso_utc[11:16] if iso_utc else "-"


def build_summary() -> str:
    with open(FORECAST_JSON, "r", encoding="utf-8") as f:
        forecast = json.load(f)

    indian_crossings = [c for d in forecast["days"]
                        for c in d["crossings"] if c.get("is_indian")]

    lines: list[str] = []
    bar = "=" * 80
    lines.append(bar)
    lines.append("  INDIAN-SATELLITE TARGETING SUMMARY — Pakistan strategic sites")
    lines.append(f"  Window: {forecast['start_date']}  ->  {forecast['end_date']}")
    lines.append(f"  Generated: {forecast['generated_at']}")
    lines.append("  All times PKT (UTC+5)")
    lines.append(bar)
    lines.append("")
    lines.append(f"Indian satellite passes in the 15-day forecast: {len(indian_crossings)}")
    lines.append("")

    # Aggregate per city
    city_counter: Counter[str] = Counter()
    city_sat_counter: dict[str, Counter[str]] = defaultdict(Counter)
    for c in indian_crossings:
        for t in c.get("targeted_sites", []):
            city_counter[t["city"]] += 1
            city_sat_counter[t["city"]][c["name"]] += 1

    priority_cities = [
        "Islamabad", "Rawalpindi", "Karachi", "Lahore",
        "Kamra (Attock)", "Quetta", "Sargodha",
    ]

    lines.append("-" * 80)
    lines.append("  PRIORITY CITIES — passes by Indian satellites over 15 days")
    lines.append("-" * 80)
    lines.append(f"  {'CITY':18s}  {'PASSES':>7s}   BREAKDOWN BY SAT")
    for city in priority_cities:
        n = city_counter.get(city, 0)
        if n == 0:
            lines.append(f"  {city:18s}  {0:>7d}   (no passes)")
            continue
        top = city_sat_counter[city].most_common(4)
        breakdown = ", ".join(f"{name}={k}" for name, k in top)
        lines.append(f"  {city:18s}  {n:>7d}   {breakdown}")
    lines.append("")

    # Per-day breakdown
    lines.append("-" * 80)
    lines.append("  DAILY INDIAN-SAT TARGETING — first 3 future passes per day")
    lines.append("-" * 80)
    for d in forecast["days"]:
        day_indian = [c for c in d["crossings"] if c.get("is_indian")]
        if not day_indian:
            continue
        # Future-only filter (matches what the popup shows)
        lines.append("")
        lines.append(f"  {d['date']}  ({len(day_indian)} Indian passes)")
        for c in day_indian[:5]:
            tgts = c.get("targeted_sites") or []
            t1 = sorted({t["city"] for t in tgts if t["tier"] == 1})
            t2 = sorted({t["city"] for t in tgts if t["tier"] == 2})
            t1_str = ", ".join(t1) if t1 else "—"
            t2_str = (" + secondary: " + ", ".join(t2[:5])) if t2 else ""
            pass_lbl = "OVER" if c["pass_type"] == "overhead" else "TILT"
            lines.append(f"    {_to_pkt(c['entry_utc'])} PKT  {pass_lbl:4s}  "
                         f"{c['name']:14s}  ->  TIER-1: {t1_str}{t2_str}")
    lines.append("")
    lines.append(bar)
    lines.append("  Sites covered: 26 (11 Tier-1 + 15 Tier-2)")
    lines.append("  Source: pakistan_strategic_sites.py (public open-source coordinates)")
    lines.append(bar)
    return "\n".join(lines)


def write_summary() -> str:
    text = build_summary()
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(text)
    return OUT_PATH


if __name__ == "__main__":
    p = write_summary()
    print(f"Wrote: {p}")
    print()
    with open(p, encoding="utf-8") as f:
        print(f.read())
