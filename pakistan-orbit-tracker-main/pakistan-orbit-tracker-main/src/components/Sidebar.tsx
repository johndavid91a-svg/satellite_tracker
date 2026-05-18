import { useMemo, useState } from "react";
import { Activity, Satellite, MapPin, Filter, Radio, Clock, ArrowUp } from "lucide-react";
import { CATEGORY_META, type Category, type SatPosition } from "@/lib/satellites";
import { formatCountdown, formatPassTime } from "@/lib/passes";
import { Switch } from "@/components/ui/switch";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Input } from "@/components/ui/input";

interface Props {
  positions: SatPosition[];
  enabled: Record<Category, boolean>;
  onToggle: (c: Category) => void;
  selected: string | null;
  onSelect: (n: string | null) => void;
  pakistanOnly: boolean;
  onTogglePakistanOnly: (v: boolean) => void;
  showNonImaging: boolean;
  onToggleShowNonImaging: (v: boolean) => void;
  loading: boolean;
  lastUpdate: Date;
  passProgress: { done: number; total: number };
}

export const Sidebar = ({
  positions,
  enabled,
  onToggle,
  selected,
  onSelect,
  pakistanOnly,
  onTogglePakistanOnly,
  showNonImaging,
  onToggleShowNonImaging,
  loading,
  lastUpdate,
  passProgress,
}: Props) => {
  const [query, setQuery] = useState("");
  const [onlyPasses, setOnlyPasses] = useState(false);

  const stats = useMemo(() => {
    const overPk = positions.filter((p) => p.overPakistan).length;
    const withPass = positions.filter((p) => p.nextPass).length;
    return { total: positions.length, overPk, withPass };
  }, [positions]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    let list = positions;
    if (q) list = list.filter((p) => p.name.toLowerCase().includes(q));
    if (onlyPasses) list = list.filter((p) => p.nextPass);
    return [...list].sort((a, b) => {
      // 1. Currently over PK first
      if (a.overPakistan !== b.overPakistan) return a.overPakistan ? -1 : 1;
      // 2. By soonest upcoming pass
      const aT = a.nextPass?.aos.getTime() ?? Infinity;
      const bT = b.nextPass?.aos.getTime() ?? Infinity;
      if (aT !== bT) return aT - bT;
      return a.name.localeCompare(b.name);
    });
  }, [positions, query, onlyPasses]);

  return (
    <aside className="panel flex h-full w-full flex-col overflow-hidden">
      <div className="border-b border-border p-4">
        <div className="flex items-center gap-2">
          <Satellite className="h-5 w-5 text-primary glow-text" />
          <h1 className="text-sm font-bold tracking-widest text-primary glow-text">
            ORBIT-PK
          </h1>
          <span className={`ml-auto h-2 w-2 rounded-full bg-accent ${loading ? "blink" : ""}`} />
        </div>
        <p className="mt-1 text-[10px] uppercase tracking-wider text-muted-foreground">
          Live Satellite Tracking · 🇵🇰
        </p>
      </div>

      <div className="grid grid-cols-3 gap-2 p-3">
        <StatCard icon={<Activity className="h-3 w-3" />} label="Tracked" value={stats.total} accent />
        <StatCard icon={<MapPin className="h-3 w-3" />} label="Over PK" value={stats.overPk} pakistan />
        <StatCard icon={<Clock className="h-3 w-3" />} label="Passes" value={stats.withPass} />
      </div>

      {passProgress.total > 0 && passProgress.done < passProgress.total && (
        <div className="px-3 pb-2">
          <div className="h-1 overflow-hidden rounded bg-secondary">
            <div
              className="h-full bg-gradient-accent transition-all"
              style={{ width: `${(passProgress.done / passProgress.total) * 100}%` }}
            />
          </div>
          <div className="mt-1 text-[9px] uppercase tracking-wider text-muted-foreground">
            Predicting passes… {passProgress.done}/{passProgress.total}
          </div>
        </div>
      )}

      {/* Categories + view-mode toggles. Wrapped in ScrollArea + max-h so the
          full list (14 categories + 3 modifiers) stays reachable on short
          viewports without pushing the satellite list off-screen. */}
      <ScrollArea className="max-h-[55vh] shrink-0 border-t border-border">
        <div className="px-3 py-3">
          <div className="mb-2 flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-muted-foreground">
            <Filter className="h-3 w-3" /> Categories
          </div>
          <div className="space-y-1.5">
            {(Object.keys(CATEGORY_META) as Category[]).map((c) => (
              <label
                key={c}
                className="flex cursor-pointer items-center justify-between rounded border border-transparent bg-secondary/40 px-2 py-1.5 text-xs hover:border-border"
              >
                <span className="flex items-center gap-2">
                  <span
                    className="h-2.5 w-2.5 rounded-full"
                    style={{ background: CATEGORY_META[c].color, boxShadow: `0 0 8px ${CATEGORY_META[c].color}` }}
                  />
                  {CATEGORY_META[c].label}
                </span>
                <Switch checked={enabled[c]} onCheckedChange={() => onToggle(c)} />
              </label>
            ))}
          </div>
          <label className="mt-1.5 flex cursor-pointer items-center justify-between rounded border border-border bg-muted/30 px-2 py-1.5 text-xs">
            <span className="flex items-center gap-2">
              <MapPin className="h-3 w-3 text-accent" /> Pakistan only
            </span>
            <Switch checked={pakistanOnly} onCheckedChange={onTogglePakistanOnly} />
          </label>
          <label className="mt-1.5 flex cursor-pointer items-center justify-between rounded border border-border bg-muted/30 px-2 py-1.5 text-xs">
            <span className="flex items-center gap-2">
              <Radio className="h-3 w-3 text-accent" /> Non-imaging sats (SDA, etc.)
            </span>
            <Switch checked={showNonImaging} onCheckedChange={onToggleShowNonImaging} />
          </label>
          <label className="mt-1.5 flex cursor-pointer items-center justify-between rounded border border-border bg-muted/30 px-2 py-1.5 text-xs">
            <span className="flex items-center gap-2">
              <Clock className="h-3 w-3 text-accent" /> Only with upcoming pass
            </span>
            <Switch checked={onlyPasses} onCheckedChange={setOnlyPasses} />
          </label>
        </div>
      </ScrollArea>

      <div className="flex min-h-0 flex-1 flex-col border-t border-border">
        <div className="p-3 pb-2">
          <Input
            placeholder="Search satellite…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="h-8 bg-secondary/50 text-xs"
          />
        </div>
        <ScrollArea className="flex-1 px-2 pb-2">
          <ul className="space-y-1">
            {filtered.map((p) => {
              const pass = p.nextPass;
              const isSel = selected === p.name;
              return (
                <li key={p.name}>
                  <button
                    onClick={() => onSelect(isSel ? null : p.name)}
                    className={`group flex w-full flex-col gap-1 rounded px-2 py-1.5 text-left text-xs transition ${
                      isSel ? "bg-primary/15 text-primary shadow-glow" : "hover:bg-secondary/60"
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <span
                        className="h-1.5 w-1.5 shrink-0 rounded-full"
                        style={{ background: CATEGORY_META[p.category].color }}
                      />
                      <span className="flex-1 truncate font-mono">{p.name}</span>
                      {p.overPakistan && (
                        <span className="rounded bg-accent/20 px-1 text-[9px] font-bold text-accent">PK</span>
                      )}
                    </div>
                    {pass && (
                      <div className="flex items-center gap-2 pl-3.5 text-[9px] uppercase tracking-wider text-muted-foreground">
                        <Clock className="h-2.5 w-2.5" />
                        <span className="text-foreground/80">
                          {formatCountdown(pass.aos, lastUpdate)}
                        </span>
                        <span>·</span>
                        <ArrowUp className="h-2.5 w-2.5" />
                        <span className="text-accent">{pass.maxElDeg.toFixed(0)}°</span>
                        <span className="ml-auto">{formatPassTime(pass.aos)}</span>
                      </div>
                    )}
                  </button>
                </li>
              );
            })}
            {filtered.length === 0 && (
              <li className="px-2 py-4 text-center text-xs text-muted-foreground">
                {loading ? "Loading TLE data…" : "No satellites"}
              </li>
            )}
          </ul>
        </ScrollArea>
      </div>

      <div className="border-t border-border p-2 text-center text-[9px] uppercase tracking-wider text-muted-foreground">
        SGP4 · UTC {lastUpdate.toISOString().slice(11, 19)} · CelesTrak
      </div>
    </aside>
  );
};

function StatCard({
  icon,
  label,
  value,
  accent,
  pakistan,
}: {
  icon: React.ReactNode;
  label: string;
  value: number;
  accent?: boolean;
  pakistan?: boolean;
}) {
  const color = pakistan ? "text-accent" : accent ? "text-primary" : "text-foreground";
  return (
    <div className="rounded border border-border bg-secondary/40 px-2 py-1.5">
      <div className="flex items-center gap-1 text-[9px] uppercase tracking-wider text-muted-foreground">
        {icon} {label}
      </div>
      <div className={`mt-0.5 font-mono text-lg font-bold ${color} glow-text`}>{value}</div>
    </div>
  );
}
