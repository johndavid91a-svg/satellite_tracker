import tkinter as tk
from tkinter import ttk
import subprocess, threading, os, sys, glob, re, webbrowser, logging, traceback, math, random, atexit
from datetime import datetime

# When launched via pythonw.exe (no console), sys.stdout/stderr can be None
# or write-fail. Any print() with a non-cp1252 character would silently
# crash the entire process. Redirect both to a UTF-8 log file so prints
# are safe and we keep a paper trail.
_log_handle = None
if sys.stdout is None or sys.stderr is None or sys.executable.endswith("pythonw.exe"):
    _log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "space_tracker_app.log")
    try:
        _log_handle = open(_log_path, "a", encoding="utf-8", buffering=1)
        sys.stdout = _log_handle
        sys.stderr = _log_handle
    except OSError:
        # Last resort: discard
        _log_handle = open(os.devnull, "w", encoding="utf-8")
        sys.stdout = _log_handle
        sys.stderr = _log_handle

# Release the log file handle on exit so the file isn't held open after the
# process leaves (lets log rotation / cleanup work, avoids stale locks).
@atexit.register
def _close_log_handle():
    h = _log_handle
    if h is not None:
        try:
            h.flush()
            h.close()
        except Exception:
            pass

# ── Path constants ─────────────────────────────────────────────────────────────
BASE_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAT_DIR   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Satellite_Tracker")
LAUNCH_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Rocket_Launches")
ORBIT_DIR  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pakistan-orbit-tracker-main", "pakistan-orbit-tracker-main")

# Crash logger
logging.basicConfig(
    filename=os.path.join(BASE_DIR, "space_tracker_crash.log"),
    level=logging.WARNING,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
def _log_exc(where):
    logging.error("%s\n%s", where, traceback.format_exc())

# ── Orbital telemetry palette — deep space + signal colors ────────────────────
BG        = "#03060f"   # deep space
BG2       = "#070d1e"
BG3       = "#0d1832"
PANEL     = "#0a1224"   # navy panel
PANEL2    = "#0f1a30"
BORDER    = "#1a2b4d"
CYAN      = "#00d4ff"   # telemetry cyan (primary)
GREEN     = "#00ff9d"   # signal-lock green
RED       = "#ff3a5e"   # anomaly red
YELLOW    = "#ffb938"   # orbital amber
AMBER     = "#ff8a1f"   # NASA orange
ACCENT    = "#3b82f6"   # orbital blue
ACCENT2   = "#7c3aed"   # violet trail
NEON      = "#5eead4"   # mint signal
MAGENTA   = "#e879f9"   # comms violet
TEXT      = "#e0f0ff"   # off-white with blue tint
TEXT_DIM  = "#7e9ab8"   # slate-blue
TEXT_MUTE = "#3d4f6e"   # deep slate
GLOW      = "#1e3a8a"   # accent glow

def dim(hex_color, factor=0.4):
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    r, g, b = int(r * factor), int(g * factor), int(b * factor)
    return f"#{r:02x}{g:02x}{b:02x}"

def _hhmm_frac(iso: str) -> float:
    """Return fraction-of-day (0–1) from an ISO timestamp string, offset to PKT (UTC+5)."""
    try:
        t = iso[11:19]   # HH:MM:SS in UTC
        h, m, s = int(t[0:2]), int(t[3:5]), int(t[6:8])
        total_sec = (h * 3600 + m * 60 + s) + 5 * 3600   # +5h for PKT
        return (total_sec % 86400) / 86400.0
    except Exception:
        return 0.0


def _utc_to_pkt(iso: str) -> str:
    """Convert ISO UTC timestamp HH:MM:SS to PKT (UTC+5) HH:MM:SS string."""
    try:
        h, m, s = int(iso[11:13]), int(iso[14:16]), int(iso[17:19])
        total = h * 3600 + m * 60 + s + 5 * 3600
        h2 = (total // 3600) % 24
        m2 = (total % 3600) // 60
        s2 = total % 60
        return f"{h2:02d}:{m2:02d}:{s2:02d}"
    except Exception:
        return iso[11:19] if len(iso) >= 19 else iso

FONT_HEAD = ("Segoe UI", 10, "bold")
FONT_MONO = ("Consolas", 9)
FONT_BIG  = ("Segoe UI", 22, "bold")
FONT_SM   = ("Segoe UI", 8)
FONT_MED  = ("Segoe UI", 10)

ENV = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}


# ── Flat styled button (identical to main app.py) ──────────────────────────────
class FlatBtn(tk.Label):
    def __init__(self, parent, text, cmd, bg=PANEL, fg=TEXT_DIM,
                 hover_bg=None, hover_fg=CYAN, font=FONT_HEAD,
                 padx=14, pady=6, **kw):
        super().__init__(parent, text=text, bg=bg, fg=fg, font=font,
                         padx=padx, pady=pady, cursor="hand2", **kw)
        self._cmd = cmd
        self._bg = bg;  self._fg = fg
        self._hbg = hover_bg or BG3;  self._hfg = hover_fg
        self._disabled = False
        self.bind("<Enter>",    self._on_enter)
        self.bind("<Leave>",    self._on_leave)
        self.bind("<Button-1>", self._on_click)

    def _on_enter(self, _):
        if not self._disabled:
            self.config(bg=self._hbg, fg=self._hfg)

    def _on_leave(self, _):
        if not self._disabled:
            self.config(bg=self._bg, fg=self._fg)

    def _on_click(self, _):
        if not self._disabled and self._cmd:
            self._cmd()

    def set_disabled(self, v):
        self._disabled = v
        self.config(fg=TEXT_MUTE if v else self._fg,
                    cursor="arrow" if v else "hand2")


# ── Satellite Tracker Panel ────────────────────────────────────────────────────
class SatellitePanel(tk.Frame):
    """Runs Satellite_Tracker/satellite_tracker_v2.py and shows live output."""

    SUBTITLE = "Pakistan Border Surveillance · Anomaly Detection · 60+ Tracked Satellites"

    def __init__(self, parent, **kw):
        super().__init__(parent, bg=BG, **kw)
        self._proc      = None
        self._running   = False
        self._seconds   = 0
        self._timer_id  = None
        self._lines     = 0
        self._crossings = 0
        self._sats      = 0
        self._anomalies = 0
        self._tracked   = 0
        self._row_alt   = False
        self._pulse_id  = None
        self._pulse_color = None
        self._pulse_on  = False
        self.docs_dir   = os.path.join(SAT_DIR, "documents")
        self.script     = os.path.join(SAT_DIR, "satellite_tracker_v2.py")
        self._build()

    # ── Build UI ───────────────────────────────────────────────────────────────
    def _build(self):
        # Header bar
        hdr = tk.Frame(self, bg=PANEL, pady=14)
        hdr.pack(fill="x", padx=0, pady=(0, 10))

        tk.Label(hdr, text="🛰️  Satellite Tracker",
                 font=("Segoe UI", 16, "bold"), bg=PANEL, fg=TEXT
                 ).pack(side="left", padx=20)

        right = tk.Frame(hdr, bg=PANEL)
        right.pack(side="right", padx=20)
        self._status_dot = tk.Label(right, text="●", font=("Segoe UI", 12),
                                    bg=PANEL, fg=TEXT_MUTE)
        self._status_dot.pack(side="left")
        self._status_lbl = tk.Label(right, text="IDLE", font=FONT_MONO,
                                    bg=PANEL, fg=TEXT_MUTE)
        self._status_lbl.pack(side="left", padx=(4, 16))
        self._timer_lbl = tk.Label(right, text="00:00",
                                   font=("Consolas", 18), bg=PANEL, fg=CYAN)
        self._timer_lbl.pack(side="left")

        # Subtitle
        tk.Label(self, text=self.SUBTITLE,
                 font=FONT_SM, bg=BG, fg=TEXT_DIM
                 ).pack(anchor="w", padx=20, pady=(0, 8))

        # Stats row
        stats_row = tk.Frame(self, bg=BG)
        stats_row.pack(fill="x", padx=20, pady=(0, 8))
        self._stat_crossings = self._stat_card(stats_row, "CROSSINGS",  CYAN)
        self._stat_sats      = self._stat_card(stats_row, "SATELLITES", GREEN)
        self._stat_anomalies = self._stat_card(stats_row, "ANOMALIES",  RED)
        self._stat_tracked   = self._stat_card(stats_row, "TRACKED",    YELLOW)

        # Progress bar
        prog_frame = tk.Frame(self, bg=BG, height=4)
        prog_frame.pack(fill="x", padx=20, pady=(0, 8))
        prog_frame.pack_propagate(False)
        self._prog_canvas = tk.Canvas(prog_frame, bg=BG3, height=4,
                                      highlightthickness=0, bd=0)
        self._prog_canvas.pack(fill="both", expand=True)
        self._prog_bar = self._prog_canvas.create_rectangle(
            0, 0, 0, 4, fill=CYAN, outline="")
        self._prog_canvas.bind("<Configure>",
                               lambda e: self._update_progress(0))

        # Action bar
        act = tk.Frame(self, bg=BG)
        act.pack(fill="x", padx=20, pady=(0, 8))

        self._btn_run = FlatBtn(act, "▶  SCAN YESTERDAY", self._run,
                                bg=BG3, fg=CYAN, hover_bg=CYAN, hover_fg=BG)
        self._btn_run.pack(side="left", padx=(0, 6))

        self._btn_stop = FlatBtn(act, "■  STOP", self._stop,
                                 bg=BG3, fg=RED, hover_bg=RED, hover_fg="#fff")
        self._btn_stop.set_disabled(True)
        self._btn_stop.pack(side="left", padx=(0, 6))

        FlatBtn(act, "[>] LATEST REPORT", self._open_report,
                bg=BG3, fg=TEXT, hover_fg=CYAN).pack(side="left", padx=(0, 6))

        FlatBtn(act, "[F] DOCUMENTS", self._open_folder,
                bg=BG3, fg=TEXT_DIM, hover_fg=CYAN).pack(side="left", padx=(0, 6))

        FlatBtn(act, "🗺  LAUNCH LIVE MAP", self._open_live_map,
                bg="#1a0f35", fg=ACCENT2, hover_bg=ACCENT2, hover_fg=BG
                ).pack(side="left", padx=(0, 6))

        FlatBtn(act, "[X] CLEAR", self._clear_log,
                bg=BG3, fg=TEXT_MUTE, hover_fg=RED).pack(side="right")

        # Log area
        log_frame = tk.Frame(self, bg=BG)
        log_frame.pack(fill="both", expand=True, padx=20, pady=(0, 16))

        log_hdr = tk.Frame(log_frame, bg=PANEL, pady=6)
        log_hdr.pack(fill="x")
        tk.Label(log_hdr, text=">> LIVE TELEMETRY", font=FONT_MONO,
                 bg=PANEL, fg=CYAN).pack(side="left", padx=12)
        self._log_count = tk.Label(log_hdr, text="0 lines", font=FONT_MONO,
                                   bg=PANEL, fg=TEXT_MUTE)
        self._log_count.pack(side="right", padx=12)

        txt_frame = tk.Frame(log_frame, bg=BG2)
        txt_frame.pack(fill="both", expand=True)

        self._log = tk.Text(txt_frame, bg=BG, fg=TEXT_DIM,
                            font=FONT_MONO, relief="flat", bd=0,
                            insertbackground=TEXT, state="disabled",
                            wrap="word", padx=12, pady=8)
        sb = tk.Scrollbar(txt_frame, command=self._log.yview,
                          bg=BG3, troughcolor=BG, width=6)
        self._log.config(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._log.pack(fill="both", expand=True)

        # Text tags
        self._log.tag_config("match",   foreground=GREEN)
        self._log.tag_config("error",   foreground=RED)
        self._log.tag_config("info",    foreground=CYAN)
        self._log.tag_config("warn",    foreground=YELLOW)
        self._log.tag_config("done",    foreground=NEON)
        self._log.tag_config("default", foreground=TEXT_DIM)
        self._log.tag_config("row_a",   background="#03060f")
        self._log.tag_config("row_b",   background="#070d1e")
        self._log.tag_config("ts",      foreground=TEXT_MUTE)

    def _stat_card(self, parent, label, color):
        outer = tk.Frame(parent, bg=color)
        outer.pack(side="left", padx=(0, 8), fill="x", expand=True)
        tk.Frame(outer, bg=color, height=2).pack(fill="x")
        f = tk.Frame(outer, bg=PANEL, padx=16, pady=12)
        f.pack(fill="both", expand=True)
        val = tk.Label(f, text="0", font=("Segoe UI", 28, "bold"),
                       bg=PANEL, fg=color)
        val.pack(anchor="w")
        tk.Label(f, text=label, font=("Consolas", 8, "bold"),
                 bg=PANEL, fg=TEXT_DIM).pack(anchor="w", pady=(2, 0))
        bar_bg = tk.Frame(f, bg=BG3, height=3)
        bar_bg.pack(fill="x", pady=(8, 0))
        bar_fill = tk.Frame(bar_bg, bg=color, height=3, width=0)
        bar_fill.place(x=0, y=0, relheight=1)
        return val, bar_fill

    # ── Actions ────────────────────────────────────────────────────────────────
    def _run(self):
        if self._running:
            return
        self._running   = True
        self._seconds   = 0
        self._crossings = 0
        self._sats      = 0
        self._anomalies = 0
        self._tracked   = 0
        self._set_status("SCANNING", CYAN)
        self._start_pulse(CYAN)
        self._btn_run.set_disabled(True)
        self._btn_stop.set_disabled(False)
        self._update_stat(self._stat_crossings, 0)
        self._update_stat(self._stat_sats,      0)
        self._update_stat(self._stat_anomalies, 0)
        self._update_stat(self._stat_tracked,   0)
        self._update_progress(0)
        self._append(
            f"[{datetime.now().strftime('%H:%M:%S')}] Starting satellite scan...\n",
            "info"
        )
        self._tick()
        threading.Thread(target=self._worker, daemon=True).start()

    def _stop(self):
        if self._proc:
            try:
                self._proc.terminate()
            except Exception:
                pass
        self._finish("STOPPED", RED)

    def _worker(self):
        try:
            self._proc = subprocess.Popen(
                [sys.executable, "-u", self.script],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                cwd=SAT_DIR, bufsize=1, env=ENV
            )
            for line in self._proc.stdout:
                self._handle_line(line.rstrip("\n"))
            self._proc.wait()
            rc = self._proc.returncode
            if rc == 0:
                self.after(0, lambda: self._finish("COMPLETE", GREEN))
            else:
                self.after(0, lambda: self._finish(f"EXIT {rc}", RED))
        except Exception as e:
            self.after(0, lambda: self._finish(f"ERROR: {e}", RED))

    def _handle_line(self, line):
        if not line.strip():
            return
        tag = "default"

        if "Total crossings:" in line or "border crossings" in line.lower():
            tag = "match"
            m = re.search(r"(\d+)", line)
            if m:
                self._crossings = int(m.group(1))
                self.after(0, lambda v=self._crossings:
                           self._update_stat(self._stat_crossings, v))
        elif "Unique satellites:" in line:
            tag = "info"
            m = re.search(r"(\d+)", line)
            if m:
                self._sats = int(m.group(1))
                self.after(0, lambda v=self._sats:
                           self._update_stat(self._stat_sats, v))
        elif "Anomalies:" in line or "ANOMALIES DETECTED" in line:
            tag = "error"
            m = re.search(r"(\d+)", line)
            if m:
                self._anomalies = int(m.group(1))
                self.after(0, lambda v=self._anomalies:
                           self._update_stat(self._stat_anomalies, v))
        elif "Loaded" in line and "satellites" in line:
            m = re.search(r"(\d+)", line)
            if m:
                self._tracked = int(m.group(1))
                self.after(0, lambda v=self._tracked:
                           self._update_stat(self._stat_tracked, v))
        elif "[HIGH]" in line or "[MEDIUM]" in line:
            tag = "error"
        elif "[+]" in line:
            tag = "match"
        elif "[*]" in line:
            tag = "info"
        elif "[!]" in line:
            tag = "warn"
        elif "Report:" in line or "Report saved" in line:
            tag = "done"

        pct = re.search(r"\]\s+(\d+)%", line)
        if pct:
            self.after(0, lambda v=int(pct.group(1)):
                       self._update_progress(v))

        self.after(0, lambda l=line, t=tag: self._append(l + "\n", t))

    def _finish(self, msg, color):
        self._running = False
        if self._timer_id:
            self.after_cancel(self._timer_id)
            self._timer_id = None
        self._set_status(msg, color)
        self._btn_run.set_disabled(False)
        self._btn_stop.set_disabled(True)
        self._update_progress(100)
        self._append(f"\n-- {msg} --\n", "warn")

    def _tick(self):
        if not self._running:
            return
        self._seconds += 1
        m = self._seconds // 60
        s = self._seconds % 60
        self._timer_lbl.config(text=f"{m:02d}:{s:02d}")
        self._timer_id = self.after(1000, self._tick)

    def _set_status(self, text, color):
        self._stop_pulse()
        self._status_dot.config(fg=color)
        self._status_lbl.config(text=text, fg=color)

    def _start_pulse(self, color):
        self._pulse_color = color
        self._pulse_on    = True
        self._pulse_tick()

    def _stop_pulse(self):
        if self._pulse_id:
            try: self.after_cancel(self._pulse_id)
            except Exception: pass
            self._pulse_id = None
        self._pulse_color = None

    def _pulse_tick(self):
        if not self._pulse_color:
            return
        c = self._pulse_color if self._pulse_on else dim(self._pulse_color, 0.35)
        try:
            self._status_dot.config(fg=c)
        except Exception:
            return
        self._pulse_on = not self._pulse_on
        self._pulse_id = self.after(550, self._pulse_tick)

    def _update_stat(self, stat_tuple, value):
        val_lbl, bar_fill = stat_tuple
        val_lbl.config(text=str(value))
        parent_w = bar_fill.master.winfo_width()
        if parent_w > 1:
            pct = min(1.0, value / 50)
            bar_fill.place(x=0, y=0, relheight=1, width=int(parent_w * pct))

    def _update_progress(self, pct):
        w = self._prog_canvas.winfo_width()
        if w > 1:
            self._prog_canvas.coords(
                self._prog_bar, 0, 0, int(w * pct / 100), 4)

    def _append(self, text, tag="default"):
        self._log.config(state="normal")
        row_tag = "row_b" if self._row_alt else "row_a"
        self._row_alt = not self._row_alt
        ts = datetime.now().strftime("%H:%M:%S  ")
        self._log.insert("end", ts,   ("ts",  row_tag))
        self._log.insert("end", text, (tag,   row_tag))
        self._log.see("end")
        self._log.config(state="disabled")
        self._lines += 1
        self._log_count.config(text=f"{self._lines} lines")

    def _clear_log(self):
        self._log.config(state="normal")
        self._log.delete("1.0", "end")
        self._log.config(state="disabled")
        self._lines = 0
        self._log_count.config(text="0 lines")

    def _open_report(self):
        docs = sorted(
            glob.glob(os.path.join(self.docs_dir, "*.docx")), reverse=True)
        if docs:
            os.startfile(docs[0])
        else:
            self._append("[!] No reports found — run a scan first.\n", "warn")

    def _open_folder(self):
        os.makedirs(self.docs_dir, exist_ok=True)
        os.startfile(self.docs_dir)

    def _open_live_map(self):
        """Start the satellite API server (if needed) then open live_map.html."""
        api_script = os.path.join(SAT_DIR, "sat_live_api.py")
        map_html   = os.path.join(SAT_DIR, "live_map.html")

        if not os.path.exists(map_html):
            self._append("[MAP] live_map.html not found.\n", "error")
            return

        # Try to reach the API; start it if not running
        try:
            import urllib.request
            urllib.request.urlopen("http://127.0.0.1:5123/positions", timeout=1)
            self._append("[MAP] Satellite API already running.\n", "info")
        except Exception:
            if os.path.exists(api_script):
                # Route stdout+stderr to a dedicated log so backend crashes
                # are visible after the fact instead of vanishing into the void.
                api_log = os.path.join(SAT_DIR, "sat_live_api.log")
                try:
                    api_log_h = open(api_log, "a", encoding="utf-8", buffering=1)
                except OSError:
                    api_log_h = subprocess.DEVNULL
                subprocess.Popen(
                    [sys.executable, api_script],
                    cwd=SAT_DIR, env=ENV,
                    stdout=api_log_h, stderr=subprocess.STDOUT,
                )
                self._append("[MAP] Starting satellite API server...\n", "info")
                import time; time.sleep(2)
            else:
                self._append("[MAP] sat_live_api.py not found — opening map anyway.\n", "warn")

        webbrowser.open(f"file:///{map_html.replace(os.sep, '/')}")
        self._append("[MAP] Live map opened in browser.\n", "done")

    def stop_process(self):
        if self._proc:
            try:
                self._proc.terminate()
            except Exception:
                pass


# ── Rocket Launches Panel ──────────────────────────────────────────────────────
class RocketLaunchPanel(tk.Frame):
    """Runs Rocket_Launches/launch_tracker.py and shows live output."""

    SUBTITLE = ("Upcoming & recent launches worldwide · All countries · "
                "SpaceX · China · Russia · India · Europe")
    ORANGE   = "#f97316"

    def __init__(self, parent, **kw):
        super().__init__(parent, bg=BG, **kw)
        self._proc     = None
        self._running  = False
        self._seconds  = 0
        self._timer_id = None
        self._lines    = 0
        self._upcoming = 0
        self._recent   = 0
        self._go       = 0
        self._errors   = 0
        self._row_alt  = False
        self._pulse_id = None
        self._pulse_color = None
        self._pulse_on = False
        self.docs_dir  = os.path.join(LAUNCH_DIR, "documents")
        self.script    = os.path.join(LAUNCH_DIR, "launch_tracker.py")
        self._build()

    # ── Build UI ───────────────────────────────────────────────────────────────
    def _build(self):
        # Header bar
        hdr = tk.Frame(self, bg=PANEL, pady=14)
        hdr.pack(fill="x", padx=0, pady=(0, 10))

        tk.Label(hdr, text="🚀  Global Rocket Launch Tracker",
                 font=("Segoe UI", 16, "bold"), bg=PANEL, fg=TEXT
                 ).pack(side="left", padx=20)

        right = tk.Frame(hdr, bg=PANEL)
        right.pack(side="right", padx=20)
        self._status_dot = tk.Label(right, text="●", font=("Segoe UI", 12),
                                    bg=PANEL, fg=TEXT_MUTE)
        self._status_dot.pack(side="left")
        self._status_lbl = tk.Label(right, text="IDLE", font=FONT_MONO,
                                    bg=PANEL, fg=TEXT_MUTE)
        self._status_lbl.pack(side="left", padx=(4, 16))
        self._timer_lbl = tk.Label(right, text="00:00",
                                   font=("Consolas", 18), bg=PANEL,
                                   fg=self.ORANGE)
        self._timer_lbl.pack(side="left")

        # Subtitle
        tk.Label(self, text=self.SUBTITLE,
                 font=FONT_SM, bg=BG, fg=TEXT_DIM
                 ).pack(anchor="w", padx=20, pady=(0, 8))

        # Stats row
        stats_row = tk.Frame(self, bg=BG)
        stats_row.pack(fill="x", padx=20, pady=(0, 8))
        self._stat_upcoming = self._stat_card(stats_row, "UPCOMING",   "#60a5fa")
        self._stat_recent   = self._stat_card(stats_row, "RECENT",     GREEN)
        self._stat_go       = self._stat_card(stats_row, "STATUS: GO", self.ORANGE)
        self._stat_errors   = self._stat_card(stats_row, "ERRORS",     RED)

        # Progress bar
        prog_frame = tk.Frame(self, bg=BG, height=4)
        prog_frame.pack(fill="x", padx=20, pady=(0, 8))
        prog_frame.pack_propagate(False)
        self._prog_canvas = tk.Canvas(prog_frame, bg=BG3, height=4,
                                      highlightthickness=0, bd=0)
        self._prog_canvas.pack(fill="both", expand=True)
        self._prog_bar = self._prog_canvas.create_rectangle(
            0, 0, 0, 4, fill=self.ORANGE, outline="")
        self._prog_canvas.bind("<Configure>",
                               lambda e: self._update_progress(0))

        # Action bar
        act = tk.Frame(self, bg=BG)
        act.pack(fill="x", padx=20, pady=(0, 8))

        self._btn_run = FlatBtn(
            act, "🚀  FETCH LAUNCHES", self._run,
            bg=BG3, fg=self.ORANGE,
            hover_bg="#ea580c", hover_fg="#fff")
        self._btn_run.pack(side="left", padx=(0, 6))

        self._btn_stop = FlatBtn(act, "■  STOP", self._stop,
                                 bg=BG3, fg=RED, hover_bg=RED, hover_fg="#fff")
        self._btn_stop.set_disabled(True)
        self._btn_stop.pack(side="left", padx=(0, 6))

        FlatBtn(act, "[>] LATEST REPORT", self._open_report,
                bg=BG3, fg=TEXT, hover_fg=self.ORANGE
                ).pack(side="left", padx=(0, 6))

        FlatBtn(act, "[F] DOCUMENTS", self._open_folder,
                bg=BG3, fg=TEXT_DIM, hover_fg=self.ORANGE
                ).pack(side="left", padx=(0, 6))

        FlatBtn(act, "[X] CLEAR", self._clear_log,
                bg=BG3, fg=TEXT_MUTE, hover_fg=RED).pack(side="right")

        # Log area
        log_frame = tk.Frame(self, bg=BG)
        log_frame.pack(fill="both", expand=True, padx=20, pady=(0, 16))

        log_hdr = tk.Frame(log_frame, bg=PANEL, pady=6)
        log_hdr.pack(fill="x")
        tk.Label(log_hdr, text=">> LIVE TELEMETRY", font=FONT_MONO,
                 bg=PANEL, fg=self.ORANGE).pack(side="left", padx=12)
        self._log_count = tk.Label(log_hdr, text="0 lines", font=FONT_MONO,
                                   bg=PANEL, fg=TEXT_MUTE)
        self._log_count.pack(side="right", padx=12)

        txt_frame = tk.Frame(log_frame, bg=BG2)
        txt_frame.pack(fill="both", expand=True)

        self._log = tk.Text(txt_frame, bg=BG, fg=TEXT_DIM,
                            font=FONT_MONO, relief="flat", bd=0,
                            insertbackground=TEXT, state="disabled",
                            wrap="word", padx=12, pady=8)
        sb = tk.Scrollbar(txt_frame, command=self._log.yview,
                          bg=BG3, troughcolor=BG, width=6)
        self._log.config(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._log.pack(fill="both", expand=True)

        # Text tags
        self._log.tag_config("match",   foreground=AMBER)
        self._log.tag_config("error",   foreground=RED)
        self._log.tag_config("info",    foreground=CYAN)
        self._log.tag_config("warn",    foreground=YELLOW)
        self._log.tag_config("done",    foreground=NEON)
        self._log.tag_config("default", foreground=TEXT_DIM)
        self._log.tag_config("row_a",   background="#03060f")
        self._log.tag_config("row_b",   background="#070d1e")
        self._log.tag_config("ts",      foreground=TEXT_MUTE)

    def _stat_card(self, parent, label, color):
        outer = tk.Frame(parent, bg=color)
        outer.pack(side="left", padx=(0, 8), fill="x", expand=True)
        tk.Frame(outer, bg=color, height=2).pack(fill="x")
        f = tk.Frame(outer, bg=PANEL, padx=16, pady=12)
        f.pack(fill="both", expand=True)
        val = tk.Label(f, text="0", font=("Segoe UI", 28, "bold"),
                       bg=PANEL, fg=color)
        val.pack(anchor="w")
        tk.Label(f, text=label, font=("Consolas", 8, "bold"),
                 bg=PANEL, fg=TEXT_DIM).pack(anchor="w", pady=(2, 0))
        bar_bg = tk.Frame(f, bg=BG3, height=3)
        bar_bg.pack(fill="x", pady=(8, 0))
        bar_fill = tk.Frame(bar_bg, bg=color, height=3, width=0)
        bar_fill.place(x=0, y=0, relheight=1)
        return val, bar_fill

    # ── Actions ────────────────────────────────────────────────────────────────
    def _run(self):
        if self._running:
            return
        self._running  = True
        self._seconds  = 0
        self._upcoming = 0
        self._recent   = 0
        self._go       = 0
        self._errors   = 0
        self._set_status("FETCHING", CYAN)
        self._start_pulse(CYAN)
        self._btn_run.set_disabled(True)
        self._btn_stop.set_disabled(False)
        self._update_stat(self._stat_upcoming, 0)
        self._update_stat(self._stat_recent,   0)
        self._update_stat(self._stat_go,       0)
        self._update_stat(self._stat_errors,   0)
        self._update_progress(0)
        self._append(
            f"[{datetime.now().strftime('%H:%M:%S')}] Fetching rocket launches...\n",
            "info"
        )
        self._tick()
        threading.Thread(target=self._worker, daemon=True).start()

    def _stop(self):
        if self._proc:
            try:
                self._proc.terminate()
            except Exception:
                pass
        self._finish("STOPPED", RED)

    def _worker(self):
        try:
            self._proc = subprocess.Popen(
                [sys.executable, "-u", self.script],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                cwd=LAUNCH_DIR, bufsize=1, env=ENV
            )
            for line in self._proc.stdout:
                self._handle_line(line.rstrip("\n"))
            self._proc.wait()
            rc = self._proc.returncode
            if rc == 0:
                self.after(0, lambda: self._finish("COMPLETE", GREEN))
            else:
                self.after(0, lambda: self._finish(f"EXIT {rc}", RED))
        except Exception as e:
            self.after(0, lambda: self._finish(f"ERROR: {e}", RED))

    def _handle_line(self, line):
        if not line.strip():
            return
        tag = "default"
        if "[+]" in line:
            tag = "match"
        elif "[!]" in line:
            tag = "error"
            self._errors += 1
            self.after(0, lambda v=self._errors:
                       self._update_stat(self._stat_errors, v))
        elif "[*]" in line:
            tag = "info"
        elif "===" in line or "---" in line:
            tag = "warn"
        elif "Report saved" in line or "DONE" in line:
            tag = "done"

        # Parse counts from output
        m = re.search(r"Total upcoming\s*:\s*(\d+)", line, re.I)
        if m:
            self.after(0, lambda v=int(m.group(1)):
                       self._update_stat(self._stat_upcoming, v))

        m = re.search(r"Total recent\s*:\s*(\d+)", line, re.I)
        if m:
            self.after(0, lambda v=int(m.group(1)):
                       self._update_stat(self._stat_recent, v))

        m = re.search(r"UPCOMING LAUNCHES \((\d+)\)", line)
        if m:
            self.after(0, lambda v=int(m.group(1)):
                       self._update_stat(self._stat_upcoming, v))

        m = re.search(r"RECENT LAUNCHES \((\d+)\)", line)
        if m:
            self.after(0, lambda v=int(m.group(1)):
                       self._update_stat(self._stat_recent, v))

        m = re.search(r"Status: GO\s*:\s*(\d+)", line, re.I)
        if m:
            self.after(0, lambda v=int(m.group(1)):
                       self._update_stat(self._stat_go, v))

        # Progress milestones
        if "Upcoming Launches" in line:
            self.after(0, lambda: self._update_progress(40))
        if "Recent Launches" in line:
            self.after(0, lambda: self._update_progress(70))
        if "Generating report" in line:
            self.after(0, lambda: self._update_progress(90))
        if "Report saved" in line:
            self.after(0, lambda: self._update_progress(100))

        self.after(0, lambda l=line, t=tag: self._append(l + "\n", t))

    def _finish(self, msg, color):
        self._running = False
        if self._timer_id:
            self.after_cancel(self._timer_id)
            self._timer_id = None
        self._set_status(msg, color)
        self._btn_run.set_disabled(False)
        self._btn_stop.set_disabled(True)
        self._update_progress(100)
        self._append(f"\n-- {msg} --\n", "warn")

    def _tick(self):
        if not self._running:
            return
        self._seconds += 1
        m = self._seconds // 60
        s = self._seconds % 60
        self._timer_lbl.config(text=f"{m:02d}:{s:02d}")
        self._timer_id = self.after(1000, self._tick)

    def _set_status(self, text, color):
        self._stop_pulse()
        self._status_dot.config(fg=color)
        self._status_lbl.config(text=text, fg=color)

    def _start_pulse(self, color):
        self._pulse_color = color
        self._pulse_on    = True
        self._pulse_tick()

    def _stop_pulse(self):
        if self._pulse_id:
            try: self.after_cancel(self._pulse_id)
            except Exception: pass
            self._pulse_id = None
        self._pulse_color = None

    def _pulse_tick(self):
        if not self._pulse_color:
            return
        c = self._pulse_color if self._pulse_on else dim(self._pulse_color, 0.35)
        try:
            self._status_dot.config(fg=c)
        except Exception:
            return
        self._pulse_on = not self._pulse_on
        self._pulse_id = self.after(550, self._pulse_tick)

    def _update_stat(self, stat_tuple, value):
        val_lbl, bar_fill = stat_tuple
        val_lbl.config(text=str(value))
        parent_w = bar_fill.master.winfo_width()
        if parent_w > 1:
            pct = min(1.0, value / 50)
            bar_fill.place(x=0, y=0, relheight=1, width=int(parent_w * pct))

    def _update_progress(self, pct):
        w = self._prog_canvas.winfo_width()
        if w > 1:
            self._prog_canvas.coords(
                self._prog_bar, 0, 0, int(w * pct / 100), 4)

    def _append(self, text, tag="default"):
        self._log.config(state="normal")
        row_tag = "row_b" if self._row_alt else "row_a"
        self._row_alt = not self._row_alt
        ts = datetime.now().strftime("%H:%M:%S  ")
        self._log.insert("end", ts,   ("ts",  row_tag))
        self._log.insert("end", text, (tag,   row_tag))
        self._log.see("end")
        self._log.config(state="disabled")
        self._lines += 1
        self._log_count.config(text=f"{self._lines} lines")

    def _clear_log(self):
        self._log.config(state="normal")
        self._log.delete("1.0", "end")
        self._log.config(state="disabled")
        self._lines = 0
        self._log_count.config(text="0 lines")

    def _open_report(self):
        docs = sorted(
            glob.glob(os.path.join(self.docs_dir, "*.docx")), reverse=True)
        if docs:
            os.startfile(docs[0])
        else:
            self._append("[!] No reports found — run a fetch first.\n", "warn")

    def _open_folder(self):
        os.makedirs(self.docs_dir, exist_ok=True)
        os.startfile(self.docs_dir)

    def stop_process(self):
        if self._proc:
            try:
                self._proc.terminate()
            except Exception:
                pass


# ── Pakistan Orbit Tracker Panel ──────────────────────────────────────────────
class OrbitTrackerPanel(tk.Frame):
    """
    Launches the Pakistan Orbit Tracker web app (React + FastAPI).
    Backend: FastAPI on port 8001
    Frontend: Vite on port 8080
    Opens in browser automatically.
    """

    TEAL = "#06b6d4"

    def __init__(self, parent, **kw):
        super().__init__(parent, bg=BG, **kw)
        self._backend_proc  = None
        self._frontend_proc = None
        self._running       = False
        self._seconds       = 0
        self._timer_id      = None
        self._lines         = 0
        self._row_alt       = False
        self._pulse_id      = None
        self._pulse_color   = None
        self._pulse_on      = False
        self._backend_autostarted = False
        self._backend_starting    = False
        self._backend_watchdog_id = None
        self.BACKEND_WATCHDOG_MS  = 30 * 1000     # health-check every 30 s
        self._build()
        # Bring the FastAPI backend up the moment the app opens AND keep a
        # watchdog on it — if it ever dies, the watchdog restarts it within
        # ~30 s. The user should never have to think about the backend again.
        self._autostart_backend()
        self._schedule_backend_watchdog()

    @staticmethod
    def _backend_python():
        """Python interpreter for the backend — prefer the project venv
        (it has uvicorn/fastapi installed), fall back to the app's Python."""
        venv_py = os.path.join(ORBIT_DIR, "backend", ".venv", "Scripts", "python.exe")
        if os.path.isfile(venv_py):
            return venv_py
        return sys.executable

    def _autostart_backend(self, reason: str = "app launch"):
        """Start the FastAPI backend (port 8001) in the background and keep
        it running. Idempotent — if :8001 already answers it does nothing,
        and concurrent calls are coalesced via the `_backend_starting` flag
        so the watchdog and the launch path never fight."""
        if self._backend_starting:
            return
        self._backend_starting = True

        def _worker():
            import urllib.request, time
            try:
                # Already healthy? Nothing to do.
                try:
                    urllib.request.urlopen(
                        "http://127.0.0.1:8001/api/health", timeout=2)
                    self.after(0, lambda: self._append(
                        "[Backend] Healthy on :8001 — no action needed.\n", "info"))
                    return
                except Exception:
                    pass
                self.after(0, lambda r=reason: self._append(
                    f"[Backend] Bringing the backend up ({r})...\n", "info"))
                # Clear any dead/zombie holder of the port, then start fresh.
                self._free_port(8001)
                backend_dir = os.path.join(ORBIT_DIR, "backend")
                py = self._backend_python()
                self._backend_proc = subprocess.Popen(
                    [py, "-m", "uvicorn", "main:app",
                     "--host", "127.0.0.1", "--port", "8001"],
                    cwd=backend_dir, env=ENV,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    text=True, encoding="utf-8", errors="replace",
                )
                self._backend_autostarted = True
                threading.Thread(target=self._stream_backend, daemon=True).start()
                for _ in range(20):
                    time.sleep(1)
                    if self._backend_proc.poll() is not None:
                        self.after(0, lambda: self._append(
                            "[Backend] ⚠ Backend exited on start — the watchdog "
                            "will retry shortly.\n", "warn"))
                        return
                    try:
                        urllib.request.urlopen(
                            "http://127.0.0.1:8001/api/health", timeout=1)
                        self.after(0, lambda: self._append(
                            "[Backend] ✅ Ready at http://127.0.0.1:8001\n", "done"))
                        return
                    except Exception:
                        pass
                self.after(0, lambda: self._append(
                    "[Backend] ⚠ Backend slow to respond — watchdog will keep "
                    "checking.\n", "warn"))
            except Exception as e:
                self.after(0, lambda e=e: self._append(
                    f"[Backend] Autostart failed: {e}\n", "error"))
            finally:
                self._backend_starting = False

        threading.Thread(target=_worker, daemon=True).start()

    def _schedule_backend_watchdog(self):
        """(Re)arm the periodic backend health check."""
        try:
            self._backend_watchdog_id = self.after(
                self.BACKEND_WATCHDOG_MS, self._backend_watchdog)
        except Exception:
            self._backend_watchdog_id = None

    def _backend_watchdog(self):
        """Every BACKEND_WATCHDOG_MS: confirm the backend still answers on
        :8001, and if it has died, bring it straight back. This is what
        makes 'backend not working' a non-issue — it self-heals, whether the
        backend crashed, was killed, or never came up. Re-arms itself for
        the life of the app."""
        def _check():
            import urllib.request
            alive = False
            try:
                urllib.request.urlopen(
                    "http://127.0.0.1:8001/api/health", timeout=3)
                alive = True
            except Exception:
                alive = False
            if not alive and not self._backend_starting:
                self.after(0, lambda: self._append(
                    "[Watchdog] Backend not responding — restarting it.\n",
                    "warn"))
                self._autostart_backend(reason="watchdog restart")
            # Re-arm the watchdog regardless of outcome.
            self.after(0, self._schedule_backend_watchdog)
        threading.Thread(target=_check, daemon=True).start()

    def _build(self):
        # Header
        hdr = tk.Frame(self, bg=PANEL, pady=14)
        hdr.pack(fill="x", pady=(0, 10))
        tk.Label(hdr, text="🌍  Pakistan Orbit Tracker",
                 font=("Segoe UI", 16, "bold"), bg=PANEL, fg=TEXT
                 ).pack(side="left", padx=20)
        right = tk.Frame(hdr, bg=PANEL)
        right.pack(side="right", padx=20)
        self._status_dot = tk.Label(right, text="●", font=("Segoe UI", 12),
                                    bg=PANEL, fg=TEXT_MUTE)
        self._status_dot.pack(side="left")
        self._status_lbl = tk.Label(right, text="OFFLINE", font=FONT_MONO,
                                    bg=PANEL, fg=TEXT_MUTE)
        self._status_lbl.pack(side="left", padx=(4, 16))
        self._timer_lbl = tk.Label(right, text="00:00",
                                   font=("Consolas", 18), bg=PANEL, fg=self.TEAL)
        self._timer_lbl.pack(side="left")

        # Subtitle
        tk.Label(self,
                 text="Live satellite tracking over Pakistan · React + FastAPI · Opens in browser",
                 font=FONT_SM, bg=BG, fg=TEXT_DIM
                 ).pack(anchor="w", padx=20, pady=(0, 8))

        # Info cards
        info_row = tk.Frame(self, bg=BG)
        info_row.pack(fill="x", padx=20, pady=(0, 16))

        for label, value, color in [
            ("BACKEND",  "FastAPI · Port 8001", self.TEAL),
            ("FRONTEND", "Vite React · Port 8080", "#a78bfa"),
            ("MAP",      "Leaflet · satellite.js", "#f97316"),
            ("DATA",     "CelesTrak TLE", "#22c55e"),
        ]:
            f = tk.Frame(info_row, bg=PANEL, padx=16, pady=14)
            f.pack(side="left", padx=(0, 8), fill="x", expand=True)
            tk.Label(f, text=value, font=("Segoe UI", 10, "bold"),
                     bg=PANEL, fg=color).pack()
            tk.Label(f, text=label, font=("Consolas", 8),
                     bg=PANEL, fg=TEXT_MUTE).pack()

        # Action bar
        act = tk.Frame(self, bg=BG)
        act.pack(fill="x", padx=20, pady=(0, 16))

        self._btn_start = FlatBtn(
            act, "▶  LAUNCH ORBIT TRACKER", self._start,
            bg=BG3, fg=self.TEAL,
            hover_bg=self.TEAL, hover_fg=BG)
        self._btn_start.pack(side="left", padx=(0, 6))

        self._btn_stop = FlatBtn(act, "■  STOP", self._stop,
                                 bg=BG3, fg=RED, hover_bg=RED, hover_fg="#fff")
        self._btn_stop.set_disabled(True)
        self._btn_stop.pack(side="left", padx=(0, 6))

        FlatBtn(act, "🌐  OPEN IN BROWSER", self._open_browser,
                bg="#0a1a2a", fg=self.TEAL, hover_fg="#fff"
                ).pack(side="left", padx=(0, 6))

        FlatBtn(act, "[F] OPEN FOLDER", self._open_folder,
                bg=BG3, fg=TEXT_DIM, hover_fg=self.TEAL
                ).pack(side="left", padx=(0, 6))

        FlatBtn(act, "[X] CLEAR", self._clear_log,
                bg=BG3, fg=TEXT_MUTE, hover_fg=RED).pack(side="right")

        # URLs display
        url_frame = tk.Frame(self, bg=BG3, pady=10)
        url_frame.pack(fill="x", padx=20, pady=(0, 12))
        tk.Label(url_frame, text="  Frontend: http://127.0.0.1:8080",
                 font=FONT_MONO, bg=BG3, fg=self.TEAL).pack(side="left", padx=8)
        tk.Label(url_frame, text="|", font=FONT_MONO, bg=BG3, fg=BORDER).pack(side="left")
        tk.Label(url_frame, text="  Backend API: http://127.0.0.1:8001/docs",
                 font=FONT_MONO, bg=BG3, fg="#a78bfa").pack(side="left", padx=8)

        # Log
        log_frame = tk.Frame(self, bg=BG)
        log_frame.pack(fill="both", expand=True, padx=20, pady=(0, 16))
        log_hdr = tk.Frame(log_frame, bg=PANEL, pady=6)
        log_hdr.pack(fill="x")
        tk.Label(log_hdr, text=">> STARTUP LOG", font=FONT_MONO,
                 bg=PANEL, fg=self.TEAL).pack(side="left", padx=12)
        self._log_count = tk.Label(log_hdr, text="0 lines", font=FONT_MONO,
                                   bg=PANEL, fg=TEXT_MUTE)
        self._log_count.pack(side="right", padx=12)
        txt_frame = tk.Frame(log_frame, bg=BG2)
        txt_frame.pack(fill="both", expand=True)
        self._log = tk.Text(txt_frame, bg=BG, fg=TEXT_DIM, font=FONT_MONO,
                            relief="flat", bd=0, state="disabled",
                            wrap="word", padx=12, pady=8)
        sb = tk.Scrollbar(txt_frame, command=self._log.yview,
                          bg=BG3, troughcolor=BG, width=6)
        self._log.config(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._log.pack(fill="both", expand=True)
        self._log.tag_config("match",   foreground=NEON)
        self._log.tag_config("error",   foreground=RED)
        self._log.tag_config("info",    foreground=CYAN)
        self._log.tag_config("warn",    foreground=YELLOW)
        self._log.tag_config("done",    foreground=GREEN)
        self._log.tag_config("default", foreground=TEXT_DIM)
        self._log.tag_config("row_a",   background="#03060f")
        self._log.tag_config("row_b",   background="#070d1e")
        self._log.tag_config("ts",      foreground=TEXT_MUTE)

    def _terminate_procs(self):
        """Kill any tracker subprocesses this panel owns. UI state untouched."""
        for proc in (self._backend_proc, self._frontend_proc):
            if proc and proc.poll() is None:
                try:
                    if os.name == "nt":
                        subprocess.run(
                            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                            capture_output=True,
                        )
                    else:
                        proc.terminate()
                except Exception:
                    pass
        self._backend_proc  = None
        self._frontend_proc = None

    def _start(self):
        # Re-launch: kill anything from a previous launch (procs or external
        # .bat-spawned ones — _worker frees ports too) so this button always
        # does something instead of silently no-op'ing when _running is stale.
        if self._running or self._backend_proc or self._frontend_proc:
            self._terminate_procs()
            if self._timer_id:
                self.after_cancel(self._timer_id)
                self._timer_id = None
            self._append("[Restart] Relaunching tracker — terminating previous instance.\n", "warn")
        self._running = True
        self._seconds = 0
        self._btn_start.set_disabled(True)
        self._btn_stop.set_disabled(False)
        self._status_dot.config(fg=self.TEAL)
        self._status_lbl.config(text="STARTING", fg=self.TEAL)
        self._start_pulse(self.TEAL)
        self._append(f"[{datetime.now().strftime('%H:%M:%S')}] Launching Pakistan Orbit Tracker...\n", "info")
        self._tick()
        threading.Thread(target=self._worker, daemon=True).start()

    @staticmethod
    def _find_node():
        """Locate node.exe — common install paths first, then PATH."""
        candidates = [
            r"C:\Program Files\nodejs\node.exe",
            r"C:\Program Files (x86)\nodejs\node.exe",
            os.path.join(os.environ.get("LOCALAPPDATA", ""),
                         "Programs", "nodejs", "node.exe"),
        ]
        for c in candidates:
            if c and os.path.isfile(c):
                return c
        import shutil
        return shutil.which("node")

    def _free_port(self, port: int) -> None:
        """Kill any process LISTENING/ESTABLISHED on `port` (Windows), tree
        included. Clears orphaned Vite/uvicorn instances before a fresh
        launch — without this, a leftover process squats on the port and
        the next launch fails."""
        if os.name != "nt":
            return
        try:
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True, text=True,
                encoding="utf-8", errors="replace",
            )
            killed = set()
            needle = f":{port} "
            for line in result.stdout.splitlines():
                if needle in line and ("LISTENING" in line or "ESTABLISHED" in line):
                    parts = line.split()
                    if parts:
                        pid = parts[-1]
                        if pid.isdigit() and pid != "0" and pid not in killed:
                            subprocess.run(
                                ["taskkill", "/F", "/T", "/PID", pid],
                                capture_output=True,
                            )
                            killed.add(pid)
            if killed:
                self.after(0, lambda k=killed, p=port: self._append(
                    f"[Cleanup] Port {p}: killed PID(s) {', '.join(sorted(k))}\n",
                    "warn"))
                import time as _t
                _t.sleep(1)   # let the OS release the socket
            else:
                self.after(0, lambda p=port: self._append(
                    f"[Cleanup] Port {p} is free.\n", "info"))
        except Exception as _e:
            self.after(0, lambda _e=_e, p=port: self._append(
                f"[Cleanup] Port {p} cleanup warning: {_e}\n", "warn"))

    def _worker(self):
        try:
            import urllib.request as _urlreq
            backend_dir = os.path.join(ORBIT_DIR, "backend")

            # If the backend was already auto-started at app launch (or a
            # previous LAUNCH) and is healthy, reuse it — don't tear it down.
            backend_already_up = False
            try:
                _urlreq.urlopen("http://127.0.0.1:8001/api/health", timeout=2)
                backend_already_up = True
                self.after(0, lambda: self._append(
                    "[Backend] Already running on :8001 — reusing it.\n", "info"))
            except Exception:
                backend_already_up = False

            if not backend_already_up:
                # ── Step 0: Free port 8001 if already occupied ────────────
                self.after(0, lambda: self._append("[Cleanup] Freeing port 8001...\n", "info"))
                self._free_port(8001)

                # ── Step 1: Start Python backend ──────────────────────────
                # Prefer the project venv (has uvicorn/fastapi); the system
                # Python may not — but if the venv is missing, fall back and
                # install requirements into the system interpreter.
                py = self._backend_python()
                self.after(0, lambda: self._append(f"[Backend] Using Python: {py}\n", "info"))

                if py == sys.executable:
                    req_file = os.path.join(backend_dir, "requirements.txt")
                    if os.path.exists(req_file):
                        self.after(0, lambda: self._append("[Backend] Installing requirements...\n", "info"))
                        subprocess.run(
                            [py, "-m", "pip", "install", "-r", req_file, "--quiet"],
                            cwd=backend_dir, env=ENV,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                        )

                self.after(0, lambda: self._append("[Backend] Starting FastAPI on port 8001...\n", "info"))

                self._backend_proc = subprocess.Popen(
                    [py, "-m", "uvicorn", "main:app",
                     "--host", "127.0.0.1", "--port", "8001"],
                    cwd=backend_dir, env=ENV,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    text=True, encoding="utf-8", errors="replace"
                )

                # Stream backend output in background
                threading.Thread(target=self._stream_backend, daemon=True).start()

            # Wait for backend to be ready
            import time, urllib.request
            for i in range(15):
                time.sleep(1)
                try:
                    urllib.request.urlopen("http://127.0.0.1:8001/api/health", timeout=1)
                    self.after(0, lambda: self._append("[Backend] ✅ Ready at http://127.0.0.1:8001\n", "done"))
                    break
                except Exception:
                    self.after(0, lambda i=i: self._append(f"[Backend] Waiting... ({i+1}/15)\n", "default"))
            else:
                self.after(0, lambda: self._append("[Backend] ⚠ Backend may not be ready — continuing anyway\n", "warn"))

            # ── Step 2: Start Vite frontend ───────────────────────────────────
            # Free port 8080 first — a leftover/orphaned Vite from a prior
            # run would otherwise squat the port and break this launch.
            self.after(0, lambda: self._append("[Frontend] Freeing port 8080...\n", "info"))
            self._free_port(8080)
            self.after(0, lambda: self._append("[Frontend] Starting Vite on port 8080...\n", "info"))

            # Verify node_modules — Vite can't start without them
            if not os.path.exists(os.path.join(ORBIT_DIR, "node_modules")):
                self.after(0, lambda: self._append(
                    "[Frontend] ⚠ node_modules missing — running 'npm install' first (this can take 2-3 min)\n", "warn"))
                if os.name == "nt":
                    inst = subprocess.run(
                        ["cmd.exe", "/c", "npm.cmd", "install"],
                        cwd=ORBIT_DIR, env=ENV,
                        capture_output=True, text=True, encoding="utf-8", errors="replace"
                    )
                else:
                    inst = subprocess.run(
                        ["npm", "install"],
                        cwd=ORBIT_DIR, env=ENV,
                        capture_output=True, text=True, encoding="utf-8", errors="replace"
                    )
                if inst.returncode != 0:
                    self.after(0, lambda: self._append(
                        f"[Frontend] ❌ npm install failed:\n{inst.stderr[:500]}\n", "error"))
                    self.after(0, lambda: self._set_status("ERROR", RED))
                    return

            # Launch Vite DIRECTLY via node (node_modules/vite/bin/vite.js)
            # so _frontend_proc IS the real Vite process — not a cmd.exe /
            # npm.cmd wrapper that can exit on its own (code 1) and orphan
            # Vite on port 8080. stdin=DEVNULL gives Vite a clean non-TTY
            # handle instead of the invalid one inherited from pythonw.
            node_exe = self._find_node()
            vite_js  = os.path.join(ORBIT_DIR, "node_modules", "vite", "bin", "vite.js")
            if node_exe and os.path.isfile(vite_js):
                self.after(0, lambda n=node_exe: self._append(
                    f"[Frontend] Using Node: {n}\n", "info"))
                self._frontend_proc = subprocess.Popen(
                    [node_exe, vite_js],
                    cwd=ORBIT_DIR, env=ENV,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    text=True, encoding="utf-8", errors="replace"
                )
            else:
                # Fallback — node or vite.js not found, go through npm.
                self.after(0, lambda: self._append(
                    "[Frontend] node/vite.js not found — falling back to npm\n", "warn"))
                if os.name == "nt":
                    self._frontend_proc = subprocess.Popen(
                        ["cmd.exe", "/c", "npm.cmd", "run", "dev"],
                        cwd=ORBIT_DIR, env=ENV,
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        stdin=subprocess.DEVNULL,
                        text=True, encoding="utf-8", errors="replace"
                    )
                else:
                    self._frontend_proc = subprocess.Popen(
                        ["npm", "run", "dev"],
                        cwd=ORBIT_DIR, env=ENV,
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        stdin=subprocess.DEVNULL,
                        text=True, encoding="utf-8", errors="replace"
                    )

            # Stream frontend output (errors will show up live in the log now)
            threading.Thread(target=self._stream_frontend, daemon=True).start()

            # Poll the actual port — Vite first-run takes 5-10s for dep optimization
            self.after(0, lambda: self._append("[Frontend] Waiting for Vite to be ready...\n", "info"))
            frontend_ready = False
            for i in range(40):                 # up to ~40 seconds
                time.sleep(1)
                # Bail if the process died
                if self._frontend_proc.poll() is not None:
                    self.after(0, lambda: self._append(
                        f"[Frontend] ❌ Vite exited with code {self._frontend_proc.returncode}\n", "error"))
                    self.after(0, lambda: self._set_status("ERROR", RED))
                    return
                try:
                    urllib.request.urlopen("http://127.0.0.1:8080", timeout=1)
                    frontend_ready = True
                    self.after(0, lambda: self._append("[Frontend] ✅ Ready at http://127.0.0.1:8080\n", "done"))
                    break
                except Exception:
                    if (i + 1) % 5 == 0:
                        self.after(0, lambda i=i: self._append(f"[Frontend] Waiting... ({i+1}/40)\n", "default"))

            if not frontend_ready:
                self.after(0, lambda: self._append(
                    "[Frontend] ⚠ Vite didn't respond within 40s — opening browser anyway\n", "warn"))

            # ── Step 3: Open browser (only after Vite is confirmed ready) ────
            # Open the same origin the .bat auto-launch uses (127.0.0.1) so the
            # browser's per-origin cache is shared — otherwise LAUNCH lands the
            # user on localhost:8080 with a stale bundle from a previous session.
            self.after(0, lambda: self._append("[Browser] Opening http://127.0.0.1:8080...\n", "match"))
            webbrowser.open("http://127.0.0.1:8080")

            self.after(0, lambda: self._set_status("LIVE", self.TEAL))
            self.after(0, lambda: self._append(
                "\n✅ Pakistan Orbit Tracker is running!\n"
                "   Frontend: http://127.0.0.1:8080\n"
                "   Backend:  http://127.0.0.1:8001/docs\n\n", "done"))

        except Exception as e:
            self.after(0, lambda: self._append(f"[ERROR] {e}\n", "error"))
            self.after(0, lambda: self._set_status("ERROR", RED))

    def _stream_backend(self):
        if not self._backend_proc:
            return
        for line in self._backend_proc.stdout:
            line = line.rstrip("\n")
            if line.strip():
                tag = "error" if "error" in line.lower() else "default"
                self.after(0, lambda l=line, t=tag: self._append(f"[BE] {l}\n", t))

    def _stream_frontend(self):
        if not self._frontend_proc:
            return
        for line in self._frontend_proc.stdout:
            line = line.rstrip("\n")
            if line.strip():
                tag = "match" if "localhost" in line or "ready" in line.lower() else "default"
                self.after(0, lambda l=line, t=tag: self._append(f"[FE] {l}\n", t))

    def _stop(self):
        self._running = False
        if self._timer_id:
            self.after_cancel(self._timer_id)
            self._timer_id = None
        self._terminate_procs()
        self._btn_start.set_disabled(False)
        self._btn_stop.set_disabled(True)
        self._set_status("OFFLINE", TEXT_MUTE)
        self._append("\n[Stopped] Both services terminated.\n", "warn")

    def _open_browser(self):
        webbrowser.open("http://127.0.0.1:8080")

    def _open_folder(self):
        os.startfile(ORBIT_DIR)

    def _tick(self):
        if not self._running:
            return
        self._seconds += 1
        m = self._seconds // 60
        s = self._seconds % 60
        self._timer_lbl.config(text=f"{m:02d}:{s:02d}")
        self._timer_id = self.after(1000, self._tick)

    def _set_status(self, text, color):
        self._stop_pulse()
        self._status_dot.config(fg=color)
        self._status_lbl.config(text=text, fg=color)

    def _start_pulse(self, color):
        self._pulse_color = color
        self._pulse_on    = True
        self._pulse_tick()

    def _stop_pulse(self):
        if self._pulse_id:
            try: self.after_cancel(self._pulse_id)
            except Exception: pass
            self._pulse_id = None
        self._pulse_color = None

    def _pulse_tick(self):
        if not self._pulse_color:
            return
        c = self._pulse_color if self._pulse_on else dim(self._pulse_color, 0.35)
        try:
            self._status_dot.config(fg=c)
        except Exception:
            return
        self._pulse_on = not self._pulse_on
        self._pulse_id = self.after(550, self._pulse_tick)

    def _append(self, text, tag="default"):
        self._log.config(state="normal")
        row_tag = "row_b" if self._row_alt else "row_a"
        self._row_alt = not self._row_alt
        ts = datetime.now().strftime("%H:%M:%S  ")
        self._log.insert("end", ts,   ("ts",  row_tag))
        self._log.insert("end", text, (tag,   row_tag))
        self._log.see("end")
        self._log.config(state="disabled")
        self._lines += 1
        self._log_count.config(text=f"{self._lines} lines")

    def _clear_log(self):
        self._log.config(state="normal")
        self._log.delete("1.0", "end")
        self._log.config(state="disabled")
        self._lines = 0
        self._log_count.config(text="0 lines")

    def stop_process(self):
        self._stop()


# ── Calendar day detail popup ────────────────────────────────────────────────
class CalDayPopup(tk.Toplevel):
    """Full-detail popup for a single forecast day, opened by double-clicking a calendar row."""

    def __init__(self, parent, day: dict):
        super().__init__(parent)
        date = day.get("date", "?")
        self.title(f"Day Detail — {date}")
        self.configure(bg=BG)
        self.resizable(True, True)
        self.geometry("900x600")
        self.attributes("-topmost", True)

        # ── Title bar ────────────────────────────────────────────────────────
        hdr = tk.Frame(self, bg=PANEL, pady=6)
        hdr.pack(fill="x")
        tk.Label(hdr, text=f"  DETAILED CROSSINGS — {date}",
                 font=FONT_HEAD, bg=PANEL, fg=CYAN, anchor="w").pack(side="left")
        tk.Button(hdr, text="✕ Close", font=FONT_SM, bg=BG3, fg=TEXT_DIM,
                  bd=0, padx=10, command=self.destroy).pack(side="right", padx=8)

        # ── Stat strip ───────────────────────────────────────────────────────
        t = day.get("totals", {})
        stat_row = tk.Frame(self, bg=BG2, pady=4)
        stat_row.pack(fill="x")
        for lbl, val, col in [
            (f"🇮🇳 India overhead",  t.get("indian_overhead", 0),   RED),
            (f"🇮🇳 India tilt-range", t.get("indian_tilt_range", 0), "#ff8888"),
            ("Other overhead",        t.get("other_overhead", 0),    GREEN),
            ("Other tilt-range",      t.get("other_tilt_range", 0),  AMBER),
            ("Unique sats",           t.get("unique_sats", 0),       CYAN),
            (f"Blind {t.get('blind_minutes',0):.0f} min",
             f"{int(t.get('blind_minutes',0)/14.4)}%",              YELLOW),
        ]:
            f = tk.Frame(stat_row, bg=BG2, padx=10)
            f.pack(side="left")
            tk.Label(f, text=str(val), font=("Consolas", 14, "bold"),
                     bg=BG2, fg=col).pack()
            tk.Label(f, text=lbl, font=FONT_SM, bg=BG2,
                     fg=TEXT_DIM).pack()

        # ── Crossings table ──────────────────────────────────────────────────
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=8, pady=6)

        style = ttk.Style(self)
        style.configure("Cal.Treeview",
                        background=BG2, foreground=TEXT,
                        fieldbackground=BG2, rowheight=22, font=FONT_MONO)
        style.configure("Cal.Treeview.Heading",
                        background=PANEL, foreground=CYAN,
                        relief="flat", font=("Consolas", 9, "bold"))
        style.map("Cal.Treeview",
                  background=[("selected", ACCENT)],
                  foreground=[("selected", "#fff")])

        cols = ("time", "pass_type", "sat", "country", "operator",
                "sensor_cat", "sensor", "duration", "dir", "dist")
        tree = ttk.Treeview(body, columns=cols, show="headings",
                            style="Cal.Treeview")
        for col, lbl, w, anchor in [
            ("time",       "PKT Time",   90, "center"),
            ("pass_type",  "Pass",        90, "center"),
            ("sat",        "Satellite",  190, "w"),
            ("country",    "Country",    100, "w"),
            ("operator",   "Operator",   120, "w"),
            ("sensor_cat", "Category",    80, "center"),
            ("sensor",     "Sensor",     130, "w"),
            ("duration",   "Dur (min)",   80, "center"),
            ("dir",        "Direction",   80, "center"),
            ("dist",       "Off-nadir",   90, "center"),
        ]:
            tree.heading(col, text=lbl)
            tree.column(col, width=w, anchor=anchor)

        vsb = ttk.Scrollbar(body, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        tree.tag_configure("indian",   foreground=RED)
        tree.tag_configure("sar",      foreground="#a855f7")
        tree.tag_configure("military", foreground="#ef4444")
        tree.tag_configure("tilt",     foreground=AMBER)

        india  = sorted(day.get("india_crossings",  []), key=lambda x: x["entry_utc"])
        others = sorted(day.get("other_crossings",  []), key=lambda x: x["entry_utc"])
        for cr in india + others:
            sc  = cr.get("sensor_category", cr.get("sensor", "Optical"))
            tag = []
            if cr.get("is_indian"):                              tag.append("indian")
            elif "MILITARY" in sc.upper():                       tag.append("military")
            elif "SAR" in sc.upper():                            tag.append("sar")
            if cr.get("pass_type") == "tilt-range":             tag.append("tilt")
            dist = (f"~{int(cr.get('min_dist_km',0))} km"
                    if cr.get("pass_type") == "tilt-range" else "overhead")
            tree.insert("", "end", tags=tuple(tag), values=(
                _utc_to_pkt(cr["entry_utc"]),
                "OVERHEAD" if cr.get("pass_type") == "overhead" else "TILT-RANGE",
                cr.get("name", "?"),
                cr.get("country", "?"),
                cr.get("operator", cr.get("owner", "?")),
                sc,
                cr.get("sensor", "?"),
                f"{cr.get('duration_min', 0):.1f}",
                cr.get("direction", "N/A"),
                dist,
            ))

        # ── Observation windows strip ─────────────────────────────────────────
        ow_frame = tk.Frame(self, bg=PANEL, pady=4, padx=8)
        ow_frame.pack(fill="x")
        tk.Label(ow_frame, text="Observation windows (PKT): ",
                 font=FONT_MONO, bg=PANEL, fg=TEXT_DIM).pack(side="left")
        ows = day.get("observation_windows", [])
        if ows:
            parts = []
            for ow in ows:
                s = _utc_to_pkt(ow["start"])[:5] if ow.get("start") else "?"
                e = _utc_to_pkt(ow["end"])[:5]   if ow.get("end")   else "?"
                parts.append(f"{s}–{e}")
            tk.Label(ow_frame, text="  |  ".join(parts),
                     font=FONT_MONO, bg=PANEL, fg=GREEN).pack(side="left")
        else:
            tk.Label(ow_frame, text="None", font=FONT_MONO,
                     bg=PANEL, fg=RED).pack(side="left")


# ── Accuracy-check results popup ─────────────────────────────────────────────
class AccuracyPopup(tk.Toplevel):
    """
    Shows prediction accuracy bucketed by lookback distance, plus a scrollable
    per-comparison record table.
    """

    def __init__(self, parent, result: dict):
        super().__init__(parent)
        self.title("Prediction Accuracy Check")
        self.configure(bg=BG)
        self.resizable(True, True)
        self.geometry("860x560")
        self.grab_set()
        self._build(result)
        self.focus_set()

    def _build(self, result: dict):
        # ── Header ──────────────────────────────────────────────────────────
        hdr = tk.Frame(self, bg=PANEL, pady=12)
        hdr.pack(fill="x")
        tk.Label(hdr, text="✔  PREDICTION ACCURACY CHECK",
                 font=("Segoe UI", 13, "bold"), bg=PANEL, fg=YELLOW,
                 padx=20).pack(side="left")
        tk.Label(hdr,
                 text=f"Generated: {result.get('generated_at', '?')}",
                 font=FONT_MONO, bg=PANEL, fg=TEXT_DIM, padx=20).pack(side="right")

        by_lb   = result.get("by_lookback", [])
        records = result.get("records", [])
        archives = result.get("archive_dates_available", [])

        # ── No-data notice ───────────────────────────────────────────────────
        if not by_lb:
            tk.Label(self,
                     text=("\n  Not enough data yet.\n\n"
                           "  The accuracy engine needs at least 2 daily REFRESH FORECAST runs\n"
                           "  on consecutive days so it can compare \"what we predicted for day N\"\n"
                           "  against \"what we computed on day N\" as ground truth.\n\n"
                           f"  Archives available so far: {len(archives)}  ({', '.join(archives) or 'none'})\n\n"
                           "  Run REFRESH FORECAST again tomorrow to start building the track record."),
                     font=FONT_MONO, bg=BG, fg=TEXT_DIM, justify="left",
                     anchor="nw").pack(fill="both", expand=True, padx=20, pady=20)
            tk.Button(self, text="Close", command=self.destroy,
                      bg=BG3, fg=TEXT, relief="flat", padx=16).pack(pady=10)
            return

        # ── Summary banner ───────────────────────────────────────────────────
        info_frame = tk.Frame(self, bg=BG3, pady=8)
        info_frame.pack(fill="x", padx=16, pady=(12, 6))
        tk.Label(info_frame,
                 text=(f"  Archives used: {len(archives)}   |   "
                       f"Comparisons: {len(records)}   |   "
                       f"Match window: ±30 min"),
                 font=FONT_MONO, bg=BG3, fg=TEXT_DIM).pack(side="left", padx=6)

        # ── By-lookback summary table ─────────────────────────────────────────
        tk.Label(self, text="  Accuracy by lookback distance",
                 font=("Consolas", 9, "bold"), bg=BG, fg=CYAN,
                 anchor="w").pack(fill="x", padx=16, pady=(8, 2))

        lb_frame = tk.Frame(self, bg=BG2)
        lb_frame.pack(fill="x", padx=16)

        style = ttk.Style(self)
        style.configure("Acc.Treeview",
                        background=BG2, foreground=TEXT,
                        fieldbackground=BG2, rowheight=22, font=FONT_MONO)
        style.configure("Acc.Treeview.Heading",
                        background=PANEL, foreground=CYAN,
                        relief="flat", font=("Consolas", 9, "bold"))
        style.map("Acc.Treeview", background=[("selected", ACCENT)],
                  foreground=[("selected", "#fff")])

        lb_cols = ("lookback", "samples", "accuracy", "shift", "verdict")
        lb_tree = ttk.Treeview(lb_frame, columns=lb_cols, show="headings",
                               height=min(len(by_lb), 6), style="Acc.Treeview")
        for col, lbl, w in [
            ("lookback", "Lookback", 100),
            ("samples",  "Samples",   80),
            ("accuracy", "Accuracy %", 110),
            ("shift",    "Avg shift",  110),
            ("verdict",  "Verdict",    300),
        ]:
            lb_tree.heading(col, text=lbl)
            lb_tree.column(col, width=w, anchor="center")

        for b in by_lb:
            acc = b.get("mean_accuracy_pct")
            shift = b.get("mean_shift_min")
            if acc is None:
                verdict = "—"
                tag = ()
            elif acc >= 95:
                verdict = "✔ Excellent"
                tag = ("good",)
            elif acc >= 85:
                verdict = "◎ Good"
                tag = ("ok",)
            elif acc >= 70:
                verdict = "△ Fair — growing drift"
                tag = ("warn",)
            else:
                verdict = "✖ Poor — TLE too stale"
                tag = ("bad",)

            lb_tree.insert("", "end", tags=tag, values=(
                f"{b['lookback_days']}d",
                b["sample_size"],
                f"{acc:.1f} %" if acc is not None else "—",
                f"{shift:.1f} min" if shift is not None else "—",
                verdict,
            ))

        lb_tree.tag_configure("good", foreground=GREEN)
        lb_tree.tag_configure("ok",   foreground=CYAN)
        lb_tree.tag_configure("warn", foreground=YELLOW)
        lb_tree.tag_configure("bad",  foreground=RED)
        lb_tree.pack(fill="x")

        # Methodology-mismatch advisory: when there are excluded
        # comparisons (e.g. v1 archive vs v2 ground-truth) say so loudly so
        # the operator knows the headline averages above are valid.
        ex = result.get("excluded_mismatches", 0)
        if ex:
            advisory = tk.Frame(self, bg=BG)
            advisory.pack(fill="x", padx=16, pady=(4, 0))
            tk.Label(advisory,
                     text=(f"⚠ {ex} comparison(s) excluded from the averages above "
                           f"because they cross methodology versions "
                           f"(pre-FEAT-003 v1 vs post-FEAT-003 v2). "
                           f"They are still shown in the per-comparison list "
                           f"below, tagged ‘MIXED’. The 51 % drop you saw is "
                           f"the v1→v2 transition, not SGP4 drift."),
                     font=("Consolas", 9), bg=BG, fg=AMBER,
                     wraplength=900, justify="left", anchor="w"
                     ).pack(fill="x")

        # ── Per-record detail table ──────────────────────────────────────────
        tk.Label(self, text="  Per-comparison record  (predicted-on → target date)",
                 font=("Consolas", 9, "bold"), bg=BG, fg=CYAN,
                 anchor="w").pack(fill="x", padx=16, pady=(12, 2))

        det_outer = tk.Frame(self, bg=BG2)
        det_outer.pack(fill="both", expand=True, padx=16, pady=(0, 4))

        det_cols = ("target", "predicted_on", "lookback",
                    "pred", "actual", "matched", "missed", "phantom",
                    "acc", "shift", "flag")
        det_tree = ttk.Treeview(det_outer, columns=det_cols, show="headings",
                                height=8, style="Acc.Treeview")
        for col, lbl, w in [
            ("target",       "Target date",    100),
            ("predicted_on", "Predicted on",   100),
            ("lookback",     "Lag",             50),
            ("pred",         "Predicted",        80),
            ("actual",       "Actual",           70),
            ("matched",      "Matched",          75),
            ("missed",       "Missed",           65),
            ("phantom",      "Phantom",          70),
            ("acc",          "Acc %",            70),
            ("shift",        "Avg shift",        85),
            ("flag",         "Flag",             110),
        ]:
            det_tree.heading(col, text=lbl)
            det_tree.column(col, width=w, anchor="center")

        for r in sorted(records, key=lambda x: (x["target_date"], x["lookback_days"])):
            acc = r.get("accuracy_pct")
            mismatch = r.get("methodology_mismatch", False)
            tag = ()
            if mismatch:
                # Methodology mismatch — the comparison is between archives
                # built with different classifier logic, so the accuracy
                # number is a code-change artefact (not SGP4 drift).
                # Mark visually so the operator doesn't read it as a real
                # failure.
                tag = ("mixed",)
            elif acc is not None:
                tag = ("good",) if acc >= 95 else ("ok",) if acc >= 85 else ("warn",) if acc >= 70 else ("bad",)
            flag_label = (
                f"⚠ MIXED  v{r.get('predicted_methodology','?')[1:]}"
                f"→v{r.get('actual_methodology','?')[1:]}"
            ) if mismatch else ""
            det_tree.insert("", "end", tags=tag, values=(
                r["target_date"],
                r["predicted_on"],
                f"{r['lookback_days']}d",
                r["predicted_count"],
                r["actual_count"],
                r["matched"],
                r["missed"],
                r["phantom"],
                f"{acc:.1f}" if acc is not None else "—",
                f"{r['mean_shift_min']:.1f} min" if r.get("mean_shift_min") is not None else "—",
                flag_label,
            ))
        det_tree.tag_configure("good",  foreground=GREEN)
        det_tree.tag_configure("ok",    foreground=CYAN)
        det_tree.tag_configure("warn",  foreground=YELLOW)
        det_tree.tag_configure("bad",   foreground=RED)
        det_tree.tag_configure("mixed", foreground=AMBER)

        vsb = ttk.Scrollbar(det_outer, orient="vertical", command=det_tree.yview)
        det_tree.configure(yscrollcommand=vsb.set)
        det_tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        # ── Footer ───────────────────────────────────────────────────────────
        foot = tk.Frame(self, bg=BG3, pady=8)
        foot.pack(fill="x")
        tk.Label(foot,
                 text="  Accuracy = matched / (matched + missed + phantom)  ·  "
                      "Ground truth = same-day day-0 forecast  ·  Match window ±30 min",
                 font=("Consolas", 8), bg=BG3, fg=TEXT_MUTE).pack(side="left", padx=10)
        tk.Button(foot, text="Close", command=self.destroy,
                  bg=BG3, fg=TEXT, relief="flat", padx=16, cursor="hand2").pack(side="right", padx=10)


# ── Modal popup that surfaces schedule changes vs the prior run ───────────────
class ChangesPopup(tk.Toplevel):
    """
    Dialog shown when forecast_changes.json contains real deltas the user
    hasn't yet acknowledged. Lists new / removed / shifted passes grouped
    by target date, with Indian entries highlighted in red.
    """

    @staticmethod
    def _filter_past_passes(ch: dict) -> dict:
        """Return a copy of the changes dict with already-happened entries
        removed and counts re-derived. Defensive against stale json — the
        forecast_diff writer applies the same filter at write-time."""
        from datetime import datetime as _dt
        try:
            now_utc = _dt.utcnow()
        except Exception:
            return ch  # never crash a popup over a clock issue

        def _future(ts: str) -> bool:
            try:
                return _dt.strptime(ts, "%Y-%m-%dT%H:%M:%SZ") > now_utc
            except (ValueError, TypeError):
                return True   # keep malformed entries — don't silently drop

        new_days = []
        for d in ch.get("days", []):
            new_p  = [p for p in d.get("new_passes", [])
                      if _future(p.get("entry_utc", ""))]
            rem_p  = [p for p in d.get("removed_passes", [])
                      if _future(p.get("entry_utc", ""))]
            shf_p  = [p for p in d.get("shifted_passes", [])
                      if _future(p.get("today_entry", p.get("entry_utc", "")))]
            new_days.append({
                **d,
                "new_passes":     new_p,
                "removed_passes": rem_p,
                "shifted_passes": shf_p,
                "counts": {
                    "new":     len(new_p),
                    "removed": len(rem_p),
                    "shifted": len(shf_p),
                },
            })
        totals = {
            "new":     sum(d["counts"]["new"]     for d in new_days),
            "removed": sum(d["counts"]["removed"] for d in new_days),
            "shifted": sum(d["counts"]["shifted"] for d in new_days),
            "blind_delta_min": ch.get("totals", {}).get("blind_delta_min", 0),
        }
        return {**ch, "days": new_days, "totals": totals,
                "cutoff_utc": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")}

    def __init__(self, parent, changes: dict, modal: bool = True,
                 history: list | None = None, reopen_owner=None):
        """
        modal=True  — the classic auto-fired popup: grabs focus, sits on top,
                      blocks interaction until dismissed. Used when a fresh
                      REFRESH FORECAST run detects unacked changes.
        modal=False — opened on demand from the SCHEDULE CHANGES button:
                      a normal, non-blocking window the operator can leave
                      open beside the dashboard and revisit any time.
        history     — when supplied (list of daily-diff entries from
                      forecast_changes_history.json), the window renders the
                      full day-by-day 15-day change record instead of just
                      today's single diff. `changes` is still used as the
                      fallback / "today" entry if history is empty.
        reopen_owner — the Forecast15DayPanel; when set, the ⟳ RELOAD button
                      re-reads the history files (picking up hourly-refresh
                      updates) by reopening the window.
        """
        super().__init__(parent)
        self._modal = modal
        self._reopen_owner = reopen_owner
        self._has_history = bool(history)
        title = ("Forecast changes — schedule differs from the previous run"
                 if modal else
                 "Schedule Changes — 15-day day-by-day modification history")
        self.title(title)
        self.configure(bg=BG)
        self.geometry("960x620" if self._has_history else "900x560")
        self.minsize(720, 400)
        # transient + lift after mainloop has had a chance to map the parent.
        try:
            parent.update_idletasks()
            w = 960 if self._has_history else 900
            h = 620 if self._has_history else 560
            self.transient(parent)
            x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
            y = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
            self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        except tk.TclError:
            pass

        if self._has_history:
            self._build_history(history, changes)
        else:
            self._build(changes)

        # Force the window above the main one. Defer grab_set until after
        # it is mapped — calling grab_set on an unmapped window is silently
        # no-op on Windows and the window ends up invisible.
        self.after(50, self._present)

    def _present(self):
        try:
            print("[POPUP] _present called")
            self.deiconify()
            self.lift()
            self.focus_force()
            self.attributes("-topmost", True)
            self.after(200, lambda: self.attributes("-topmost", False))
            # Only grab focus when modal — the on-demand SCHEDULE CHANGES
            # window must NOT block the dashboard behind it.
            if self._modal:
                self.grab_set()
            print(f"[POPUP] _present done — modal={self._modal}")
        except Exception as e:
            import traceback
            print(f"[POPUP] _present failed: {e}")
            traceback.print_exc()

    def _build(self, ch: dict):
        # Defensive past-pass filter: forecast_diff already filters at
        # write-time, but the JSON may have been generated hours before this
        # popup opens. Drop any entry whose start time is now in the past so
        # the counters and the list stay justifiable.
        ch = self._filter_past_passes(ch)

        t = ch.get("totals", {})
        compared_to = ch.get("compared_to") or "(no prior run)"
        total_changes = (t.get("new", 0) + t.get("removed", 0)
                         + t.get("shifted", 0))
        zero_changes = total_changes == 0

        # Top banner — different headline when nothing changed
        top = tk.Frame(self, bg=PANEL, pady=14)
        top.pack(fill="x")
        if zero_changes:
            tk.Label(top,
                     text="✓  Refresh complete — schedule is unchanged",
                     font=("Segoe UI", 14, "bold"),
                     bg=PANEL, fg=GREEN).pack(side="left", padx=20)
        else:
            tk.Label(top,
                     text="🔔  Satellite schedule has changed",
                     font=("Segoe UI", 14, "bold"),
                     bg=PANEL, fg=NEON).pack(side="left", padx=20)
        tk.Label(top,
                 text=f"New TLE data fetched today — compared with prior "
                      f"snapshot taken on {compared_to}",
                 font=("Consolas", 10),
                 bg=PANEL, fg=TEXT_DIM).pack(side="right", padx=20)

        # Quick summary strip — natural English instead of cryptic symbols
        sumf = tk.Frame(self, bg=BG3, pady=10)
        sumf.pack(fill="x")
        ind_new = sum(1 for d in ch["days"] for p in d["new_passes"] if p["is_indian"])
        ind_rem = sum(1 for d in ch["days"] for p in d["removed_passes"] if p["is_indian"])
        ind_sft = sum(1 for d in ch["days"] for p in d["shifted_passes"] if p["is_indian"])
        for label, val, color in [
            ("Newly scheduled passes",  t.get("new", 0),                       GREEN),
            ("Previously scheduled, now removed", t.get("removed", 0),          RED),
            ("Existing passes, time changed",     t.get("shifted", 0),          YELLOW),
            ("Total blind-time change (min)",     f"{t.get('blind_delta_min', 0):+.0f}", CYAN),
            ("Indian schedule changes",           f"{ind_new + ind_rem + ind_sft}",      RED),
        ]:
            cell = tk.Frame(sumf, bg=BG3, padx=14)
            cell.pack(side="left")
            tk.Label(cell, text=str(val), font=("Segoe UI", 16, "bold"),
                     bg=BG3, fg=color).pack(anchor="w")
            tk.Label(cell, text=label, font=("Consolas", 8),
                     bg=BG3, fg=TEXT_DIM).pack(anchor="w")

        # ── Scrollable cards (one per change) ─────────────────────────────
        # Treeview rows can't wrap. We instead render each change as a card
        # with chips for date / change-type / sat / country and a wrapped
        # Label for the natural-English explanation. Reads top-to-bottom.
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=12, pady=(10, 0))

        canvas = tk.Canvas(body, bg=BG, highlightthickness=0)
        vsb = ttk.Scrollbar(body, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        cards_holder = tk.Frame(canvas, bg=BG)
        canvas_win = canvas.create_window((0, 0), window=cards_holder, anchor="nw")

        def _on_holder_config(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
        cards_holder.bind("<Configure>", _on_holder_config)

        def _on_canvas_config(event):
            canvas.itemconfigure(canvas_win, width=event.width)
        canvas.bind("<Configure>", _on_canvas_config)

        # Mouse-wheel scroll
        def _on_wheel(event):
            canvas.yview_scroll(int(-event.delta / 120), "units")
        canvas.bind_all("<MouseWheel>", _on_wheel)
        # Unbind on destroy so other widgets keep mousewheel after we close
        def _unbind_wheel(_e):
            try: canvas.unbind_all("<MouseWheel>")
            except tk.TclError: pass
        self.bind("<Destroy>", _unbind_wheel)

        kind_meta = {
            "new":     ("Newly added pass",            GREEN),
            "removed": ("Was scheduled, now removed",  RED),
            "shifted": ("Pass time updated",           YELLOW),
        }

        def fmt_date(d_str: str) -> str:
            try:
                import datetime
                d = datetime.datetime.strptime(d_str, "%Y-%m-%d")
                return d.strftime("%a %d %b")
            except Exception:
                return d_str

        # Build the list of changes — India first, then chronological
        rows = []
        for d in ch["days"]:
            for p in d["new_passes"]:
                tpkt = _utc_to_pkt(p["entry_utc"])[:5]
                explanation = (
                    f"BEFORE: not on this day's schedule   →   "
                    f"NOW: {tpkt} PKT "
                    f"({p['pass_type'].replace('-', ' ')}). "
                    f"Appeared after today's fresh TLE pull."
                )
                rows.append((d["date"], "new", p, explanation))
            for p in d["removed_passes"]:
                tpkt = _utc_to_pkt(p["entry_utc"])[:5]
                explanation = (
                    f"BEFORE: {tpkt} PKT   →   NOW: removed. "
                    f"After today's fresh TLE pull, it is no longer expected "
                    f"to pass over Pakistan on this day."
                )
                rows.append((d["date"], "removed", p, explanation))
            for p in d["shifted_passes"]:
                shift = p["shift_min"]
                direction = "later" if shift > 0 else "earlier"
                y_t = _utc_to_pkt(p["yesterday_entry"])[:5]
                t_t = _utc_to_pkt(p["today_entry"])[:5]
                explanation = (
                    f"BEFORE: {y_t} PKT   →   NOW: {t_t} PKT "
                    f"({abs(shift)} minutes {direction}). "
                    f"Re-timed after today's fresh TLE pull."
                )
                rows.append((d["date"], "shifted", p, explanation))

        rows.sort(key=lambda r: (not r[2]["is_indian"], r[0], r[1]))

        if not rows:
            # Friendly empty-state, especially for "refresh produced no diff"
            empty = tk.Frame(cards_holder, bg=PANEL, pady=24)
            empty.pack(fill="x", padx=4, pady=20)
            tk.Label(empty,
                     text="✓  No schedule changes detected",
                     bg=PANEL, fg=GREEN,
                     font=("Segoe UI", 13, "bold")
                     ).pack(pady=(8, 4))
            tk.Label(empty,
                     text=("Today's freshly-fetched TLEs produce the same "
                           "pass schedule as the prior snapshot. "
                           "No satellites were added, removed, or shifted "
                           "for any of the next 15 days."),
                     bg=PANEL, fg=TEXT_DIM,
                     font=("Segoe UI", 10),
                     wraplength=820, justify="center"
                     ).pack(pady=(0, 14))

        for date_str, kind, p, explanation in rows:
            self._add_change_card(
                cards_holder, fmt_date(date_str), kind, kind_meta,
                p, explanation,
            )

        # Footer with explanatory caption + OK button
        ftr = tk.Frame(self, bg=BG, pady=14)
        ftr.pack(fill="x", padx=12)
        tk.Label(
            ftr,
            text=("Source: today's fresh TLEs from celestrak.org vs the "
                  "snapshot saved before this run. Indian satellites are "
                  "highlighted in red."),
            font=("Consolas", 9), bg=BG, fg=TEXT_DIM, justify="left"
        ).pack(side="left")
        FlatBtn(ftr, "✓  OK, GOT IT",
                self._dismiss, bg=ACCENT, fg="#fff",
                hover_bg=NEON, hover_fg=BG,
                font=("Segoe UI", 10, "bold"), padx=18, pady=8
                ).pack(side="right")

        self.bind("<Escape>", lambda e: self._dismiss())
        self._generated_at = ch.get("generated_at", "")

    # ── Shared row-builder ─────────────────────────────────────────────────
    @staticmethod
    def _rows_from_changes(ch: dict) -> list[tuple]:
        """Flatten a changes dict into (target_date, kind, pass, explanation)
        tuples. Used by the day-by-day history view (and could back _build
        too). India-first, then chronological."""
        rows: list[tuple] = []
        for d in ch.get("days", []):
            for p in d.get("new_passes", []):
                tpkt = _utc_to_pkt(p["entry_utc"])[:5]
                rows.append((d["date"], "new", p,
                    f"BEFORE: not on this day's schedule   →   "
                    f"NOW: {tpkt} PKT ({p['pass_type'].replace('-', ' ')})."))
            for p in d.get("removed_passes", []):
                tpkt = _utc_to_pkt(p["entry_utc"])[:5]
                rows.append((d["date"], "removed", p,
                    f"BEFORE: {tpkt} PKT   →   NOW: removed — no longer "
                    f"expected to pass over Pakistan on this day."))
            for p in d.get("shifted_passes", []):
                shift = p.get("shift_min", 0)
                direction = "later" if shift > 0 else "earlier"
                y_t = _utc_to_pkt(p["yesterday_entry"])[:5]
                t_t = _utc_to_pkt(p["today_entry"])[:5]
                rows.append((d["date"], "shifted", p,
                    f"BEFORE: {y_t} PKT   →   NOW: {t_t} PKT "
                    f"({abs(shift)} min {direction})."))
        rows.sort(key=lambda r: (not r[2].get("is_indian"), r[0], r[1]))
        return rows

    # ── 15-day day-by-day history view (SCHEDULE CHANGES button) ───────────
    def _build_history(self, history: list, today_changes: dict):
        """Render the rolling 15-day change record inside two country tabs —
        Indian satellites and other-country satellites — one section per
        run-day, newest first. `history` is the list from
        forecast_changes_history.json; `today_changes` is the live
        forecast_changes.json used only as a fallback if history is empty."""
        import datetime as _dt

        # Newest run-day first.
        hist = sorted(history, key=lambda h: h.get("run_date", ""), reverse=True)
        if not hist and today_changes:
            hist = [{
                "run_date":     (today_changes.get("generated_at", "") or "")[:10],
                "generated_at": today_changes.get("generated_at"),
                "compared_to":  today_changes.get("compared_to"),
                "totals":       today_changes.get("totals", {}),
                "days":         today_changes.get("days", []),
                "methodology_mismatch": today_changes.get("methodology_mismatch", False),
                "methodology_prev":     today_changes.get("methodology_prev"),
                "methodology_curr":     today_changes.get("methodology_curr"),
            }]
        window = (f"{hist[-1]['run_date']} .. {hist[0]['run_date']}"
                  if hist else "(no history yet)")

        # ── Top banner ────────────────────────────────────────────────────
        top = tk.Frame(self, bg=PANEL, pady=14)
        top.pack(fill="x")
        tk.Label(top, text="🗓  Schedule Change History",
                 font=("Segoe UI", 14, "bold"),
                 bg=PANEL, fg=NEON).pack(side="left", padx=20)
        tk.Label(top,
                 text=f"{len(hist)} day(s) retained   ·   window {window}",
                 font=("Consolas", 10),
                 bg=PANEL, fg=TEXT_DIM).pack(side="right", padx=20)

        # ── Country tabs ──────────────────────────────────────────────────
        # One tab for Indian satellites, one for every other country, so the
        # operator can isolate the threat-relevant feed from the rest.
        try:
            style = ttk.Style(self)
            style.configure("Changes.TNotebook", background=BG, borderwidth=0)
            style.configure("Changes.TNotebook.Tab",
                            background=BG3, foreground=TEXT_DIM,
                            padding=(20, 9), font=("Segoe UI", 10, "bold"))
            style.map("Changes.TNotebook.Tab",
                      background=[("selected", PANEL)],
                      foreground=[("selected", NEON)])
        except tk.TclError:
            pass
        nb = ttk.Notebook(self, style="Changes.TNotebook")
        nb.pack(fill="both", expand=True, padx=8, pady=(8, 0))
        india_tab = tk.Frame(nb, bg=BG)
        other_tab = tk.Frame(nb, bg=BG)
        nb.add(india_tab, text="   INDIAN SATELLITES   ")
        nb.add(other_tab, text="   OTHER COUNTRIES   ")
        self._build_history_tab(india_tab, hist, "india")
        self._build_history_tab(other_tab, hist, "other")

        # ── Footer ────────────────────────────────────────────────────────
        ftr = tk.Frame(self, bg=BG, pady=14)
        ftr.pack(fill="x", padx=12)
        tk.Label(
            ftr,
            text=("Rolling 15-day record from forecast_changes_history.json — "
                  "refreshed hourly + by every daily run. Backed up under "
                  "backups/<date>/. ⟳ RELOAD picks up the latest hourly "
                  "update. Indian satellites highlighted in red."),
            font=("Consolas", 9), bg=BG, fg=TEXT_DIM, justify="left",
            wraplength=620
        ).pack(side="left")
        FlatBtn(ftr, "✓  CLOSE",
                self._dismiss, bg=ACCENT, fg="#fff",
                hover_bg=NEON, hover_fg=BG,
                font=("Segoe UI", 10, "bold"), padx=18, pady=8
                ).pack(side="right")
        # ⟳ RELOAD — re-read the history files so the operator sees the
        # latest hourly-refresh data without closing/reopening the window.
        if self._reopen_owner is not None:
            FlatBtn(ftr, "⟳  RELOAD",
                    self._reload_via_owner, bg=BG3, fg=NEON,
                    hover_bg=NEON, hover_fg=BG,
                    font=("Segoe UI", 10, "bold"), padx=18, pady=8
                    ).pack(side="right", padx=(0, 8))
        self.bind("<Escape>", lambda e: self._dismiss())
        self._generated_at = (today_changes or {}).get("generated_at", "")

    def _build_history_tab(self, parent, hist: list, country: str):
        """Render the day-by-day change sections for ONE country filter into
        `parent`. `country` is 'india' (Indian sats only) or 'other' (every
        non-Indian sat). Each tab carries its own filtered summary strip."""
        import datetime as _dt

        kind_meta = {
            "new":     ("Newly added pass",            GREEN),
            "removed": ("Was scheduled, now removed",  RED),
            "shifted": ("Pass time updated",           YELLOW),
        }

        def fmt_date(d_str: str) -> str:
            try:
                return _dt.datetime.strptime(d_str, "%Y-%m-%d").strftime("%a %d %b")
            except Exception:
                return d_str

        def keep(p: dict) -> bool:
            is_ind = bool(p.get("is_indian"))
            return is_ind if country == "india" else not is_ind

        # Pre-filter each day's rows once; tally the filtered aggregate.
        # Methodology-mismatch days are EXCLUDED from the aggregate — their
        # rows are code-upgrade artefacts, not real schedule movement.
        per_day_rows: dict[str, list] = {}
        agg = {"new": 0, "removed": 0, "shifted": 0}
        for entry in hist:
            rows = [r for r in self._rows_from_changes(entry) if keep(r[2])]
            per_day_rows[entry.get("run_date", "?")] = rows
            if entry.get("methodology_mismatch"):
                continue
            for _d, kind, _p, _e in rows:
                if kind in agg:
                    agg[kind] += 1

        # ── Filtered summary strip ────────────────────────────────────────
        sumf = tk.Frame(parent, bg=BG3, pady=10)
        sumf.pack(fill="x")
        for label, val, color in [
            ("Days on record",          len(hist),         CYAN),
            ("Newly scheduled",         agg["new"],        GREEN),
            ("Removed",                 agg["removed"],    RED),
            ("Time-shifted",            agg["shifted"],    YELLOW),
            ("Total modifications",     sum(agg.values()), NEON),
        ]:
            cell = tk.Frame(sumf, bg=BG3, padx=14)
            cell.pack(side="left")
            tk.Label(cell, text=str(val), font=("Segoe UI", 16, "bold"),
                     bg=BG3, fg=color).pack(anchor="w")
            tk.Label(cell, text=label, font=("Consolas", 8),
                     bg=BG3, fg=TEXT_DIM).pack(anchor="w")

        # ── Scrollable day-by-day sections ────────────────────────────────
        body = tk.Frame(parent, bg=BG)
        body.pack(fill="both", expand=True, padx=4, pady=(10, 0))
        canvas = tk.Canvas(body, bg=BG, highlightthickness=0)
        vsb = ttk.Scrollbar(body, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        holder = tk.Frame(canvas, bg=BG)
        canvas_win = canvas.create_window((0, 0), window=holder, anchor="nw")
        holder.bind("<Configure>",
                    lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfigure(canvas_win, width=e.width))
        def _on_wheel(event):
            canvas.yview_scroll(int(-event.delta / 120), "units")
        # Bind the wheel only while the pointer is over THIS tab's canvas —
        # two notebook tabs each own a canvas, so a global bind would fight.
        canvas.bind("<Enter>",
                    lambda e: canvas.bind_all("<MouseWheel>", _on_wheel))
        canvas.bind("<Leave>",
                    lambda e: canvas.unbind_all("<MouseWheel>"))
        def _unbind_wheel(_e):
            try: canvas.unbind_all("<MouseWheel>")
            except tk.TclError: pass
        self.bind("<Destroy>", _unbind_wheel, add="+")

        scope_lbl = "Indian" if country == "india" else "other-country"

        # One section per run-day, counts re-derived from the filtered rows.
        for entry in hist:
            run_date = entry.get("run_date", "?")
            rows = per_day_rows.get(run_date, [])
            n_new = sum(1 for r in rows if r[1] == "new")
            n_rem = sum(1 for r in rows if r[1] == "removed")
            n_sft = sum(1 for r in rows if r[1] == "shifted")
            n_all = len(rows)

            mismatch = entry.get("methodology_mismatch", False)
            # Newest entry whose run_date is today = the live/present day.
            is_today = (run_date == _dt.date.today().strftime("%Y-%m-%d"))

            # Day-section header bar
            hdr = tk.Frame(holder, bg=BG3)
            hdr.pack(fill="x", padx=4, pady=(10, 0))
            day_color = (AMBER if mismatch
                         else GREEN if n_all == 0
                         else NEON)
            label_txt = f"  {fmt_date(run_date)}  ·  {run_date}"
            if is_today:
                label_txt += "   ● TODAY · LIVE"
            tk.Label(hdr, text=label_txt,
                     bg=BG3, fg=(CYAN if is_today else day_color),
                     font=("Segoe UI", 11, "bold")).pack(side="left", pady=6)
            tk.Label(hdr,
                     text=(f"+{n_new} new   −{n_rem} removed   ~{n_sft} shifted   "
                           f"·  vs {entry.get('compared_to') or '(no baseline)'}  "),
                     bg=BG3, fg=TEXT_DIM,
                     font=("Consolas", 9)).pack(side="right", pady=6)

            # Methodology-transition banner: on the day the per-sat standoff
            # classifier shipped, the diff shows a huge "+N new" that is the
            # code upgrade (SAR sats becoming visible), NOT real schedule
            # movement. Make that unmistakable so the operator doesn't read
            # it as an actual surge of new satellite activity.
            if mismatch:
                warn = tk.Frame(holder, bg=PANEL)
                warn.pack(fill="x", padx=4, pady=(2, 0))
                tk.Label(warn,
                         text=("   ⚠  Methodology change this day "
                               f"({entry.get('methodology_prev','v1')} → "
                               f"{entry.get('methodology_curr','v2')}): the "
                               "tilt-standoff classifier was upgraded. The "
                               f"+{n_new} / −{n_rem} / ~{n_sft} {scope_lbl} "
                               "counts above are SAR/extra-tilt passes that "
                               "became visible because of the code change — "
                               "NOT a real surge in scheduled activity. "
                               "Per-pass cards are suppressed for this day; "
                               "this day is also left out of the tab totals "
                               "above."),
                         bg=PANEL, fg=AMBER, anchor="w", justify="left",
                         font=("Segoe UI", 9), wraplength=860
                         ).pack(fill="x", pady=8, padx=10)
                # Skip the artefact cards — the banner says it all.
                continue

            if n_all == 0:
                line = tk.Frame(holder, bg=PANEL)
                line.pack(fill="x", padx=4, pady=(2, 0))
                tk.Label(line,
                         text=(f"   ✓  No {scope_lbl} satellite modifications "
                               "this day."),
                         bg=PANEL, fg=TEXT_DIM, anchor="w",
                         font=("Segoe UI", 10)).pack(fill="x", pady=8, padx=10)
                continue

            for date_str, kind, p, explanation in rows:
                self._add_change_card(holder, fmt_date(date_str), kind,
                                      kind_meta, p, explanation)

    def _reload_via_owner(self):
        """Re-open the Schedule Changes window from fresh files. Cleanest
        way to pick up hourly-refresh updates — the owner re-reads
        forecast_changes_history.json and builds a new window; we then
        close this stale one."""
        owner = self._reopen_owner
        try:
            self.destroy()
        finally:
            if owner is not None and hasattr(owner, "_open_schedule_changes"):
                owner._open_schedule_changes()

    def _add_change_card(self, parent, date_lbl, kind, kind_meta,
                         pass_dict, explanation: str):
        """
        One card per schedule change. Top row: date chip, change-type label,
        satellite + country. Below: full natural-English explanation that
        wraps to as many lines as needed.
        """
        kind_text, kind_color = kind_meta[kind]
        is_indian = pass_dict["is_indian"]
        name_color = RED if is_indian else TEXT

        card_outer = tk.Frame(parent, bg=BG)
        card_outer.pack(fill="x", padx=4, pady=4)

        # Left accent bar shows urgency (red for India, kind-color otherwise)
        accent = tk.Frame(card_outer, bg=RED if is_indian else kind_color,
                          width=4)
        accent.pack(side="left", fill="y")

        card = tk.Frame(card_outer, bg=PANEL)
        card.pack(side="left", fill="x", expand=True, padx=(0, 0))

        # Top row inside the card
        top = tk.Frame(card, bg=PANEL)
        top.pack(fill="x", padx=14, pady=(10, 4))

        # Date chip
        date_chip = tk.Label(top, text=f" {date_lbl} ",
                             bg=BG3, fg=CYAN,
                             font=("Consolas", 9, "bold"),
                             padx=8, pady=3)
        date_chip.pack(side="left")

        # Change-type label
        tk.Label(top, text=f"  {kind_text}",
                 bg=PANEL, fg=kind_color,
                 font=("Segoe UI", 10, "bold")
                 ).pack(side="left")

        # Right side: satellite + country
        right_top = tk.Frame(top, bg=PANEL)
        right_top.pack(side="right")
        country_prefix = "🇮🇳  " if is_indian else ""
        tk.Label(right_top,
                 text=f"{country_prefix}{pass_dict['name']}",
                 bg=PANEL, fg=name_color,
                 font=("Segoe UI", 10, "bold")).pack(side="left")
        tk.Label(right_top,
                 text=f"   ·  {pass_dict['country']}",
                 bg=PANEL, fg=TEXT_DIM,
                 font=("Consolas", 9)).pack(side="left")

        # Wrapped explanation — re-wraps when the card's width changes
        exp_lbl = tk.Label(card,
                           text=explanation,
                           bg=PANEL, fg=TEXT,
                           font=("Segoe UI", 10),
                           justify="left", anchor="w",
                           wraplength=820)
        exp_lbl.pack(fill="x", padx=14, pady=(0, 6), anchor="w")

        # ── FEAT-004: ⚠ TARGETS line ────────────────────────────────────
        # For any pass that brings a tier-1 Pakistan strategic site inside
        # the satellite's standoff radius, surface the targeted cities in
        # a bold red warning line. Below it (in a dimmer line) we list any
        # tier-2 sites so the operator gets the full picture without the
        # warning bar becoming a wall of text.
        targets = pass_dict.get("targeted_sites") or []
        tier1 = [t for t in targets if t.get("tier") == 1]
        tier2 = [t for t in targets if t.get("tier") == 2]
        if tier1:
            # Unique cities, ordered by closest approach (list already sorted)
            seen = set(); t1_cities = []
            for t in tier1:
                c = t.get("city")
                if c and c not in seen:
                    seen.add(c)
                    t1_cities.append(c)
            warning = "⚠  TARGETS:  " + " · ".join(t1_cities)
            tk.Label(card,
                     text=warning,
                     bg=PANEL, fg=RED,
                     font=("Segoe UI", 10, "bold"),
                     justify="left", anchor="w",
                     wraplength=820
                     ).pack(fill="x", padx=14, pady=(0, 2), anchor="w")
        if tier2:
            seen = set(); t2_cities = []
            for t in tier2:
                c = t.get("city")
                if c and c not in seen:
                    seen.add(c)
                    t2_cities.append(c)
            secondary = "   secondary: " + ", ".join(t2_cities)
            tk.Label(card,
                     text=secondary,
                     bg=PANEL, fg=AMBER,
                     font=("Consolas", 9),
                     justify="left", anchor="w",
                     wraplength=820
                     ).pack(fill="x", padx=14, pady=(0, 2), anchor="w")

        # Bottom padding (kept after target lines so spacing is consistent
        # whether targets are present or not).
        tk.Frame(card, bg=PANEL, height=6).pack(fill="x")

        def _rewrap(event, lbl=exp_lbl):
            new_w = max(200, event.width - 60)  # padding + accent
            lbl.config(wraplength=new_w)
        card.bind("<Configure>", _rewrap)

    def _dismiss(self):
        # Record that this exact diff version has been acked.
        try:
            ack_path = os.path.join(SAT_DIR, ".changes_acked")
            with open(ack_path, "w", encoding="utf-8") as f:
                f.write(self._generated_at)
        except OSError:
            pass
        self.destroy()


# ── HiRes EO 15-Day Forecast Panel ─────────────────────────────────────────────
class Forecast15DayPanel(tk.Frame):
    """
    Surfaces Satellite_Tracker/forecast_15day.json — the rolling 15-day
    HiRes EO forecast plus daily blind windows. The user can also trigger
    `run_daily.py` from here to refresh the forecast.
    """

    SUBTITLE = ("HiRes EO Pakistan-airspace forecast · 15-day window · "
                "Daily blind windows · ISRO sats in red")
    COLOR    = NEON

    def __init__(self, parent, **kw):
        super().__init__(parent, bg=BG, **kw)
        self._proc      = None
        self._running   = False
        self._seconds   = 0
        self._timer_id  = None
        self._lines     = 0
        self._row_alt   = False
        self._pulse_id  = None
        self._pulse_color = None
        self._pulse_on  = False
        self._forecast  = None
        self.forecast_json = os.path.join(SAT_DIR, "forecast_15day.json")
        self.run_script    = os.path.join(SAT_DIR, "run_daily.py")
        self.hourly_script = os.path.join(SAT_DIR, "run_hourly.py")
        self.docs_dir      = os.path.join(SAT_DIR, "documents")
        # Hourly TLE auto-refresh state. The timer fires run_hourly.py in a
        # background thread every HOURLY_REFRESH_MS so the forecast + change
        # history never lag CelesTrak by more than ~1 hour, even if nobody
        # touches the dashboard.
        self.HOURLY_REFRESH_MS = 60 * 60 * 1000      # 1 hour
        self._hourly_enabled   = True
        self._hourly_timer_id  = None
        self._hourly_running   = False
        self._hourly_last_run  = None
        # Live "now" playhead state (the cyan line creeping across today's
        # row + the live coverage chip). Geometry is filled by the calendar
        # / timeline renderers; the 1-second timer redraws the marker.
        self._live_timer_id    = None
        self._cal_geom         = None
        self._tl_geom          = None
        self._build()
        # First load is silent — the popup is fired by <Map> handler once
        # the main window is actually on screen.
        self._reload_from_disk(popup_if_new=False)
        # Kick off the hourly auto-refresh loop (first tick one interval out;
        # the panel already loaded current data above).
        self._schedule_hourly_refresh()
        # Start the 1-second live-playhead loop.
        self._tick_live_marker()

    def _apply_dark_treeview_style(self):
        """Style ttk.Treeview to match the rest of the dark UI."""
        style = ttk.Style(self)
        try:
            style.theme_use("clam")  # only built-in theme that lets us recolor headings
        except tk.TclError:
            pass
        style.configure("Forecast.Treeview",
                        background=BG2, foreground=TEXT,
                        fieldbackground=BG2, bordercolor=BORDER,
                        rowheight=24, font=FONT_MONO)
        style.configure("Forecast.Treeview.Heading",
                        background=PANEL, foreground=CYAN,
                        relief="flat", font=("Consolas", 9, "bold"))
        style.map("Forecast.Treeview.Heading",
                  background=[("active", BG3)])
        style.map("Forecast.Treeview",
                  background=[("selected", ACCENT)],
                  foreground=[("selected", "#ffffff")])

    # ── Build UI ───────────────────────────────────────────────────────────
    def _build(self):
        # Dark-theme both Treeviews used in this panel
        self._apply_dark_treeview_style()

        # ── Scrollable container ───────────────────────────────────────────
        # The forecast panel stacks a lot vertically (stats, action bar,
        # daily table, blind calendar, timeline, crossings, telemetry log) —
        # more than fits in most windows. Wrap the whole thing in a canvas
        # so the operator can scroll all the way down to the bottom strip.
        outer = tk.Frame(self, bg=BG)
        outer.pack(fill="both", expand=True)
        self._scroll_canvas = tk.Canvas(outer, bg=BG, highlightthickness=0)
        _vsb = ttk.Scrollbar(outer, orient="vertical",
                             command=self._scroll_canvas.yview)
        self._scroll_canvas.configure(yscrollcommand=_vsb.set)
        self._scroll_canvas.pack(side="left", fill="both", expand=True)
        _vsb.pack(side="right", fill="y")
        content = tk.Frame(self._scroll_canvas, bg=BG)
        _content_win = self._scroll_canvas.create_window(
            (0, 0), window=content, anchor="nw")
        content.bind("<Configure>", lambda e: self._scroll_canvas.configure(
            scrollregion=self._scroll_canvas.bbox("all")))
        self._scroll_canvas.bind("<Configure>",
            lambda e: self._scroll_canvas.itemconfigure(_content_win,
                                                        width=e.width))
        # Mouse-wheel scrolls the outer container, but defers to the inner
        # scrollable widgets (daily table, blind calendar, crossings, log)
        # when the pointer is over them.
        self.bind("<Map>",
                  lambda e: self.bind_all("<MouseWheel>", self._outer_wheel))
        self.bind("<Unmap>",
                  lambda e: self.unbind_all("<MouseWheel>"))

        hdr = tk.Frame(content, bg=PANEL, pady=14)
        hdr.pack(fill="x", pady=(0, 10))
        tk.Label(hdr, text="📅  15-Day HiRes EO Forecast",
                 font=("Segoe UI", 16, "bold"), bg=PANEL, fg=TEXT
                 ).pack(side="left", padx=20)

        right = tk.Frame(hdr, bg=PANEL); right.pack(side="right", padx=20)
        self._status_dot = tk.Label(right, text="●", font=("Segoe UI", 12),
                                    bg=PANEL, fg=TEXT_MUTE)
        self._status_dot.pack(side="left")
        self._status_lbl = tk.Label(right, text="IDLE", font=FONT_MONO,
                                    bg=PANEL, fg=TEXT_MUTE)
        self._status_lbl.pack(side="left", padx=(4, 16))
        self._timer_lbl = tk.Label(right, text="00:00",
                                   font=("Consolas", 18), bg=PANEL, fg=self.COLOR)
        self._timer_lbl.pack(side="left")

        tk.Label(content, text=self.SUBTITLE, font=FONT_SM, bg=BG, fg=TEXT_DIM
                 ).pack(anchor="w", padx=20, pady=(0, 8))

        # ── Stats row — 4 cards with sub-breakdown text ────────────────────
        stats_row = tk.Frame(content, bg=BG)
        stats_row.pack(fill="x", padx=20, pady=(0, 8))
        self._stat_sats   = self._stat_card2(stats_row, "Satellites tracked",
                                             "0", "Optical + SAR + Military fleet",
                                             CYAN)
        self._stat_india  = self._stat_card2(stats_row, "🇮🇳 India passes (15d)",
                                             "0", "0 overhead   0 tilt-range", RED)
        self._stat_sar    = self._stat_card2(stats_row, "📡 SAR passes (15d)",
                                             "0", "0 SAR  ·  0 Military  (day/night)",
                                             "#a855f7")
        self._stat_other  = self._stat_card2(stats_row, "Other countries (15d)",
                                             "0", "0 overhead   0 tilt-range", GREEN)
        self._stat_blind  = self._stat_card2(stats_row, "Blind time (15d)",
                                             "0 h", "of 360 h total — Pakistan unobserved",
                                             YELLOW)

        # Action bar
        act = tk.Frame(content, bg=BG); act.pack(fill="x", padx=20, pady=(0, 8))
        self._btn_refresh = FlatBtn(act, "⟳  REFRESH FORECAST", self._refresh,
                                    bg=BG3, fg=self.COLOR,
                                    hover_bg=self.COLOR, hover_fg=BG)
        self._btn_refresh.pack(side="left", padx=(0, 6))
        self._btn_stop = FlatBtn(act, "■  STOP", self._stop,
                                 bg=BG3, fg=RED, hover_bg=RED, hover_fg="#fff")
        self._btn_stop.set_disabled(True)
        self._btn_stop.pack(side="left", padx=(0, 6))
        FlatBtn(act, "[>] OPEN WORD REPORT", self._open_report,
                bg=BG3, fg=TEXT, hover_fg=self.COLOR).pack(side="left", padx=(0, 6))
        FlatBtn(act, "[J] OPEN JSON", self._open_json,
                bg=BG3, fg=TEXT_DIM, hover_fg=self.COLOR).pack(side="left", padx=(0, 6))
        FlatBtn(act, "↻  RE-READ JSON (no recompute)", self._reload_from_disk,
                bg=BG3, fg=TEXT_DIM, hover_fg=self.COLOR).pack(side="left", padx=(0, 6))
        FlatBtn(act, "✔  ACCURACY CHECK", self._run_accuracy_check,
                bg=BG3, fg=YELLOW, hover_bg=YELLOW, hover_fg=BG).pack(side="left", padx=(0, 6))
        FlatBtn(act, "⇄  SCHEDULE CHANGES", self._open_schedule_changes,
                bg=BG3, fg=NEON, hover_bg=NEON, hover_fg=BG).pack(side="left", padx=(0, 6))
        FlatBtn(act, "⏱  AUTO TLE", self._toggle_hourly,
                bg=BG3, fg=NEON, hover_bg=NEON, hover_fg=BG).pack(side="left", padx=(0, 6))
        FlatBtn(act, "[X] CLEAR LOG", self._clear_log,
                bg=BG3, fg=TEXT_MUTE, hover_fg=RED).pack(side="right")
        # Hourly auto-refresh status chip — updated by _update_hourly_label.
        self._hourly_lbl = tk.Label(act, text="⏱ Auto TLE: hourly · last —",
                                    font=("Consolas", 9), bg=BG, fg=NEON)
        self._hourly_lbl.pack(side="right", padx=(0, 12))

        # Generated-at strip
        meta_frame = tk.Frame(content, bg=BG3, pady=8)
        meta_frame.pack(fill="x", padx=20, pady=(0, 6))
        self._meta_lbl = tk.Label(
            meta_frame, text="Forecast: not yet generated", font=FONT_MONO,
            bg=BG3, fg=TEXT_DIM
        )
        self._meta_lbl.pack(side="left", padx=10)

        # ── "Changes since yesterday" banner ──────────────────────────────
        ch_frame = tk.Frame(content, bg="#1a1f33", pady=8)
        ch_frame.pack(fill="x", padx=20, pady=(0, 10))
        tk.Label(ch_frame, text="🔔  CHANGES SINCE LAST RUN",
                 font=("Consolas", 9, "bold"),
                 bg="#1a1f33", fg=NEON).pack(side="left", padx=10)
        self._changes_lbl = tk.Label(
            ch_frame,
            text="No prior forecast to compare yet.",
            font=("Consolas", 10), bg="#1a1f33", fg=TEXT_DIM,
            wraplength=1100, justify="left"
        )
        self._changes_lbl.pack(side="left", padx=10, fill="x", expand=True)

        # ── Body: stacked — daily table, timeline strip, day details, log ──
        body = tk.Frame(content, bg=BG)
        body.pack(fill="both", expand=True, padx=20, pady=(0, 16))

        # TOP: daily summary table
        top = tk.Frame(body, bg=BG2)
        top.pack(fill="x")
        tk.Label(top, text=">> DAILY FORECAST  ·  click a row to view its 24-h timeline",
                 font=FONT_MONO, bg=PANEL, fg=self.COLOR, pady=6,
                 anchor="w", padx=12).pack(fill="x")
        cols = ("date", "ind_oh", "ind_tilt", "oth_oh", "oth_tilt",
                "sats", "blind", "longest")
        self._tree = ttk.Treeview(top, columns=cols, show="headings", height=8,
                                  style="Forecast.Treeview")
        for col, label, w in [
            ("date",     "Date",            100),
            ("ind_oh",   "🇮🇳 Over",        80),
            ("ind_tilt", "🇮🇳 Tilt",        80),
            ("oth_oh",   "Other Over",      100),
            ("oth_tilt", "Other Tilt",      100),
            ("sats",     "Sats",            60),
            ("blind",    "Blind (min)",     110),
            ("longest",  "Longest gap (min)", 130),
        ]:
            self._tree.heading(col, text=label)
            self._tree.column(col, width=w, anchor="center")
        sb = ttk.Scrollbar(top, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side="left", fill="x", expand=True)
        sb.pack(side="right", fill="y")
        self._tree.tag_configure("indian_heavy", foreground=RED)
        self._tree.tag_configure("blind_heavy",  foreground=YELLOW)
        # Optical/SAR sub-row styling — cyan for visible-light, violet for radar.
        # These rows show the per-sensor breakdown below each date's total row.
        self._tree.tag_configure("optical_row", foreground=CYAN)
        self._tree.tag_configure("sar_row",     foreground=MAGENTA)
        self._tree.bind("<<TreeviewSelect>>", self._on_day_select)

        # ── 15-DAY BLIND CALENDAR (all days at a glance) ──────────────────
        cal_frame = tk.Frame(body, bg=PANEL)
        cal_frame.pack(fill="x", pady=(10, 0))
        cal_hdr = tk.Frame(cal_frame, bg=PANEL)
        cal_hdr.pack(fill="x")
        tk.Label(cal_hdr,
                 text=">> 15-DAY BLIND CALENDAR  ·  green=observed  red=blind  ▐India  ▐purple=SAR  ▐red=Military"
                      "  ·  hover=details  dbl-click=full popup",
                 font=FONT_MONO, bg=PANEL, fg=self.COLOR, pady=6, padx=12,
                 anchor="w").pack(side="left")
        # Live "is a satellite over us RIGHT NOW" chip — refreshed every
        # second by _tick_live_marker(), in step with the cyan playhead that
        # moves across today's row.
        self._live_chip = tk.Label(
            cal_hdr, text="◌ LIVE  —  initialising…",
            font=("Consolas", 9, "bold"), bg=PANEL, fg=TEXT_MUTE,
            pady=6, padx=12, anchor="e")
        self._live_chip.pack(side="right")
        cal_inner = tk.Frame(cal_frame, bg=BG)
        cal_inner.pack(fill="x", padx=12, pady=(0, 8))
        # Show ~8 rows at a time; scroll to see all 15
        VISIBLE_ROWS = 8
        cal_h = 18 + VISIBLE_ROWS * 22 + 4
        self._cal_canvas = tk.Canvas(cal_inner, bg=BG, highlightthickness=0,
                                     height=cal_h)
        cal_vsb = ttk.Scrollbar(cal_inner, orient="vertical",
                                command=self._cal_canvas.yview)
        self._cal_canvas.configure(yscrollcommand=cal_vsb.set)
        self._cal_canvas.pack(side="left", fill="x", expand=True)
        cal_vsb.pack(side="right", fill="y")
        self._cal_canvas.bind("<Configure>", lambda e: self._render_blind_calendar())
        self._cal_canvas.bind("<Button-1>",  self._cal_click)
        self._cal_canvas.bind("<Double-Button-1>", self._cal_dbl_click)
        self._cal_canvas.bind("<Motion>",    self._cal_hover)
        self._cal_canvas.bind("<Leave>",     self._cal_leave)
        # Mouse-wheel scroll on the calendar
        self._cal_canvas.bind("<MouseWheel>",
            lambda e: self._cal_canvas.yview_scroll(-1 if e.delta > 0 else 1, "units"))
        # Hit regions built during _render_blind_calendar:
        #   list of (x0, x1, y_top, y_bot, kind, data_dict)
        self._cal_hit_regions: list = []
        # Tooltip window
        self._cal_tooltip: tk.Toplevel | None = None

        # ── 24-h TIMELINE for the selected day (visual ribbon) ─────────────
        tl_frame = tk.Frame(body, bg=PANEL)
        tl_frame.pack(fill="x", pady=(10, 0))
        self._tl_title = tk.Label(
            tl_frame, text=">> SELECTED DAY  ·  24-HR TIMELINE  (PKT = UTC+5)",
            font=FONT_MONO, bg=PANEL, fg=self.COLOR, pady=6, padx=12,
            anchor="w"
        )
        self._tl_title.pack(fill="x")
        self._timeline = tk.Canvas(
            tl_frame, bg=BG, highlightthickness=0, height=72
        )
        self._timeline.pack(fill="x", padx=12, pady=(0, 8))
        self._timeline.bind("<Configure>", lambda e: self._render_timeline())

        # Legend strip under the timeline
        leg = tk.Frame(tl_frame, bg=PANEL); leg.pack(fill="x", padx=12, pady=(0, 8))
        for sw, txt, col in [
            ("■", "Pakistan observed", GREEN),
            ("■", "Blind (no satellite)", "#2a2a3f"),
            ("▬", "🇮🇳 India crossing", RED),
            ("▬", "Other crossing", CYAN),
            ("▬", "Tilt-range only", AMBER),
        ]:
            tk.Label(leg, text=f"  {sw} {txt}", font=("Consolas", 9),
                     bg=PANEL, fg=col).pack(side="left")

        # ── Selected-day crossings list ───────────────────────────────────
        det = tk.Frame(body, bg=BG2)
        det.pack(fill="both", expand=True, pady=(10, 0))
        self._det_title = tk.Label(
            det, text=">> CROSSINGS ON SELECTED DAY",
            font=FONT_MONO, bg=PANEL, fg=self.COLOR, pady=6, padx=12,
            anchor="w"
        )
        self._det_title.pack(fill="x")
        det_cols = ("time", "type", "sat", "country", "sensor",
                    "off_km", "dur", "dir")
        self._det = ttk.Treeview(det, columns=det_cols, show="headings", height=8,
                                 style="Forecast.Treeview")
        for col, label, w, anchor in [
            ("time",    "PKT time",        110, "center"),
            ("type",    "Pass",             80, "center"),
            ("sat",     "Satellite",       180, "w"),
            ("country", "Country",         110, "w"),
            ("sensor",  "Sensor",          130, "w"),
            ("off_km",  "Off-nadir (km)",  120, "center"),
            ("dur",     "Duration (min)",  120, "center"),
            ("dir",     "Direction",        90, "center"),
        ]:
            self._det.heading(col, text=label)
            self._det.column(col, width=w, anchor=anchor)
        dsb = ttk.Scrollbar(det, orient="vertical", command=self._det.yview)
        self._det.configure(yscrollcommand=dsb.set)
        self._det.pack(side="left", fill="both", expand=True)
        dsb.pack(side="right", fill="y")
        self._det.tag_configure("indian",     foreground=RED)
        self._det.tag_configure("tilt",       foreground=AMBER)
        self._det.tag_configure("sar",        foreground="#a855f7")
        self._det.tag_configure("military",   foreground="#ef4444")

        # ── Compact telemetry log at the very bottom ───────────────────────
        log_frame = tk.Frame(body, bg=BG2)
        log_frame.pack(fill="x", pady=(10, 0))
        tk.Label(log_frame, text=">> TELEMETRY",
                 font=FONT_MONO, bg=PANEL, fg=self.COLOR,
                 pady=4, padx=12, anchor="w").pack(fill="x")
        self._log = tk.Text(log_frame, bg=BG, fg=TEXT_DIM,
                            font=FONT_MONO, relief="flat", bd=0,
                            state="disabled", wrap="word", padx=10, pady=4,
                            height=5)
        lsb = ttk.Scrollbar(log_frame, command=self._log.yview)
        self._log.config(yscrollcommand=lsb.set)
        lsb.pack(side="right", fill="y")
        self._log.pack(fill="both", expand=True)
        for tag, color in [
            ("match", GREEN), ("error", RED), ("info", CYAN),
            ("warn", YELLOW), ("done", NEON), ("default", TEXT_DIM),
            ("ts", TEXT_MUTE),
        ]:
            self._log.tag_config(tag, foreground=color)

        # Currently selected date for timeline / detail (set after reload)
        self._selected_date: str | None = None

    def _outer_wheel(self, e):
        """Scroll the whole forecast panel on mouse-wheel — but yield to the
        inner scrollable widgets (daily table, blind calendar, crossings
        list, telemetry log) when the pointer is over one of them, so their
        own wheel scrolling still works."""
        cv = getattr(self, "_scroll_canvas", None)
        if cv is None:
            return
        skip = tuple(w for w in (getattr(self, "_cal_canvas", None),
                                 getattr(self, "_tree", None),
                                 getattr(self, "_det", None),
                                 getattr(self, "_log", None)) if w is not None)
        node = self.winfo_containing(e.x_root, e.y_root)
        while node is not None:
            if node in skip:
                return
            try:
                node = node.master
            except AttributeError:
                break
        cv.yview_scroll(int(-e.delta / 120), "units")

    def _stat_card(self, parent, label, color):
        outer = tk.Frame(parent, bg=color)
        outer.pack(side="left", padx=(0, 8), fill="x", expand=True)
        tk.Frame(outer, bg=color, height=2).pack(fill="x")
        f = tk.Frame(outer, bg=PANEL, padx=14, pady=10)
        f.pack(fill="both", expand=True)
        val = tk.Label(f, text="0", font=("Segoe UI", 24, "bold"),
                       bg=PANEL, fg=color)
        val.pack(anchor="w")
        tk.Label(f, text=label, font=("Consolas", 8, "bold"),
                 bg=PANEL, fg=TEXT_DIM).pack(anchor="w", pady=(2, 0))
        return val

    def _stat_card2(self, parent, label, value, sub, color):
        """Larger 3-row stat card: label / big-value / smaller breakdown."""
        outer = tk.Frame(parent, bg=color)
        outer.pack(side="left", padx=(0, 8), fill="x", expand=True)
        tk.Frame(outer, bg=color, height=2).pack(fill="x")
        f = tk.Frame(outer, bg=PANEL, padx=16, pady=12)
        f.pack(fill="both", expand=True)
        tk.Label(f, text=label, font=("Segoe UI", 9, "bold"),
                 bg=PANEL, fg=color, anchor="w"
                 ).pack(anchor="w")
        val = tk.Label(f, text=value, font=("Segoe UI", 28, "bold"),
                       bg=PANEL, fg=TEXT)
        val.pack(anchor="w", pady=(2, 2))
        sub_lbl = tk.Label(f, text=sub, font=("Consolas", 9),
                           bg=PANEL, fg=TEXT_DIM, anchor="w")
        sub_lbl.pack(anchor="w")
        return (val, sub_lbl)

    # ── Actions ────────────────────────────────────────────────────────────
    def _run(self):
        """Alias so the global 'ENGAGE ALL TRACKERS' button includes us."""
        self._refresh()

    def _terminate_proc(self):
        """Kill the run_daily subprocess if alive. UI state untouched."""
        if self._proc and self._proc.poll() is None:
            try:
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(self._proc.pid)],
                        capture_output=True,
                    )
                else:
                    self._proc.terminate()
            except Exception:
                pass
        self._proc = None

    def _refresh(self):
        # Re-run on every click. Kill an in-flight run_daily first so the
        # button always does something — never silently no-op when _running
        # is stale (e.g. a previous run that errored without resetting state).
        if self._running or self._proc:
            self._terminate_proc()
            if self._timer_id:
                self.after_cancel(self._timer_id)
                self._timer_id = None
            self._append("[Restart] Re-running forecast — terminating previous run.\n", "warn")
        self._running  = True
        self._seconds  = 0
        self._set_status("GENERATING", CYAN)
        self._start_pulse(CYAN)
        self._btn_refresh.set_disabled(True)
        self._btn_stop.set_disabled(False)
        self._append(f"[{datetime.now().strftime('%H:%M:%S')}] "
                     f"Refreshing TLEs + regenerating 15-day forecast...\n", "info")
        self._tick()
        threading.Thread(target=self._worker, daemon=True).start()

    def _stop(self):
        self._terminate_proc()
        self._finish("STOPPED", RED)

    def _worker(self):
        try:
            self._proc = subprocess.Popen(
                [sys.executable, "-u", self.run_script],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                cwd=SAT_DIR, bufsize=1, env=ENV
            )
            for line in self._proc.stdout:
                self._handle_line(line.rstrip("\n"))
            self._proc.wait()
            rc = self._proc.returncode
            if rc == 0:
                self.after(0, lambda: self._finish("COMPLETE", GREEN))
                # User explicitly clicked REFRESH FORECAST — always pop the
                # comparison window so they see what this run produced,
                # even if there are zero schedule changes vs the prior run.
                self.after(0, lambda:
                    self._reload_from_disk(popup_if_new=True, force_popup=True))
            else:
                self.after(0, lambda: self._finish(f"EXIT {rc}", RED))
        except Exception as e:
            self.after(0, lambda: self._finish(f"ERROR: {e}", RED))

    def _handle_line(self, line):
        if not line.strip():
            return
        tag = "default"
        if "[FORECAST]" in line or "[TLE]" in line or "[BACKUP]" in line:
            tag = "info"
        if "[+]" in line:
            tag = "match"
        if "[!]" in line or "FATAL" in line:
            tag = "error"
        if "[DONE]" in line or "wrote" in line:
            tag = "done"
        self.after(0, lambda l=line, t=tag: self._append(l + "\n", t))

    def _finish(self, msg, color):
        self._running = False
        if self._timer_id:
            self.after_cancel(self._timer_id)
            self._timer_id = None
        self._set_status(msg, color)
        self._btn_refresh.set_disabled(False)
        self._btn_stop.set_disabled(True)
        self._append(f"\n-- {msg} --\n", "warn")

    # ── Hourly TLE auto-refresh ────────────────────────────────────────────
    def _schedule_hourly_refresh(self):
        """(Re)arm the hourly auto-refresh timer. Idempotent — cancels any
        pending timer first so toggling on/off can't stack timers."""
        if self._hourly_timer_id is not None:
            try:
                self.after_cancel(self._hourly_timer_id)
            except Exception:
                pass
            self._hourly_timer_id = None
        if self._hourly_enabled:
            self._hourly_timer_id = self.after(
                self.HOURLY_REFRESH_MS, self._hourly_tick)
        self._update_hourly_label()

    def _hourly_tick(self):
        """Timer callback — fire one hourly refresh, then re-arm."""
        self._hourly_timer_id = None
        if self._hourly_enabled:
            self._hourly_refresh()
        self._schedule_hourly_refresh()

    def _toggle_hourly(self):
        """Flip the hourly auto-refresh on/off from the UI button."""
        self._hourly_enabled = not self._hourly_enabled
        state = "ON" if self._hourly_enabled else "OFF"
        self._append(f"[{datetime.now().strftime('%H:%M:%S')}] "
                     f"Hourly TLE auto-refresh: {state}\n", "info")
        self._schedule_hourly_refresh()

    def _hourly_refresh(self):
        """Run run_hourly.py in the background. Unlike the manual REFRESH
        FORECAST button this does NOT block the panel or disable the manual
        controls — it's a quiet background top-up. Skipped if a manual
        refresh or a prior hourly run is still in flight."""
        if self._running or self._hourly_running:
            self._append("[hourly] skipped — a refresh is already running\n",
                         "warn")
            return
        self._hourly_running = True
        self._append(f"[{datetime.now().strftime('%H:%M:%S')}] "
                     f"Hourly TLE refresh starting (background)…\n", "info")
        threading.Thread(target=self._hourly_worker, daemon=True).start()

    def _hourly_worker(self):
        try:
            proc = subprocess.Popen(
                [sys.executable, "-u", self.hourly_script],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                cwd=SAT_DIR, bufsize=1, env=ENV,
            )
            for line in proc.stdout:
                self._handle_line(line.rstrip("\n"))
            proc.wait()
            rc = proc.returncode
            self._hourly_last_run = datetime.now()
            if rc == 0:
                # Reload the panel + history silently — no popup; this is a
                # background top-up, not a user-initiated action.
                self.after(0, lambda: self._reload_from_disk(popup_if_new=False))
                self.after(0, lambda: self._append(
                    f"[{datetime.now().strftime('%H:%M:%S')}] "
                    f"Hourly TLE refresh complete — forecast + change "
                    f"history updated.\n", "done"))
            else:
                self.after(0, lambda: self._append(
                    f"[hourly] run_hourly.py exited {rc}\n", "error"))
        except Exception as e:
            self.after(0, lambda e=e: self._append(
                f"[hourly] error: {e}\n", "error"))
        finally:
            self._hourly_running = False
            self.after(0, self._update_hourly_label)

    def _update_hourly_label(self):
        """Refresh the small auto-refresh status chip in the action bar."""
        if not hasattr(self, "_hourly_lbl"):
            return
        if not self._hourly_enabled:
            self._hourly_lbl.config(text="⏱ Auto TLE: OFF", fg=TEXT_MUTE)
            return
        last = (self._hourly_last_run.strftime("%H:%M")
                if self._hourly_last_run else "—")
        self._hourly_lbl.config(
            text=f"⏱ Auto TLE: hourly · last {last}", fg=NEON)

    def _clear_all_views(self):
        """Reset table, timeline, detail list, stats — leaves the panel
        in a clean 'no data yet' state for cold-start or error fallback."""
        for iid in self._tree.get_children():
            self._tree.delete(iid)
        if hasattr(self, "_det"):
            for iid in self._det.get_children():
                self._det.delete(iid)
        if hasattr(self, "_timeline"):
            self._timeline.delete("all")
        if hasattr(self, "_tl_title"):
            self._tl_title.config(
                text=">> SELECTED DAY  ·  24-HR TIMELINE  (PKT = UTC+5)")
        for stat in (getattr(self, "_stat_sats", None),
                     getattr(self, "_stat_india", None),
                     getattr(self, "_stat_sar",   None),
                     getattr(self, "_stat_other", None),
                     getattr(self, "_stat_blind", None)):
            if stat:
                val, sub = stat
                val.config(text="0")
                sub.config(text="")

    # ── Disk read ──────────────────────────────────────────────────────────
    def _reload_from_disk(self, popup_if_new: bool = True,
                          force_popup: bool = False):
        """
        Re-read forecast_15day.json + forecast_changes.json off disk and
        repopulate every UI surface. Tolerant of transient I/O errors —
        if anything fails we restore the empty state with a helpful message
        rather than leaving the panel in a half-rendered state.

        `force_popup=True` is passed by the REFRESH FORECAST completion
        handler so the comparison popup always appears, even on zero diff.
        """
        import json
        try:
            self._reload_changes_banner(popup_if_new=popup_if_new,
                                        force_popup=force_popup)
        except Exception as e:
            self._append(f"[!] Changes banner reload failed: {e}\n", "error")

        if not os.path.isfile(self.forecast_json):
            self._meta_lbl.config(
                text="Forecast file missing — click REFRESH FORECAST to generate it.")
            self._clear_all_views()
            return
        try:
            with open(self.forecast_json, "r", encoding="utf-8") as f:
                fc = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            self._meta_lbl.config(
                text=f"Forecast file unreadable ({type(e).__name__}) — try REFRESH FORECAST.")
            self._clear_all_views()
            self._append(f"[!] Could not read forecast: {e}\n", "error")
            return
        self._populate_ui(fc)

    def _populate_ui(self, fc: dict):
        """Populate all UI surfaces from a loaded forecast dict."""
        self._forecast = fc

        gen = fc.get("generated_at", "?")
        sd  = fc.get("start_date", "?")
        ed  = fc.get("end_date", "?")
        self._meta_lbl.config(
            text=f"Generated: {gen}     |     Window: {sd}  →  {ed}     "
                 f"|     Propagator: {fc.get('propagator', '?')}"
        )

        days = fc.get("days", [])
        ind_oh_total   = sum(d["totals"].get("indian_overhead",   0) for d in days)
        ind_tilt_total = sum(d["totals"].get("indian_tilt_range", 0) for d in days)
        oth_oh_total   = sum(d["totals"].get("other_overhead",    0) for d in days)
        oth_tilt_total = sum(d["totals"].get("other_tilt_range",  0) for d in days)
        total_blind    = sum(d["totals"]["blind_minutes"]            for d in days)
        total_minutes  = len(days) * 1440
        total_blind_h  = total_blind / 60.0
        total_h        = total_minutes / 60.0

        # Count SAR and Military passes from the sensor field stored per crossing
        sar_total = 0; mil_total = 0
        for d in days:
            for c in d.get("crossings", []):
                sensor_val = c.get("sensor", c.get("sensor_category", "")).upper()
                if "MILITARY" in sensor_val:
                    mil_total += 1
                elif "SAR" in sensor_val:
                    sar_total += 1

        sv, ss = self._stat_sats
        sv.config(text=str(fc.get("satellite_count", 0)))
        ss.config(text=f"Optical + SAR + Military fleet")

        iv, iss = self._stat_india
        iv.config(text=str(ind_oh_total + ind_tilt_total))
        iss.config(text=f"{ind_oh_total} overhead   {ind_tilt_total} tilt-range")

        if hasattr(self, "_stat_sar"):
            sarv, sarss = self._stat_sar
            sarv.config(text=str(sar_total + mil_total))
            sarss.config(text=f"{sar_total} SAR  ·  {mil_total} Military  (day/night)")

        ov, oss = self._stat_other
        ov.config(text=str(oth_oh_total + oth_tilt_total))
        oss.config(text=f"{oth_oh_total} overhead   {oth_tilt_total} tilt-range")

        bv, bss = self._stat_blind
        bv.config(text=f"{total_blind_h:.0f} h")
        bss.config(text=f"of {total_h:.0f} h total ({100*total_blind_h/total_h:.0f}% unobserved)")

        for iid in self._tree.get_children():
            self._tree.delete(iid)
        first_iid = None

        def _split_day(crossings: list[dict]) -> dict:
            """Per-pass-type Optical/SAR breakdown plus unique-sat splits."""
            buckets = {
                "indian_overhead":   {"opt": 0, "sar": 0},
                "indian_tilt_range": {"opt": 0, "sar": 0},
                "other_overhead":    {"opt": 0, "sar": 0},
                "other_tilt_range":  {"opt": 0, "sar": 0},
            }
            sats_opt, sats_sar = set(), set()
            for c in crossings:
                kind = "indian" if c.get("is_indian") else "other"
                ptyp = "overhead" if c.get("pass_type") == "overhead" else "tilt_range"
                bucket = "sar" if "SAR" in (c.get("sensor", "") or "").upper() else "opt"
                buckets[f"{kind}_{ptyp}"][bucket] += 1
                (sats_sar if bucket == "sar" else sats_opt).add(c.get("norad_id"))
            buckets["_sats_opt"] = len(sats_opt)
            buckets["_sats_sar"] = len(sats_sar)
            return buckets

        for d in days:
            t = d["totals"]
            tags = ()
            if t.get("indian_crossings", 0) >= 3:
                tags = ("indian_heavy",)
            elif t.get("longest_blind_min", 0) >= 120:
                tags = ("blind_heavy",)

            # Row 1 — date totals (existing values)
            iid = self._tree.insert("", "end", values=(
                d["date"],
                t.get("indian_overhead",   0),
                t.get("indian_tilt_range", 0),
                t.get("other_overhead",    0),
                t.get("other_tilt_range",  0),
                t["unique_sats"],
                f"{t['blind_minutes']:.0f}",
                f"{t['longest_blind_min']:.0f}",
            ), tags=tags)

            # Rows 2 + 3 — Optical (above) / SAR (below) breakdown per pass type
            # Blind/Longest are day-level metrics so left blank on sub-rows.
            splits = _split_day(d.get("crossings", []))
            self._tree.insert("", "end", values=(
                "  Optical",
                splits["indian_overhead"]["opt"],
                splits["indian_tilt_range"]["opt"],
                splits["other_overhead"]["opt"],
                splits["other_tilt_range"]["opt"],
                splits["_sats_opt"],
                "", "",
            ), tags=("optical_row",))
            self._tree.insert("", "end", values=(
                "  SAR",
                splits["indian_overhead"]["sar"],
                splits["indian_tilt_range"]["sar"],
                splits["other_overhead"]["sar"],
                splits["other_tilt_range"]["sar"],
                splits["_sats_sar"],
                "", "",
            ), tags=("sar_row",))

            if first_iid is None:
                first_iid = iid
        total_indian = ind_oh_total + ind_tilt_total
        total_other  = oth_oh_total + oth_tilt_total
        self._append(f"[*] Reloaded forecast: {len(days)} days, "
                     f"India={total_indian} (OH:{ind_oh_total} Tilt:{ind_tilt_total}), "
                     f"Other={total_other} (OH:{oth_oh_total} Tilt:{oth_tilt_total}).\n",
                     "info")
        if first_iid is not None:
            self._tree.selection_set(first_iid)
            self._tree.see(first_iid)
        self.after(50, self._render_blind_calendar)

    def _reload_changes_banner(self, popup_if_new: bool = True,
                               force_popup: bool = False):
        """
        Read forecast_changes.json (if any) and update the banner.

        Popup rules:
          - `force_popup=True` (REFRESH FORECAST button)  → always show the
            popup, even if there are 0 changes or the diff was previously
            acknowledged. Gives the user an unambiguous "here is what
            today's TLE pull produced vs the prior snapshot" view.
          - `popup_if_new=True` + `force_popup=False` (startup)  → show only
            when there are real, unacked changes (silent otherwise).
        """
        import json
        changes_path = os.path.join(SAT_DIR, "forecast_changes.json")
        if not os.path.isfile(changes_path):
            self._changes_lbl.config(
                text="No prior forecast to compare yet.", fg=TEXT_DIM)
            return
        try:
            with open(changes_path, "r", encoding="utf-8") as f:
                ch = json.load(f)
        except Exception:
            self._changes_lbl.config(
                text="Could not read forecast_changes.json", fg=RED)
            return
        compared_to = ch.get("compared_to")
        if not compared_to:
            self._changes_lbl.config(
                text="First-ever run — nothing to compare against yet.",
                fg=TEXT_DIM)
            return
        t = ch.get("totals", {})
        # Count Indian deltas explicitly
        ind_new = sum(1 for d in ch["days"] for p in d["new_passes"] if p["is_indian"])
        ind_rem = sum(1 for d in ch["days"] for p in d["removed_passes"] if p["is_indian"])
        ind_sft = sum(1 for d in ch["days"] for p in d["shifted_passes"] if p["is_indian"])
        msg = (f"Compared to {compared_to}:   "
               f"+{t.get('new', 0)} new   "
               f"-{t.get('removed', 0)} removed   "
               f"~{t.get('shifted', 0)} shifted   "
               f"blind {t.get('blind_delta_min', 0):+.0f} min   "
               f"|   🇮🇳 India: +{ind_new} / -{ind_rem} / ~{ind_sft}")
        # Color hint: red if Indian deltas are non-zero
        color = RED if (ind_new + ind_rem + ind_sft) > 0 else NEON
        self._changes_lbl.config(text=msg, fg=color)

        # ── No automatic popup ─────────────────────────────────────────────
        # Per user request: the schedule-changes window is NEVER shown
        # automatically (not on startup, not after a REFRESH FORECAST).
        # It only opens when the user clicks the ⇄ SCHEDULE CHANGES button
        # (see _open_schedule_changes). This method now only refreshes the
        # inline banner text above. `force_popup` / `popup_if_new` are kept
        # in the signature for call-site compatibility but no longer pop.
        return

    # ── 15-day blind calendar ──────────────────────────────────────────────
    def _render_blind_calendar(self):
        c = self._cal_canvas
        c.delete("all")
        self._cal_hit_regions = []
        self._cal_geom = None          # invalidated until a full render succeeds
        if not self._forecast:
            return
        days = self._forecast.get("days", [])
        if not days:
            return
        W = c.winfo_width()
        if W < 10:
            return

        HEADER_H = 18          # height of the hour-label header row
        ROW_H    = 22          # height of each day row
        DATE_W   = 72          # width of the date label column on the left
        PCT_W    = 48          # width of the blind% column on the right
        bar_x0   = DATE_W
        bar_x1   = W - PCT_W
        bar_w    = bar_x1 - bar_x0

        # Set scrollregion so the scrollbar covers all rows + header
        total_h = HEADER_H + len(days) * ROW_H + 4
        c.configure(scrollregion=(0, 0, W, total_h))
        rows_top = HEADER_H    # y where day rows start
        if bar_w < 10:
            return

        total_rows_h = len(days) * ROW_H

        # ── 15-minute grid lines through all day rows ─────────────────────────
        # 96 slots of 15 min each; major=hourly, medium=30min, minor=15min
        for q in range(0, 97):          # 0..96 inclusive = 0:00..24:00
            xx = bar_x0 + (q / 96.0) * bar_w
            is_hour  = (q % 4 == 0)
            is_half  = (q % 2 == 0)     # 30-min mark (includes hours)
            is_major6 = (q % 24 == 0)   # 6-hour marks
            if is_major6:
                grid_color = "#2a2f4a"
            elif is_hour:
                grid_color = "#1e2538"
            elif is_half:
                grid_color = "#181e2c"
            else:
                grid_color = "#141820"
            c.create_line(xx, rows_top, xx, rows_top + total_rows_h,
                          fill=grid_color, width=1)

        # ── Day rows ──────────────────────────────────────────────────────────
        for i, day in enumerate(days):
            y_top   = rows_top + i * ROW_H
            y_mid   = y_top + ROW_H // 2
            bar_top = y_top + 2
            bar_bot = y_top + ROW_H - 2
            is_sel  = (day["date"] == self._selected_date)
            row_bg  = "#1e2540" if is_sel else BG

            c.create_rectangle(0, y_top, W, y_top + ROW_H, fill=row_bg, outline="")

            # Date label
            c.create_text(DATE_W - 6, y_mid,
                          text=day["date"][5:],
                          fill=self.COLOR if is_sel else TEXT_DIM,
                          font=("Consolas", 8), anchor="e")

            # Blind background (dark red)
            c.create_rectangle(bar_x0, bar_top, bar_x1, bar_bot,
                                fill="#3a1020", outline="")

            # Observation windows (green) — include sats that produced coverage
            ow_sats = {}  # map start->list of sats for hover
            for cr_src in (day.get("india_crossings", []) + day.get("other_crossings", [])):
                for ow in day.get("observation_windows", []):
                    if cr_src.get("entry_utc", "") <= ow.get("end", "") and \
                       cr_src.get("entry_utc", "") >= ow.get("start", ""):
                        ow_sats.setdefault(ow.get("start", ""), []).append(cr_src)
            for ow in day.get("observation_windows", []):
                try:
                    t0 = _hhmm_frac(ow["start"])
                    t1 = _hhmm_frac(ow["end"])
                    rx0 = bar_x0 + t0 * bar_w
                    rx1 = bar_x0 + t1 * bar_w
                    c.create_rectangle(rx0, bar_top, rx1, bar_bot,
                                       fill="#1a6b35", outline="")
                    self._cal_hit_regions.append((
                        rx0, rx1, bar_top, bar_bot, "obs_window",
                        {"start": ow.get("start", ""), "end": ow.get("end", ""),
                         "day": day["date"],
                         "sats": ow_sats.get(ow.get("start", ""), [])}
                    ))
                except Exception:
                    pass

            # Indian crossing ticks (red)
            for cr in day.get("india_crossings", []):
                try:
                    xx = bar_x0 + _hhmm_frac(cr["entry_utc"]) * bar_w
                    c.create_line(xx, bar_top - 1, xx, bar_bot + 1, fill=RED, width=2)
                    self._cal_hit_regions.append((
                        xx - 4, xx + 4, bar_top, bar_bot, "crossing", cr))
                except Exception:
                    pass

            # Other crossing ticks (cyan = optical, purple = SAR, red = military)
            for cr in day.get("other_crossings", []):
                try:
                    xx = bar_x0 + _hhmm_frac(cr["entry_utc"]) * bar_w
                    sensor_cat = cr.get("sensor_category", cr.get("sensor", "")).upper()
                    if "MILITARY" in sensor_cat:
                        tick_col = "#ef4444"; tick_w = 2
                    elif "SAR" in sensor_cat:
                        tick_col = "#a855f7"; tick_w = 2
                    else:
                        tick_col = CYAN;     tick_w = 1
                    c.create_line(xx, bar_top + 2, xx, bar_bot - 2,
                                  fill=tick_col, width=tick_w)
                    self._cal_hit_regions.append((
                        xx - 4, xx + 4, bar_top, bar_bot, "crossing", cr))
                except Exception:
                    pass

            # Blind % on the right
            t = day["totals"]
            pct = int(t["blind_minutes"] / 14.4)
            pct_color = RED if pct > 80 else (YELLOW if pct > 50 else GREEN)
            c.create_text(bar_x1 + PCT_W - 4, y_mid,
                          text=f"{pct}%", fill=pct_color,
                          font=("Consolas", 8), anchor="e")

        # ── Hour header row (labels every 2 h, ticks every 1 h) ──────────────
        # Header background
        c.create_rectangle(0, 0, W, HEADER_H, fill=PANEL, outline="")
        # "UTC" axis label on the left
        c.create_text(DATE_W - 4, HEADER_H // 2,
                      text="PKT", fill=TEXT_MUTE,
                      font=("Consolas", 7), anchor="e")
        # Header ticks: every 15 min (q=0..96). Labels every 1 h (every 4th).
        for q in range(0, 97):
            h_frac = q / 96.0
            xx     = bar_x0 + h_frac * bar_w
            is_hour   = (q % 4 == 0)   # full-hour mark
            is_half   = (q % 2 == 0)   # 30-min mark
            is_major6 = (q % 24 == 0)  # 6-hour mark

            if is_major6:
                tick_len = 6; tick_col = TEXT_DIM
            elif is_hour:
                tick_len = 4; tick_col = TEXT_MUTE
            elif is_half:
                tick_len = 3; tick_col = "#2e3555"
            else:
                tick_len = 2; tick_col = "#252a45"
            c.create_line(xx, HEADER_H - tick_len, xx, HEADER_H,
                          fill=tick_col, width=1)

            # Hour label (every hour on even hours to avoid clutter)
            if is_hour:
                hour_num = q // 4
                lbl_xx   = xx
                anchor   = "n"
                if hour_num == 0:
                    lbl_xx = bar_x0 + 1; anchor = "nw"
                elif hour_num == 24:
                    lbl_xx = bar_x1 - 1; anchor = "ne"
                c.create_text(lbl_xx, 2,
                              text=f"{hour_num:02d}",
                              fill=TEXT_DIM if is_major6 else TEXT_MUTE,
                              font=("Consolas", 7), anchor=anchor)

        # Stash geometry + locate today's row, then drop the live "now"
        # playhead onto it. _hhmm_frac uses PKT (UTC+5), so the marker —
        # also placed at the current PKT fraction — lines up exactly with
        # the green/red segments under it.
        import datetime as _dtlm
        _today_utc = _dtlm.datetime.utcnow().strftime("%Y-%m-%d")
        _today_row = next((idx for idx, d in enumerate(days)
                           if d["date"] == _today_utc), None)
        self._cal_geom = {
            "bar_x0": bar_x0, "bar_w": bar_w,
            "rows_top": rows_top, "row_h": ROW_H,
            "today_row": _today_row, "n_rows": len(days),
        }
        self._draw_live_marker()

    def _cal_day_at(self, y):
        """Return the day dict for a canvas y pixel (accounts for scroll offset)."""
        HEADER_H, ROW_H = 18, 22
        # Convert widget y to canvas y (accounts for scrolled position)
        canvas_y = self._cal_canvas.canvasy(y)
        idx = int(canvas_y - HEADER_H) // ROW_H
        if not self._forecast:
            return None
        days = self._forecast.get("days", [])
        return days[idx] if 0 <= idx < len(days) else None

    def _cal_click(self, event):
        """Select day from blind calendar click."""
        day = self._cal_day_at(event.y)
        if not day:
            return
        self._selected_date = day["date"]
        for iid in self._tree.get_children():
            if self._tree.set(iid, "date") == self._selected_date:
                self._tree.selection_set(iid)
                self._tree.see(iid)
                break
        self._render_timeline()
        self._render_detail_list()
        self._render_blind_calendar()

    def _cal_dbl_click(self, event):
        """Double-click on calendar row → open detailed day popup."""
        day = self._cal_day_at(event.y)
        if day:
            CalDayPopup(self.winfo_toplevel(), day)

    def _cal_leave(self, event):
        self._cal_hide_tooltip()

    def _cal_hide_tooltip(self):
        if self._cal_tooltip:
            try:
                self._cal_tooltip.destroy()
            except Exception:
                pass
            self._cal_tooltip = None

    def _cal_hover(self, event):
        """Show tooltip when hovering over a crossing tick or observation window."""
        mx, my = event.x, event.y
        hit = None
        for (x0, x1, y0, y1, kind, data) in self._cal_hit_regions:
            if x0 <= mx <= x1 and y0 <= my <= y1:
                hit = (kind, data)
                break

        if hit is None:
            self._cal_hide_tooltip()
            return

        kind, data = hit
        if kind == "crossing":
            cr = data
            sensor_val = cr.get("sensor_category", cr.get("sensor", "Optical"))
            lines = [
                f"  {cr.get('name', '?')}",
                f"  Country : {cr.get('country', '?')}",
                f"  Operator: {cr.get('operator', cr.get('owner', '?'))}",
                f"  Sensor  : {cr.get('sensor', '?')}  [{sensor_val}]",
                f"  Type    : {'OVERHEAD' if cr.get('pass_type') == 'overhead' else 'TILT-RANGE'}",
                f"  Entry   : {_utc_to_pkt(cr['entry_utc'])} PKT",
                f"  Duration: {cr.get('duration_min', '?')} min",
                f"  Dir     : {cr.get('direction', 'N/A')}",
            ]
        else:  # obs_window
            start_pkt = _utc_to_pkt(data["start"])[:5] if data.get("start") else "?"
            end_pkt   = _utc_to_pkt(data["end"])[:5]   if data.get("end")   else "?"
            sats = data.get("sats", [])
            lines = [
                f"  Observation window",
                f"  {start_pkt} → {end_pkt} PKT",
                f"  {len(sats)} satellite(s) overhead/tilt-range",
            ]
            for s in sats[:5]:
                lines.append(f"    · {s.get('name','?')} ({s.get('country','?')})")
            if len(sats) > 5:
                lines.append(f"    … +{len(sats)-5} more")

        self._cal_hide_tooltip()
        tip = tk.Toplevel(self._cal_canvas)
        tip.overrideredirect(True)
        tip.attributes("-topmost", True)
        tip.configure(bg="#0d1a2e")
        frm = tk.Frame(tip, bg="#0d1a2e", bd=1, relief="flat",
                       highlightbackground="#2a4a7f", highlightthickness=1)
        frm.pack(fill="both", expand=True)
        for ln in lines:
            tk.Label(frm, text=ln, font=("Consolas", 9),
                     bg="#0d1a2e", fg="#aaccee",
                     anchor="w", justify="left", padx=4, pady=1).pack(fill="x")
        # Position near cursor, avoid screen edge
        tip.update_idletasks()
        tw, th = tip.winfo_width(), tip.winfo_height()
        sx = event.x_root + 12
        sy = event.y_root - th // 2
        screen_w = tip.winfo_screenwidth()
        if sx + tw > screen_w:
            sx = event.x_root - tw - 6
        tip.geometry(f"+{sx}+{sy}")
        self._cal_tooltip = tip

    # ── Day-select / timeline / detail list ────────────────────────────────
    def _on_day_select(self, event=None):
        sel = self._tree.selection()
        if not sel:
            return
        iid = sel[0]
        date_str = self._tree.set(iid, "date")
        # If the user clicked an Optical/SAR sub-row, walk up to find the
        # nearest preceding row carrying a real date and redirect selection
        # there so the timeline + detail list stay anchored on the day.
        if date_str and date_str.strip() in ("Optical", "SAR"):
            cursor = self._tree.prev(iid)
            while cursor:
                d = self._tree.set(cursor, "date")
                if d and d.strip() not in ("Optical", "SAR"):
                    date_str = d
                    self._tree.selection_set(cursor)
                    self._tree.see(cursor)
                    iid = cursor
                    break
                cursor = self._tree.prev(cursor)
        self._selected_date = date_str
        self._render_timeline()
        self._render_detail_list()
        self._render_blind_calendar()

    def _get_selected_day(self):
        if not self._forecast or not self._selected_date:
            return None
        for d in self._forecast.get("days", []):
            if d["date"] == self._selected_date:
                return d
        return None

    def _render_timeline(self):
        """Paint the 24-hr PKT ribbon for the selected day on the Canvas."""
        c = self._timeline
        c.delete("all")
        self._tl_geom = None           # invalidated until a full render succeeds
        w = c.winfo_width() or 1200
        h = 72
        left, right = 60, w - 20
        bar_top, bar_bot = 22, 50
        if right - left < 50:
            return

        # Background: blind by default (dark navy)
        c.create_rectangle(left, bar_top, right, bar_bot,
                           fill="#1a1f33", outline="")

        day = self._get_selected_day()
        if not day:
            c.create_text((left + right) / 2, h // 2,
                          text="Select a day to view its 24-hour timeline",
                          fill=TEXT_MUTE, font=FONT_MONO)
            return

        # Helpers to convert a UTC time string to an x-coordinate.
        # +5h → PKT, consistent with the 15-day calendar's _hhmm_frac and
        # the "PKT" axis label (the ribbon used to plot UTC under a PKT
        # label — fixed here so the live playhead lands correctly).
        def t_to_x(t_str):
            # t_str like 2026-05-12T05:34:12Z — pull HH:MM:SS
            try:
                hms = t_str[11:19]
                h_, m_, s_ = hms.split(":")
                sec = (int(h_) * 3600 + int(m_) * 60 + int(s_)) + 5 * 3600
                frac = (sec % 86400) / 86400.0
            except Exception:
                return left
            return left + frac * (right - left)

        # Paint observation windows as green segments (means: ≥1 sat overhead/tilt)
        for w_ in day.get("observation_windows", []):
            x1 = t_to_x(w_["start"]); x2 = t_to_x(w_["end"])
            if x2 - x1 < 1: x2 = x1 + 1
            c.create_rectangle(x1, bar_top, x2, bar_bot,
                               fill=GREEN, outline="")

        # Vertical tick marks for each crossing — color by country/pass-type
        for cr in day.get("crossings", []):
            x = t_to_x(cr["entry_utc"])
            if cr["is_indian"]:
                color = RED
                tag_top = bar_top - 8
            else:
                color = AMBER if cr["pass_type"] == "tilt-range" else CYAN
                tag_top = bar_top - 4
            c.create_line(x, tag_top, x, bar_bot + 4,
                          fill=color, width=2)

        # Hour ticks + labels
        for hour in range(0, 25, 3):
            xx = left + (hour / 24.0) * (right - left)
            c.create_line(xx, bar_bot, xx, bar_bot + 6, fill=TEXT_MUTE)
            c.create_text(xx, bar_bot + 14,
                          text=f"{hour:02d}h",
                          fill=TEXT_DIM, font=("Consolas", 8))
        # 'UTC' axis label
        c.create_text(left - 12, (bar_top + bar_bot) / 2,
                      text="PKT", fill=TEXT_DIM, font=("Consolas", 8),
                      anchor="e")

        # Title bar: selected date + counts
        t = day["totals"]
        self._tl_title.config(
            text=(f">> {day['date']}  ·  "
                  f"INDIA {t['indian_overhead']}↓ + {t['indian_tilt_range']}↻   "
                  f"Other {t['other_overhead']}↓ + {t['other_tilt_range']}↻   "
                  f"Blind: {t['blind_minutes']:.0f} min  "
                  f"(longest gap {t['longest_blind_min']:.0f} min)")
        )

        # Stash geometry for the live "now" playhead — only meaningful when
        # the selected day IS today.
        import datetime as _dtlm
        self._tl_geom = {
            "left": left, "right": right,
            "bar_top": bar_top, "bar_bot": bar_bot,
            "is_today": (day["date"] == _dtlm.datetime.utcnow().strftime("%Y-%m-%d")),
        }
        self._draw_live_marker()

    def _draw_live_marker(self):
        """Draw / refresh the live 'now' playhead — a cyan vertical line —
        on today's row of the 15-day calendar and on the 24-h timeline (when
        today is the selected day), and refresh the live coverage chip.
        Cheap enough to run every second; never raises."""
        try:
            import datetime as _dt
            now = _dt.datetime.utcnow()
            now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
            pkt_sec   = (now.hour * 3600 + now.minute * 60 + now.second) + 5 * 3600
            pkt_frac  = (pkt_sec % 86400) / 86400.0
            pkt_label = f"{(pkt_sec % 86400) // 3600:02d}:{(pkt_sec % 86400) % 3600 // 60:02d}"

            # ── 15-day calendar — playhead on today's row ─────────────────
            g = getattr(self, "_cal_geom", None)
            if g and hasattr(self, "_cal_canvas"):
                c = self._cal_canvas
                c.delete("live_marker")
                trow = g.get("today_row")
                if trow is not None:
                    x  = g["bar_x0"] + pkt_frac * g["bar_w"]
                    y0 = g["rows_top"] + trow * g["row_h"]
                    y1 = y0 + g["row_h"]
                    c.create_line(x, y0 - 3, x, y1 + 3, fill="#00e5ff",
                                  width=3, tags="live_marker")
                    c.create_line(x, y0 - 3, x, y1 + 3, fill="#ffffff",
                                  width=1, tags="live_marker")
                    c.create_polygon(x - 5, y0 - 9, x + 5, y0 - 9, x, y0 - 1,
                                     fill="#00e5ff", outline="#ffffff",
                                     tags="live_marker")

            # ── 24-h timeline — playhead only when today is selected ──────
            tg = getattr(self, "_tl_geom", None)
            if hasattr(self, "_timeline"):
                self._timeline.delete("live_marker")
                if tg and tg.get("is_today"):
                    tc = self._timeline
                    x = tg["left"] + pkt_frac * (tg["right"] - tg["left"])
                    tc.create_line(x, tg["bar_top"] - 8, x, tg["bar_bot"] + 8,
                                   fill="#00e5ff", width=3, tags="live_marker")
                    tc.create_line(x, tg["bar_top"] - 8, x, tg["bar_bot"] + 8,
                                   fill="#ffffff", width=1, tags="live_marker")
                    tc.create_polygon(x - 5, tg["bar_top"] - 14,
                                      x + 5, tg["bar_top"] - 14,
                                      x, tg["bar_top"] - 6,
                                      fill="#00e5ff", outline="#ffffff",
                                      tags="live_marker")

            self._update_live_chip(now_iso, pkt_label)
        except Exception:
            pass

    def _update_live_chip(self, now_iso: str, pkt_label: str):
        """Set the live coverage chip: is a satellite over Pakistan right now,
        and if not, when is the next pass."""
        if not hasattr(self, "_live_chip"):
            return
        fc = self._forecast
        if not fc or not fc.get("days"):
            self._live_chip.config(text="◌ LIVE  —  no forecast loaded",
                                   fg=TEXT_MUTE)
            return
        import datetime as _dt
        today_utc = _dt.datetime.utcnow().strftime("%Y-%m-%d")
        days  = fc["days"]
        today = next((d for d in days if d["date"] == today_utc), None)
        if today is None:
            self._live_chip.config(
                text=f"◌ LIVE {pkt_label} PKT  —  forecast not current",
                fg=YELLOW)
            return
        covered = any(ow.get("start", "") <= now_iso <= ow.get("end", "")
                      for ow in today.get("observation_windows", []))
        live_sats = [c for c in (today.get("india_crossings", [])
                                 + today.get("other_crossings", []))
                     if c.get("entry_utc", "") <= now_iso <= c.get("exit_utc", "")]
        if covered:
            if live_sats:
                names = ", ".join(dict.fromkeys(c["name"] for c in live_sats))
                ind = any(c.get("is_indian") for c in live_sats)
                self._live_chip.config(
                    text=f"● LIVE {pkt_label} PKT  —  SATELLITE OVERHEAD: {names}",
                    fg=RED if ind else GREEN)
            else:
                self._live_chip.config(
                    text=f"● LIVE {pkt_label} PKT  —  SATELLITE OVERHEAD",
                    fg=GREEN)
        else:
            upcoming = [c for d in days
                        for c in (d.get("india_crossings", [])
                                  + d.get("other_crossings", []))
                        if c.get("entry_utc", "") > now_iso]
            nxt = min(upcoming, key=lambda c: c["entry_utc"]) if upcoming else None
            if nxt:
                try:
                    t_next = _dt.datetime.strptime(nxt["entry_utc"], "%Y-%m-%dT%H:%M:%SZ")
                    t_now  = _dt.datetime.strptime(now_iso, "%Y-%m-%dT%H:%M:%SZ")
                    mins = max(0, int((t_next - t_now).total_seconds() // 60))
                    self._live_chip.config(
                        text=(f"● LIVE {pkt_label} PKT  —  BLIND, NO SATELLITE "
                              f"OVERHEAD  ·  next: {nxt['name']} in {mins} min"),
                        fg=RED)
                except Exception:
                    self._live_chip.config(
                        text=f"● LIVE {pkt_label} PKT  —  BLIND, NO SATELLITE OVERHEAD",
                        fg=RED)
            else:
                self._live_chip.config(
                    text=f"● LIVE {pkt_label} PKT  —  BLIND, NO SATELLITE OVERHEAD",
                    fg=RED)

    def _tick_live_marker(self):
        """1-second loop that creeps the live playhead and refreshes the chip."""
        self._draw_live_marker()
        try:
            self._live_timer_id = self.after(1000, self._tick_live_marker)
        except Exception:
            self._live_timer_id = None

    def _render_detail_list(self):
        """Populate the per-day crossings detail Treeview."""
        for iid in self._det.get_children():
            self._det.delete(iid)
        day = self._get_selected_day()
        if not day:
            return
        # Show India first, then others — sorted by entry time within each group
        india  = sorted(day.get("india_crossings", []),
                        key=lambda c: c["entry_utc"])
        others = sorted(day.get("other_crossings", []),
                        key=lambda c: c["entry_utc"])
        for c in india + others:
            tags = []
            if c["is_indian"]:
                tags.append("indian")
            elif "MILITARY" in c.get("sensor_category", c.get("sensor", "")).upper():
                tags.append("military")
            elif "SAR" in c.get("sensor_category", c.get("sensor", "")).upper():
                tags.append("sar")
            if c["pass_type"] == "tilt-range":
                tags.append("tilt")
            self._det.insert("", "end", values=(
                _utc_to_pkt(c["entry_utc"]),
                "OVERHEAD" if c["pass_type"] == "overhead" else "TILT-RANGE",
                c["name"],
                c["country"],
                c["sensor"],
                f"~{int(c.get('min_dist_km', 0))} km" if c["pass_type"] == "tilt-range" else "0 (overhead)",
                f"{c['duration_min']:.1f}",
                c["direction"],
            ), tags=tuple(tags))
        self._det_title.config(
            text=f">> CROSSINGS ON {day['date']}  ·  "
                 f"{len(india)} India  +  {len(others)} other"
        )

    # ── Accuracy check ────────────────────────────────────────────────────
    def _run_accuracy_check(self):
        """Run accuracy_tracker.build_accuracy_record() in a thread and show results."""
        import threading, sys
        self._append("[*] Running accuracy check…\n", "info")

        def _worker():
            try:
                sys.path.insert(0, SAT_DIR)
                import accuracy_tracker
                result = accuracy_tracker.build_accuracy_record()
                self.after(0, lambda r=result: _show(r))
            except Exception as exc:
                self.after(0, lambda e=exc: self._append(
                    f"[!] Accuracy check failed: {e}\n", "error"))

        def _show(result):
            by_lb = result.get("by_lookback", [])
            records = result.get("records", [])
            self._append(
                f"[✔] Accuracy check done — {len(records)} comparisons across "
                f"{len(result.get('archive_dates_available', []))} archived runs.\n",
                "done")
            AccuracyPopup(self.winfo_toplevel(), result)

        threading.Thread(target=_worker, daemon=True).start()

    def _open_schedule_changes(self):
        """Open the Schedule Changes window on demand (non-modal).

        Renders the rolling 15-day day-by-day modification history from
        Satellite_Tracker/forecast_changes_history.json. Falls back to the
        single latest diff (forecast_changes.json) if the history file
        doesn't exist yet (e.g. only one daily run so far). Non-blocking —
        the operator can leave it open beside the dashboard.
        """
        import json
        history_path = os.path.join(SAT_DIR, "forecast_changes_history.json")
        changes_path = os.path.join(SAT_DIR, "forecast_changes.json")

        history: list = []
        if os.path.isfile(history_path):
            try:
                with open(history_path, "r", encoding="utf-8") as f:
                    hp = json.load(f)
                if isinstance(hp.get("history"), list):
                    history = hp["history"]
            except (OSError, json.JSONDecodeError) as e:
                self._append(f"[!] forecast_changes_history.json unreadable "
                             f"({type(e).__name__}) — falling back to latest "
                             f"diff only.\n", "warn")

        changes: dict = {}
        if os.path.isfile(changes_path):
            try:
                with open(changes_path, "r", encoding="utf-8") as f:
                    changes = json.load(f)
            except (OSError, json.JSONDecodeError):
                changes = {}

        if not history and not changes:
            self._append("[!] No schedule-change record yet — run REFRESH "
                         "FORECAST at least twice (on different days) so the "
                         "history can start accumulating.\n", "warn")
            return

        if history:
            self._append(f"[*] Opening Schedule Changes — {len(history)}-day "
                         f"modification history.\n", "info")
        else:
            self._append("[*] Opening Schedule Changes — only the latest diff "
                         "is available (history will build over the coming "
                         "days).\n", "info")
        # modal=False — non-blocking window; history drives the day-by-day
        # view. reopen_owner=self enables the ⟳ RELOAD button to re-read the
        # files (picking up the latest hourly-refresh data).
        ChangesPopup(self.winfo_toplevel(), changes, modal=False,
                     history=history, reopen_owner=self)

    # ── File openers ───────────────────────────────────────────────────────
    def _open_report(self):
        docs = sorted(
            glob.glob(os.path.join(self.docs_dir, "Pakistan_15Day_Forecast_*.docx")),
            reverse=True
        )
        if docs:
            os.startfile(docs[0])
        else:
            self._append("[!] No forecast Word doc yet — click REFRESH first.\n", "warn")

    def _open_json(self):
        if os.path.isfile(self.forecast_json):
            os.startfile(self.forecast_json)
        else:
            self._append("[!] forecast_15day.json not present yet.\n", "warn")

    # ── Plumbing shared with the other panels ──────────────────────────────
    def _tick(self):
        if not self._running:
            return
        self._seconds += 1
        m, s = self._seconds // 60, self._seconds % 60
        self._timer_lbl.config(text=f"{m:02d}:{s:02d}")
        self._timer_id = self.after(1000, self._tick)

    def _set_status(self, text, color):
        self._stop_pulse()
        self._status_dot.config(fg=color)
        self._status_lbl.config(text=text, fg=color)

    def _start_pulse(self, color):
        self._pulse_color = color
        self._pulse_on    = True
        self._pulse_tick()

    def _stop_pulse(self):
        if self._pulse_id:
            try: self.after_cancel(self._pulse_id)
            except Exception: pass
            self._pulse_id = None
        self._pulse_color = None

    def _pulse_tick(self):
        if not self._pulse_color:
            return
        c = self._pulse_color if self._pulse_on else dim(self._pulse_color, 0.35)
        try:
            self._status_dot.config(fg=c)
        except Exception:
            return
        self._pulse_on = not self._pulse_on
        self._pulse_id = self.after(550, self._pulse_tick)

    def _append(self, text, tag="default"):
        self._log.config(state="normal")
        ts = datetime.now().strftime("%H:%M:%S  ")
        self._log.insert("end", ts,   ("ts",))
        self._log.insert("end", text, (tag,))
        self._log.see("end")
        self._log.config(state="disabled")
        self._lines += 1

    def _clear_log(self):
        self._log.config(state="normal")
        self._log.delete("1.0", "end")
        self._log.config(state="disabled")
        self._lines = 0

    def stop_process(self):
        if self._proc:
            try:
                self._proc.terminate()
            except Exception:
                pass


# ── Main Application ───────────────────────────────────────────────────────────
class SplashScreen(tk.Toplevel):
    """Professional startup splash — presents the author identity while the
    main dashboard builds in the background. Borderless, centred, dark-themed,
    with a short staged progress animation. Auto-dismissed by the app."""

    def __init__(self, parent):
        super().__init__(parent)
        self.overrideredirect(True)            # no title bar / chrome
        try:
            self.attributes("-topmost", True)  # sit above everything on launch
        except tk.TclError:
            pass

        W, H = 560, 340
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{W}x{H}+{(sw - W) // 2}+{(sh - H) // 2}")
        self.configure(bg=NEON)

        # Neon hairline border → inner dark panel
        inner = tk.Frame(self, bg=BG2)
        inner.pack(fill="both", expand=True, padx=2, pady=2)
        tk.Frame(inner, bg=CYAN,   height=3).pack(fill="x")
        tk.Frame(inner, bg=ACCENT, height=1).pack(fill="x")

        tk.Frame(inner, bg=BG2, height=40).pack()
        tk.Label(inner, text="◉   ORBITAL  INTELLIGENCE  SYSTEMS",
                 font=("Consolas", 9, "bold"), bg=BG2, fg=CYAN).pack()

        tk.Frame(inner, bg=BG2, height=16).pack()
        tk.Label(inner, text="TATARI AI",
                 font=("Segoe UI", 32, "bold"), bg=BG2, fg=TEXT).pack()
        tk.Label(inner, text="ATLAS   ·   SPACE  TRACKER",
                 font=("Consolas", 11, "bold"), bg=BG2, fg=NEON).pack(pady=(8, 0))

        tk.Frame(inner, bg=BG2, height=34).pack()

        # Staged progress bar
        bar_bg = tk.Frame(inner, bg=BG3, width=380, height=4)
        bar_bg.pack()
        bar_bg.pack_propagate(False)
        self._bar_w = 380
        self._bar = tk.Frame(bar_bg, bg=NEON, height=4)
        self._bar.place(x=0, y=0, width=0, height=4)

        self._status = tk.Label(inner, text="Initializing orbital systems...",
                                font=("Consolas", 8), bg=BG2, fg=TEXT_DIM)
        self._status.pack(pady=(12, 0))

        # Author credit pinned to the splash footer
        tk.Frame(inner, bg=BG2).pack(expand=True, fill="both")
        tk.Frame(inner, bg=BG3, height=1).pack(fill="x", padx=24)
        tk.Label(inner, text="by   TATARI",
                 font=("Consolas", 8, "bold"), bg=BG2, fg=TEXT_MUTE
                 ).pack(pady=(8, 12))

        self.update_idletasks()
        self._animate()

    def _animate(self, step: int = 0):
        stages = [
            (16,  "Loading TLE catalogue..."),
            (40,  "Propagating orbits (SGP4)..."),
            (62,  "Computing Pakistan crossings..."),
            (84,  "Building dashboard modules..."),
            (100, "Ready."),
        ]
        if step >= len(stages):
            return
        pct, msg = stages[step]
        try:
            self._bar.place_configure(width=int(self._bar_w * pct / 100))
            self._status.config(text=msg)
            self.after(340, lambda: self._animate(step + 1))
        except tk.TclError:
            pass  # splash already torn down — harmless


class SpaceTrackerApp(tk.Tk):
    """Standalone ATLAS — Space Tracker dashboard."""

    NAV_ITEMS = [
        ("satellite", "🛰️",  "Satellite Tracker"),
        ("forecast",  "📅", "15-Day Forecast"),
        ("launches",  "🚀", "Rocket Launches"),
        ("orbit",     "🌍", "Pakistan Orbit Tracker"),
    ]

    def __init__(self):
        super().__init__()
        self.title("ATLAS — SPACE TRACKER")
        self.geometry("1300x820")
        self.minsize(1000, 640)
        self.configure(bg=BG)
        self._panels = {}
        self._active = None
        self._nav_btns = {}

        # ── Professional startup splash ────────────────────────────────────
        # Hide the main window, show the SABEEL AHMED AI splash, build the
        # dashboard behind it, then reveal. Never let a splash failure block
        # the app from starting.
        self.withdraw()
        splash = None
        try:
            splash = SplashScreen(self)
            splash.update()
        except tk.TclError:
            splash = None

        self._build()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        # NOTE: the schedule-changes window is NEVER raised automatically.
        # Per user request it opens ONLY when the ⇄ SCHEDULE CHANGES button
        # is clicked. The old startup auto-popup call has been removed.

        def _reveal():
            if splash is not None:
                try:
                    splash.destroy()
                except tk.TclError:
                    pass
            self.deiconify()
            self.lift()
            try:
                self.focus_force()
            except tk.TclError:
                pass
        # ~2.1 s — long enough for the splash progress animation to complete.
        self.after(2100, _reveal)

    def _check_for_unacked_changes(self):
        """
        DISABLED — kept only so any stray call site does not crash.
        The schedule-changes window is now opened exclusively by the
        ⇄ SCHEDULE CHANGES button (see Forecast15DayPanel._open_schedule_changes).
        """
        return
        # --- legacy auto-popup logic below, intentionally unreachable ---
        import json
        print("[POPUP] checking forecast_changes.json...")
        changes_path = os.path.join(SAT_DIR, "forecast_changes.json")
        if not os.path.isfile(changes_path):
            print("[POPUP] no forecast_changes.json — nothing to show")
            return
        try:
            with open(changes_path, "r", encoding="utf-8") as f:
                ch = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print(f"[POPUP] could not read: {e}")
            return
        if not ch.get("compared_to"):
            print("[POPUP] compared_to is empty — first run, suppressing")
            return
        t = ch.get("totals", {})
        total = (t.get("new", 0) + t.get("removed", 0) + t.get("shifted", 0))
        if total == 0:
            print("[POPUP] no changes — silent (per spec)")
            return
        ack_path = os.path.join(SAT_DIR, ".changes_acked")
        acked = ""
        if os.path.isfile(ack_path):
            try:
                with open(ack_path, "r", encoding="utf-8") as f:
                    acked = f.read().strip()
            except OSError:
                pass
        if ch.get("generated_at", "") == acked:
            print(f"[POPUP] already acked (generated_at={ch.get('generated_at')})")
            return
        print(f"[POPUP] FIRING — {total} changes vs {ch.get('compared_to')}")
        try:
            ChangesPopup(self, ch)
            print("[POPUP] popup constructed OK")
        except Exception as e:
            import traceback
            print(f"[POPUP] failed: {e}")
            traceback.print_exc()

    # ── Build UI ───────────────────────────────────────────────────────────────
    def _build(self):
        # ── Title bar — satellite telemetry ────────────────────────────────────
        tb = tk.Frame(self, bg=BG2, height=52)
        tb.pack(fill="x")
        tb.pack_propagate(False)

        # Satellite glyph cluster
        tk.Label(tb, text="🛰", font=("Segoe UI Emoji", 18),
                 bg=BG2, fg=CYAN).pack(side="left", padx=(18, 6))
        tk.Label(tb, text="◉", font=("Segoe UI", 14, "bold"),
                 bg=BG2, fg=NEON).pack(side="left", padx=(0, 10))

        tk.Label(tb, text="ATLAS",
                 font=("Segoe UI", 15, "bold"), bg=BG2, fg=TEXT
                 ).pack(side="left")
        tk.Label(tb, text="ORBITAL  COMMAND",
                 font=("Consolas", 8, "bold"), bg=BG2, fg=CYAN
                 ).pack(side="left", padx=(10, 0), pady=(6, 0))
        tk.Label(tb, text="·  SATELLITE  &  LAUNCH  TELEMETRY",
                 font=("Consolas", 8), bg=BG2, fg=TEXT_MUTE
                 ).pack(side="left", padx=(8, 0), pady=(6, 0))

        # ── Author credit — pinned to the far top-right ────────────────────
        credit = tk.Frame(tb, bg=BG2)
        credit.pack(side="right", padx=(0, 18))
        tk.Label(credit, text="TATARI",
                 font=("Segoe UI", 12, "bold"), bg=BG2, fg=NEON
                 ).pack(side="right")
        tk.Label(credit, text="by",
                 font=("Consolas", 8), bg=BG2, fg=TEXT_MUTE
                 ).pack(side="right", padx=(0, 6))
        tk.Frame(tb, bg=BG3, width=1, height=24).pack(side="right", padx=10)

        # Right side: signal status + UTC clock
        right_tb = tk.Frame(tb, bg=BG2)
        right_tb.pack(side="right", padx=18)
        self._clock_lbl = tk.Label(right_tb, text="--:--:-- UTC",
                                   font=("Consolas", 12, "bold"),
                                   bg=BG2, fg=NEON)
        self._clock_lbl.pack(side="right")
        tk.Label(right_tb, text="◉ SIGNAL LOCK",
                 font=("Consolas", 8, "bold"), bg=BG2, fg=GREEN
                 ).pack(side="right", padx=(0, 14))
        self._tick_clock()

        # Telemetry strip — 3 layered bars (signal-cyan → blue → glow)
        tk.Frame(self, bg=CYAN,   height=2).pack(fill="x")
        tk.Frame(self, bg=ACCENT, height=1).pack(fill="x")
        tk.Frame(self, bg=GLOW,   height=1).pack(fill="x")

        # ── Main layout ────────────────────────────────────────────────────────
        layout = tk.Frame(self, bg=BG)
        layout.pack(fill="both", expand=True)

        # ── Sidebar ────────────────────────────────────────────────────────────
        sidebar = tk.Frame(layout, bg=PANEL, width=220)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        # Brand — animated orbital command center
        self._build_orbital_brand(sidebar)
        # Telemetry accent under brand
        tk.Frame(sidebar, bg=CYAN,   height=2).pack(fill="x")
        tk.Frame(sidebar, bg=ACCENT, height=1).pack(fill="x")

        # Nav section label
        nav = tk.Frame(sidebar, bg=PANEL, pady=12)
        nav.pack(fill="x")
        tk.Label(nav, text="◈  TRACKING  MODULES", font=("Consolas", 8, "bold"),
                 bg=PANEL, fg=NEON).pack(anchor="w", padx=14, pady=(8, 4))

        for key, icon, label in self.NAV_ITEMS:
            btn_tuple = self._make_nav_btn(nav, key, icon, label)
            self._nav_btns[key] = btn_tuple

        # Mission control section
        tk.Frame(sidebar, bg=BORDER, height=1).pack(fill="x", pady=(10, 8))
        tk.Label(sidebar, text="◆  MISSION  CONTROL", font=("Consolas", 8, "bold"),
                 bg=PANEL, fg=CYAN).pack(anchor="w", padx=14, pady=(0, 8))

        # HERO — RUN ALL
        hero_wrap = tk.Frame(sidebar, bg=PANEL)
        hero_wrap.pack(fill="x", padx=12, pady=(0, 6))
        tk.Frame(hero_wrap, bg=CYAN, height=2).pack(fill="x")
        FlatBtn(
            hero_wrap, "▶   ENGAGE  ALL  TRACKERS", self._run_all,
            bg=ACCENT, fg="#ffffff",
            hover_bg=NEON, hover_fg=BG,
            font=("Segoe UI", 10, "bold"),
            padx=0, pady=14,
        ).pack(fill="x")
        tk.Frame(hero_wrap, bg=NEON, height=2).pack(fill="x")

        tk.Label(sidebar, text="LAUNCH  ALL  MODULES  IN  PARALLEL",
                 font=("Consolas", 7), bg=PANEL, fg=TEXT_MUTE
                 ).pack(anchor="center", padx=12, pady=(0, 10))

        FlatBtn(sidebar, "■   ABORT  ALL", self._stop_all,
                bg=BG3, fg=RED, hover_bg=RED, hover_fg="#fff",
                font=("Segoe UI", 9, "bold"), padx=0, pady=8
                ).pack(fill="x", padx=12)

        # Footer
        tk.Frame(sidebar, bg=BORDER, height=1).pack(side="bottom", fill="x")
        footer = tk.Frame(sidebar, bg=PANEL, pady=10)
        footer.pack(side="bottom", fill="x")
        tk.Label(footer, text="◉ ONLINE", font=("Consolas", 8, "bold"),
                 bg=PANEL, fg=GREEN).pack(side="left", padx=14)
        tk.Label(footer, text="v1.0", font=FONT_MONO,
                 bg=PANEL, fg=TEXT_MUTE).pack(side="right", padx=14)

        # Sidebar right border
        tk.Frame(layout, bg=BORDER, width=1).pack(side="left", fill="y")

        # ── Content area ───────────────────────────────────────────────────────
        self._content = tk.Frame(layout, bg=BG)
        self._content.pack(side="left", fill="both", expand=True)

        # Build panels
        self._panels["satellite"] = SatellitePanel(self._content)
        self._panels["forecast"]  = Forecast15DayPanel(self._content)
        self._panels["launches"]  = RocketLaunchPanel(self._content)
        self._panels["orbit"]     = OrbitTrackerPanel(self._content)

        # Show first tab
        self._show_tab("satellite")

    # ── Animated orbital brand ────────────────────────────────────────────────
    def _build_orbital_brand(self, parent):
        """Sidebar brand: animated starfield + concentric orbits + satellite."""
        W, H = 200, 170
        self._brand_canvas = tk.Canvas(
            parent, width=W, height=H, bg=PANEL,
            highlightthickness=0, bd=0,
        )
        self._brand_canvas.pack(fill="x", pady=(14, 10))
        c = self._brand_canvas

        cx, cy = W // 2, H // 2 + 18      # ring center offset down to leave room for text

        # ── Starfield (drawn first so everything renders above it) ──────────
        self._brand_stars = []
        for _ in range(22):
            sx = random.randint(4, W - 4)
            sy = random.randint(4, H - 4)
            # Avoid drawing stars on top of the text band
            r = random.choice([1, 1, 1, 2])
            bright = random.choice([TEXT, NEON, CYAN, ACCENT2])
            d = dim(bright, 0.25)
            item = c.create_oval(sx - r, sy - r, sx + r, sy + r,
                                 fill=bright, outline="")
            self._brand_stars.append({
                "item": item, "bright": bright, "dim": d,
                "phase": random.random() * math.tau,
                "twinkle": random.random() < 0.55,
            })

        # ── Concentric orbit rings ──────────────────────────────────────────
        for r, col in [(58, dim(CYAN, 0.45)),
                       (42, dim(ACCENT, 0.55)),
                       (26, dim(ACCENT2, 0.45))]:
            c.create_oval(cx - r, cy - r, cx + r, cy + r,
                          outline=col, width=1)

        # ── Earth glyph at center ───────────────────────────────────────────
        c.create_oval(cx - 6, cy - 6, cx + 6, cy + 6,
                      fill=ACCENT, outline=NEON, width=1)
        c.create_oval(cx - 9, cy - 9, cx + 9, cy + 9,
                      outline=dim(NEON, 0.5), width=1)

        # ── Satellite (placeholder coords; animated below) ──────────────────
        sat_body  = c.create_rectangle(0, 0, 0, 0, fill=CYAN, outline="")
        sat_left  = c.create_rectangle(0, 0, 0, 0, fill=dim(CYAN, 0.7), outline="")
        sat_right = c.create_rectangle(0, 0, 0, 0, fill=dim(CYAN, 0.7), outline="")
        sat_glow  = c.create_oval(0, 0, 0, 0, outline=NEON, width=1)
        self._brand_sat_items = (sat_body, sat_left, sat_right, sat_glow)
        self._brand_sat_angle = 0.0
        self._brand_sat_orbit_r = 58
        self._brand_center = (cx, cy)

        # ── Text overlay (ATLAS + tagline) ──────────────────────────────────
        c.create_text(W // 2, 14, text="ATLAS",
                      font=("Segoe UI", 18, "bold"), fill=TEXT)
        c.create_text(W // 2, 32, text="ORBITAL  COMMAND  CENTER",
                      font=("Consolas", 7, "bold"), fill=CYAN)

        # ── Start animation ─────────────────────────────────────────────────
        self._brand_anim_id = None
        self._brand_tick = 0
        self._animate_orbital_brand()

    def _animate_orbital_brand(self):
        """Advance satellite + twinkle stars. Re-schedules itself."""
        try:
            c = self._brand_canvas
            cx, cy = self._brand_center
            r = self._brand_sat_orbit_r

            # Satellite position
            self._brand_sat_angle = (self._brand_sat_angle + 0.052) % math.tau
            ang = self._brand_sat_angle
            sx = cx + r * math.cos(ang)
            sy = cy + r * math.sin(ang)

            body, left, right, glow = self._brand_sat_items
            # Body — 5x5 square
            c.coords(body,  sx - 2, sy - 2, sx + 3, sy + 3)
            # Solar panels — thin rectangles flanking the body
            c.coords(left,  sx - 7, sy - 1, sx - 3, sy + 2)
            c.coords(right, sx + 3, sy - 1, sx + 7, sy + 2)
            # Glow halo
            c.coords(glow,  sx - 5, sy - 5, sx + 6, sy + 6)

            # Twinkle ~ every 6 ticks (~360ms)
            self._brand_tick += 1
            if self._brand_tick % 6 == 0:
                for st in self._brand_stars:
                    if not st["twinkle"]:
                        continue
                    st["phase"] = (st["phase"] + 0.6) % math.tau
                    on = math.sin(st["phase"]) > 0
                    c.itemconfig(st["item"],
                                 fill=st["bright"] if on else st["dim"])
        except tk.TclError:
            # Canvas was destroyed — stop the loop quietly
            return
        except Exception:
            _log_exc("orbital brand animation")
            return

        self._brand_anim_id = self.after(60, self._animate_orbital_brand)

    # ── Nav button factory ─────────────────────────────────────────────────────
    def _make_nav_btn(self, parent, key, icon, label):
        f = tk.Frame(parent, bg=PANEL, cursor="hand2")
        f.pack(fill="x", padx=6, pady=2)

        accent_bar = tk.Frame(f, bg=PANEL, width=3)
        accent_bar.pack(side="left", fill="y")

        lbl = tk.Label(f, text=f"  {icon}  {label}", font=FONT_MED,
                       bg=PANEL, fg=TEXT_DIM, anchor="w", padx=10, pady=10)
        lbl.pack(side="left", fill="x", expand=True)

        badge = tk.Label(f, text="—", font=FONT_MONO,
                         bg=BG3, fg=TEXT_MUTE, padx=8, pady=3)
        badge.pack(side="right", padx=10)

        def click(_=None):
            self._show_tab(key)

        for w in (f, lbl, badge, accent_bar):
            w.bind("<Button-1>", click)

        def enter(_):
            if self._active != key:
                f.config(bg=BG3); lbl.config(bg=BG3); accent_bar.config(bg=ACCENT2)
        def leave(_):
            if self._active != key:
                f.config(bg=PANEL); lbl.config(bg=PANEL); accent_bar.config(bg=PANEL)
        for w in (f, lbl):
            w.bind("<Enter>", enter); w.bind("<Leave>", leave)

        return (f, lbl, badge, accent_bar)

    # ── Tab switching ──────────────────────────────────────────────────────────
    def _show_tab(self, key):
        if self._active and self._active in self._nav_btns:
            f, lbl, badge, bar = self._nav_btns[self._active]
            f.config(bg=PANEL); lbl.config(bg=PANEL, fg=TEXT_DIM); bar.config(bg=PANEL)

        self._active = key

        f, lbl, badge, bar = self._nav_btns[key]
        f.config(bg=BG3)
        lbl.config(bg=BG3, fg=CYAN)
        bar.config(bg=CYAN)

        for k, p in self._panels.items():
            p.pack_forget()
        self._panels[key].pack(fill="both", expand=True)

    # ── Bulk actions ───────────────────────────────────────────────────────────
    def _run_all(self):
        for p in self._panels.values():
            if not p._running:
                p._run()

    def _stop_all(self):
        for p in self._panels.values():
            if p._running:
                p._stop()

    # ── Clock ──────────────────────────────────────────────────────────────────
    def _tick_clock(self):
        now = datetime.utcnow().strftime("%Y-%m-%d  %H:%M:%S UTC")
        self._clock_lbl.config(text=now)
        self.after(1000, self._tick_clock)

    # ── Cleanup ────────────────────────────────────────────────────────────────
    def _on_close(self):
        for p in self._panels.values():
            p.stop_process()
        self.destroy()


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = SpaceTrackerApp()
    app.mainloop()
