"""
Claude Usage Monitor — Standalone Desktop Widget
A tiny always-on-top window showing Claude session/weekly usage.
No browser required. Auto-refreshes every 60 seconds.

First run: choose your browser to provide cookies.
  - Firefox: auto-detected from cookies.sqlite
  - Chrome/Edge/other: manual paste from DevTools
The sessionKey auto-renews on each API call.

Requires: pip install curl_cffi
"""

__version__ = "1.2.0"

import tkinter as tk
import json
import os
import sys
import re
import stat
import glob
import shutil
import sqlite3
import tempfile
import webbrowser
from curl_cffi import requests as curl_requests

# Hide console window when launched from .bat / shortcut (Windows only)
if sys.platform == "win32":
    import ctypes
    ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.json")
REFRESH_MS = 60_000  # 60 seconds


# ---------------------------------------------------------------------------
# Config persistence
# ---------------------------------------------------------------------------

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, ValueError):
            return {}
    return {}


def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(cfg, f, indent=2)
        if sys.platform != "win32":
            os.chmod(CONFIG_FILE, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Cookie helpers
# ---------------------------------------------------------------------------

def sanitize_cookies(raw):
    """Strip newlines and control characters from cookie input."""
    return re.sub(r'[\x00-\x1f\x7f]', '', raw).strip()


def _find_firefox_profiles_dir():
    """Return the Firefox profiles root directory for this OS, or None."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA", "")
        return os.path.join(base, "Mozilla", "Firefox", "Profiles") if base else None
    elif sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/Firefox/Profiles")
    else:
        return os.path.expanduser("~/.mozilla/firefox")


def extract_firefox_cookies():
    """Extract claude.ai cookies from Firefox's cookies.sqlite.

    Returns a cookie header string, or raises an exception with a
    user-friendly message explaining what went wrong.
    """
    profiles_dir = _find_firefox_profiles_dir()
    if not profiles_dir or not os.path.isdir(profiles_dir):
        raise FileNotFoundError("Firefox profile directory not found.")

    # Find all cookies.sqlite files across profiles
    cookie_files = glob.glob(os.path.join(profiles_dir, "*", "cookies.sqlite"))
    if not cookie_files:
        raise FileNotFoundError("No Firefox cookie database found. Is Firefox installed?")

    # Use the most recently modified profile
    cookie_files.sort(key=os.path.getmtime, reverse=True)
    db_path = cookie_files[0]

    # Copy to temp file to avoid locking issues while Firefox is running
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".sqlite")
    os.close(tmp_fd)
    try:
        shutil.copy2(db_path, tmp_path)
        conn = sqlite3.connect(f"file:{tmp_path}?mode=ro", uri=True)
        try:
            rows = conn.execute(
                "SELECT name, value FROM moz_cookies "
                "WHERE host LIKE '%claude.ai' ORDER BY name"
            ).fetchall()
        finally:
            conn.close()
    finally:
        os.unlink(tmp_path)

    if not rows:
        raise ValueError(
            "No claude.ai cookies found in Firefox.\n"
            "Open claude.ai in Firefox and log in first."
        )

    cookie_str = "; ".join(f"{name}={value}" for name, value in rows)
    return cookie_str


def _find_safari_cookies_path():
    """Return the Safari binary cookies path (macOS only), or None."""
    if sys.platform != "darwin":
        return None
    path = os.path.expanduser("~/Library/Cookies/Cookies.binarycookies")
    return path if os.path.exists(path) else None


def extract_safari_cookies():
    """Extract claude.ai cookies from Safari's binary cookie store.

    Safari stores cookies in a custom binary format. This parser handles
    the documented format without external dependencies.
    """
    import struct

    path = _find_safari_cookies_path()
    if not path:
        raise FileNotFoundError(
            "Safari cookie file not found.\n"
            "This feature is only available on macOS."
        )

    with open(path, "rb") as f:
        data = f.read()

    # Validate magic bytes: "cook"
    if data[:4] != b"cook":
        raise ValueError("Invalid Safari cookie file format.")

    num_pages = struct.unpack(">I", data[4:8])[0]
    page_sizes = []
    offset = 8
    for _ in range(num_pages):
        page_sizes.append(struct.unpack(">I", data[offset:offset + 4])[0])
        offset += 4

    cookies = []
    for page_size in page_sizes:
        page_data = data[offset:offset + page_size]
        offset += page_size

        if page_data[:4] != b"\x00\x00\x01\x00":
            continue

        num_cookies = struct.unpack("<I", page_data[4:8])[0]
        cookie_offsets = []
        pos = 8
        for _ in range(num_cookies):
            cookie_offsets.append(struct.unpack("<I", page_data[pos:pos + 4])[0])
            pos += 4

        for co in cookie_offsets:
            try:
                # Cookie record layout (little-endian):
                # 0-4: size, 4-8: flags, 8-12: padding
                # 12-16: url_offset, 16-20: name_offset
                # 20-24: path_offset, 24-28: value_offset
                c = page_data[co:]
                if len(c) < 28:
                    continue
                url_off = struct.unpack("<I", c[16:20])[0]
                name_off = struct.unpack("<I", c[20:24])[0]
                value_off = struct.unpack("<I", c[24:28])[0]

                def read_cstr(buf, start):
                    end = buf.index(b"\x00", start)
                    return buf[start:end].decode("utf-8", errors="replace")

                domain = read_cstr(c, url_off)
                name = read_cstr(c, name_off)
                value = read_cstr(c, value_off)

                if "claude.ai" in domain:
                    cookies.append((name, value))
            except (struct.error, ValueError, IndexError):
                continue

    if not cookies:
        raise ValueError(
            "No claude.ai cookies found in Safari.\n"
            "Open claude.ai in Safari and log in first."
        )

    return "; ".join(f"{name}={value}" for name, value in cookies)


# ---------------------------------------------------------------------------
# API communication
# ---------------------------------------------------------------------------

def api_request(path, cookies):
    """Make a GET request to claude.ai using Chrome TLS impersonation."""
    url = f"https://claude.ai{path}"
    resp = curl_requests.get(
        url,
        headers={
            "Accept": "application/json",
            "Cookie": cookies,
            "Referer": "https://claude.ai/settings/usage",
        },
        impersonate="chrome",
        timeout=15,
    )

    # Update sessionKey from Set-Cookie if present
    updated_cookies = cookies
    set_cookie = resp.headers.get("Set-Cookie", "")
    if "sessionKey=" in set_cookie:
        start = set_cookie.index("sessionKey=") + len("sessionKey=")
        end = set_cookie.index(";", start) if ";" in set_cookie[start:] else len(set_cookie)
        new_key = set_cookie[start:end]
        old_match = re.search(r'sessionKey=[^;]+', cookies)
        if old_match:
            updated_cookies = cookies[:old_match.start()] + f'sessionKey={new_key}' + cookies[old_match.end():]

    if resp.status_code == 200:
        try:
            return resp.json(), updated_cookies
        except (json.JSONDecodeError, ValueError):
            raise Exception("Invalid JSON in API response")
    elif resp.status_code in (401, 403):
        raise PermissionError(f"Auth failed (HTTP {resp.status_code}). Paste fresh cookies.")
    else:
        raise Exception(f"HTTP {resp.status_code}")


def time_until(iso_str):
    if not iso_str:
        return ""
    from datetime import datetime, timezone
    try:
        reset = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        diff = (reset - now).total_seconds()
        if diff <= 0:
            return "Resetting..."
        h = int(diff // 3600)
        m = int((diff % 3600) // 60)
        return f"Resets in {h}h {m}m"
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Main widget
# ---------------------------------------------------------------------------

class UsageWidget:
    BG = "#1a1a2e"
    BG2 = "#12122a"
    BAR_BG = "#2a2a3e"
    TEXT = "#e0e0e0"
    DIM = "#777777"
    DIMMER = "#555555"
    BLUE = "#2563eb"
    AMBER = "#d97706"
    GREEN = "#059669"
    RED = "#dc2626"
    FF_ORANGE = "#e05d00"
    SAFARI_BLUE = "#0a84ff"

    # Default geometry for the main usage view
    MAIN_GEOM = "420x120"
    MAIN_MIN_W = 320
    MAIN_MIN_H = 100

    def __init__(self):
        self.cfg = load_config()
        self.cookies = self.cfg.get("cookies", "")
        self.org_id = self.cfg.get("org_id", "")
        self._refreshing = False

        self.topmost = self.cfg.get("topmost", True)

        self.root = tk.Tk()
        self.root.title("Claude Usage")
        self.root.configure(bg=self.BG)
        self.root.attributes("-topmost", self.topmost)
        self.root.resizable(True, True)
        self.root.minsize(self.MAIN_MIN_W, self.MAIN_MIN_H)
        geom = self.cfg.get("geometry", self.MAIN_GEOM)
        self.root.geometry(geom)
        self.root.overrideredirect(False)

        if not self.cookies:
            self._show_browser_chooser()
            return

        self._build_ui()
        self._refresh()
        self.root.mainloop()

    # ------------------------------------------------------------------
    # Browser chooser (first screen)
    # ------------------------------------------------------------------

    def _show_browser_chooser(self):
        self.root.resizable(False, False)
        self.root.geometry("340x280")
        self.root.title("Claude Usage \u2014 Setup")
        self._build_browser_chooser()
        self.root.mainloop()

    def _build_browser_chooser(self, can_cancel=False):
        frame = tk.Frame(self.root, bg=self.BG, padx=20, pady=16)
        frame.pack(fill="both", expand=True)

        tk.Label(frame, text="Choose how to connect", bg=self.BG, fg=self.TEXT,
                 font=("Segoe UI", 11, "bold"), anchor="w").pack(fill="x", pady=(0, 2))

        tk.Label(frame, text="Log into claude.ai in your browser first, then pick your browser below.",
                 bg=self.BG, fg=self.AMBER, font=("Segoe UI", 9),
                 anchor="w", wraplength=300, justify="left").pack(fill="x", pady=(0, 10))

        # Firefox button
        ff_btn = tk.Button(
            frame, text="\U0001f98a  Firefox (auto-detect)",
            bg=self.FF_ORANGE, fg="white",
            font=("Segoe UI", 10, "bold"), relief="flat",
            padx=12, pady=6, anchor="w",
            command=self._on_firefox)
        ff_btn.pack(fill="x", pady=(0, 6))

        # Safari button (macOS only)
        safari_available = sys.platform == "darwin"
        safari_btn = tk.Button(
            frame, text="\U0001f9ed  Safari (auto-detect)",
            bg=self.SAFARI_BLUE if safari_available else self.BAR_BG,
            fg="white" if safari_available else self.DIMMER,
            font=("Segoe UI", 10, "bold"), relief="flat",
            padx=12, pady=6, anchor="w",
            command=self._on_safari if safari_available else None,
            state="normal" if safari_available else "disabled")
        safari_btn.pack(fill="x", pady=(0, 6))
        if not safari_available:
            tk.Label(frame, text="macOS only", bg=self.BG, fg=self.DIMMER,
                     font=("Segoe UI", 8), anchor="e").pack(fill="x", pady=(0, 4))

        # Chrome / manual button
        chrome_btn = tk.Button(
            frame, text="\U0001f310  Chrome / Other (manual paste)",
            bg=self.BAR_BG, fg=self.TEXT,
            font=("Segoe UI", 10), relief="flat",
            padx=12, pady=6, anchor="w",
            command=self._on_manual)
        chrome_btn.pack(fill="x", pady=(0, 6))

        self.chooser_status = tk.Label(frame, text="", bg=self.BG, fg=self.RED,
                                        font=("Segoe UI", 9), wraplength=300, justify="left")
        self.chooser_status.pack(fill="x", pady=(4, 0))

        if can_cancel:
            cancel_btn = tk.Button(frame, text="Cancel", bg=self.BAR_BG, fg=self.DIM,
                                   font=("Segoe UI", 9), relief="flat", padx=12, pady=4,
                                   command=self._cancel_setup)
            cancel_btn.pack(pady=(4, 0))
            self.root.bind("<Escape>", lambda e: self._cancel_setup())

    def _on_firefox(self):
        self.chooser_status.config(text="Detecting Firefox cookies...", fg=self.DIM)
        self.root.update()
        try:
            cookies = extract_firefox_cookies()
            self._try_connect(cookies)
        except Exception as e:
            self.chooser_status.config(text=str(e), fg=self.RED)

    def _on_safari(self):
        self.chooser_status.config(text="Detecting Safari cookies...", fg=self.DIM)
        self.root.update()
        try:
            cookies = extract_safari_cookies()
            self._try_connect(cookies)
        except Exception as e:
            self.chooser_status.config(text=str(e), fg=self.RED)

    def _on_manual(self):
        """Switch to manual paste UI."""
        for w in self.root.winfo_children():
            w.destroy()
        self.root.resizable(False, False)
        self.root.geometry("420x250")
        self._build_manual_paste_ui()

    def _try_connect(self, cookies):
        """Validate cookies against the API and transition to main UI."""
        cookies = sanitize_cookies(cookies)
        try:
            data, updated_cookies = api_request("/api/organizations", cookies)
            if not data or not isinstance(data, list) or len(data) == 0:
                self.chooser_status.config(text="No organizations found.", fg=self.RED)
                return

            self.cookies = updated_cookies
            self.org_id = data[0].get("uuid", "")
            self.cfg["cookies"] = self.cookies
            self.cfg["org_id"] = self.org_id
            save_config(self.cfg)

            self._transition_to_main()

        except PermissionError as e:
            self.chooser_status.config(text=str(e), fg=self.RED)
        except Exception as e:
            self.chooser_status.config(text=f"Error: {e}", fg=self.RED)

    def _transition_to_main(self):
        """Clear setup UI and show the main usage view."""
        for w in self.root.winfo_children():
            w.destroy()
        geom = self.cfg.get("geometry", self.MAIN_GEOM)
        self.root.geometry(geom)
        self.root.title("Claude Usage")
        self._build_ui()
        self._refresh()

    # ------------------------------------------------------------------
    # Manual paste UI (Chrome / Other)
    # ------------------------------------------------------------------

    def _build_manual_paste_ui(self, can_cancel=True):
        frame = tk.Frame(self.root, bg=self.BG, padx=16, pady=12)
        frame.pack(fill="both", expand=True)

        tk.Label(frame, text="Paste cookie header from claude.ai", bg=self.BG, fg=self.TEXT,
                 font=("Segoe UI", 10, "bold"), anchor="w").pack(fill="x")

        steps = tk.Frame(frame, bg=self.BG)
        steps.pack(fill="x", pady=(2, 6))
        tk.Label(steps, text=(
            "1. Open claude.ai in your browser\n"
            "2. F12 > Network tab > reload page\n"
            "3. Click any request > Headers > cookie: > copy value"
        ), bg=self.BG, fg=self.DIM, font=("Segoe UI", 8), anchor="w",
                 justify="left").pack(side="left")

        open_btn = tk.Button(steps, text="Open\nclaude.ai", bg=self.BAR_BG, fg=self.TEXT,
                             font=("Segoe UI", 8), relief="flat", padx=8, pady=2,
                             command=lambda: webbrowser.open("https://claude.ai/settings/usage"))
        open_btn.pack(side="right", padx=(8, 0))

        self.key_entry = tk.Entry(frame, font=("Consolas", 9), width=50)
        self.key_entry.pack(fill="x", pady=(0, 6))
        self.key_entry.focus_set()

        self.setup_status = tk.Label(frame, text="", bg=self.BG, fg=self.RED, font=("Segoe UI", 9))
        self.setup_status.pack(fill="x")

        btn_row = tk.Frame(frame, bg=self.BG)
        btn_row.pack(fill="x", pady=(4, 0))

        btn = tk.Button(btn_row, text="Connect", bg=self.BLUE, fg="white",
                        font=("Segoe UI", 10, "bold"), relief="flat", padx=16, pady=4,
                        command=self._on_manual_connect)
        btn.pack(side="left")

        if can_cancel:
            back_btn = tk.Button(btn_row, text="Back", bg=self.BAR_BG, fg=self.DIM,
                                 font=("Segoe UI", 9), relief="flat", padx=12, pady=4,
                                 command=self._back_to_chooser)
            back_btn.pack(side="left", padx=(8, 0))

        self.root.bind("<Return>", lambda e: self._on_manual_connect())
        if can_cancel:
            self.root.bind("<Escape>", lambda e: self._back_to_chooser())

    def _on_manual_connect(self):
        raw = self.key_entry.get()
        cookies = sanitize_cookies(raw)
        if not cookies:
            self.setup_status.config(text="Please paste the cookie string.")
            return

        self.setup_status.config(text="Connecting...", fg=self.DIM)
        self.root.update()

        try:
            data, updated_cookies = api_request("/api/organizations", cookies)
            if not data or not isinstance(data, list) or len(data) == 0:
                self.setup_status.config(text="No organizations found.", fg=self.RED)
                return

            self.cookies = updated_cookies
            self.org_id = data[0].get("uuid", "")
            self.cfg["cookies"] = self.cookies
            self.cfg["org_id"] = self.org_id
            save_config(self.cfg)

            self._transition_to_main()

        except PermissionError as e:
            self.setup_status.config(text=str(e), fg=self.RED)
        except Exception as e:
            self.setup_status.config(text=f"Error: {e}", fg=self.RED)

    def _back_to_chooser(self):
        for w in self.root.winfo_children():
            w.destroy()
        self.root.resizable(False, False)
        self.root.geometry("340x280")
        self._build_browser_chooser()

    # ------------------------------------------------------------------
    # Main usage UI — compact horizontal grid layout
    # ------------------------------------------------------------------

    def _build_ui(self):
        self.root.resizable(True, True)
        self.root.minsize(self.MAIN_MIN_W, self.MAIN_MIN_H)

        main = tk.Frame(self.root, bg=self.BG, padx=10, pady=8)
        main.pack(fill="both", expand=True)

        # Grid: col0=label, col1=bar (stretches), col2=pct, col3=reset
        main.columnconfigure(1, weight=1)

        self.bars = {}
        configs = [
            ("session", "Session", self.BLUE),
            ("weekly", "Weekly", self.AMBER),
            ("sonnet", "Sonnet", self.GREEN),
        ]

        for row_idx, (key, label, color) in enumerate(configs):
            main.rowconfigure(row_idx, weight=1)

            lbl = tk.Label(main, text=label, bg=self.BG, fg=self.DIM,
                           font=("Segoe UI", 9), anchor="w", width=7)
            lbl.grid(row=row_idx, column=0, sticky="w", padx=(0, 6))

            bar_outer = tk.Frame(main, bg=self.BAR_BG, height=14)
            bar_outer.grid(row=row_idx, column=1, sticky="ew", pady=3)
            bar_outer.grid_propagate(False)

            bar_inner = tk.Frame(bar_outer, bg=color, height=14, width=0)
            bar_inner.place(x=0, y=0, relheight=1.0)

            pct_label = tk.Label(main, text="--", bg=self.BG, fg=self.TEXT,
                                 font=("Segoe UI", 9, "bold"), anchor="e", width=4)
            pct_label.grid(row=row_idx, column=2, sticky="e", padx=(6, 2))

            reset_label = tk.Label(main, text="", bg=self.BG, fg=self.DIMMER,
                                   font=("Segoe UI", 8), anchor="e", width=10)
            reset_label.grid(row=row_idx, column=3, sticky="e", padx=(2, 0))

            self.bars[key] = {
                "pct": pct_label,
                "bar_outer": bar_outer,
                "bar_inner": bar_inner,
                "reset": reset_label,
                "color": color,
            }

        # Separator
        sep_row = len(configs)
        sep = tk.Frame(main, bg=self.BAR_BG, height=1)
        sep.grid(row=sep_row, column=0, columnspan=4, sticky="ew", pady=(4, 2))

        # Footer
        footer_row = sep_row + 1
        gear_btn = tk.Label(main, text="Settings", bg=self.BG, fg="#666666",
                            font=("Segoe UI", 8, "underline"), cursor="hand2")
        gear_btn.grid(row=footer_row, column=0, columnspan=2, sticky="w")
        gear_btn.bind("<Button-1>", lambda e: self._show_settings())

        self.status_label = tk.Label(main, text="Loading...", bg=self.BG, fg=self.DIMMER,
                                     font=("Segoe UI", 8))
        self.status_label.grid(row=footer_row, column=2, columnspan=2, sticky="e")

        # Redraw bars on resize
        self.root.bind("<Configure>", lambda e: self._on_resize())

        # Save geometry on close
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_resize(self):
        """Recalculate bar fill widths after a window resize."""
        for info in self.bars.values():
            self.root.update_idletasks()
            outer_w = info["bar_outer"].winfo_width()
            if outer_w <= 1:
                continue
            pct_text = info["pct"].cget("text").rstrip("%")
            try:
                pct = float(pct_text)
            except ValueError:
                continue
            bar_w = int(outer_w * min(pct, 100) / 100)
            info["bar_inner"].place(x=0, y=0, relheight=1.0, width=bar_w)

    def _on_close(self):
        """Save window geometry before exit."""
        self.cfg["geometry"] = self.root.geometry()
        save_config(self.cfg)
        self.root.destroy()

    def _update_bar(self, key, utilization, resets_at):
        info = self.bars[key]
        pct = utilization if utilization is not None else 0
        info["pct"].config(text=f"{pct}%")

        self.root.update_idletasks()
        outer_w = info["bar_outer"].winfo_width()
        bar_w = int(outer_w * min(pct, 100) / 100) if outer_w > 1 else 0
        color = self.RED if pct > 80 else info["color"]
        info["bar_inner"].config(bg=color, width=bar_w)
        info["bar_inner"].place(x=0, y=0, relheight=1.0, width=bar_w)

        info["reset"].config(text=time_until(resets_at))

    def _toggle_topmost(self):
        self.topmost = not self.topmost
        self.root.attributes("-topmost", self.topmost)
        self.cfg["topmost"] = self.topmost
        save_config(self.cfg)

    def _show_settings(self):
        menu = tk.Menu(self.root, tearoff=0, bg=self.BAR_BG, fg=self.TEXT,
                       activebackground=self.BLUE, activeforeground="white",
                       font=("Segoe UI", 9))
        menu.add_command(label="Refresh now", command=self._refresh)
        check = "\u2713 " if self.topmost else "   "
        menu.add_command(label=f"{check}Always on top", command=self._toggle_topmost)
        menu.add_separator()
        menu.add_command(label="Switch account / re-paste cookies", command=self._logout)

        try:
            menu.tk_popup(self.root.winfo_rootx() + 10, self.root.winfo_rooty() + self.root.winfo_height() - 10)
        finally:
            menu.grab_release()

    def _logout(self):
        self._show_reauth()

    def _refresh(self):
        if self._refreshing:
            return
        self._refreshing = True

        try:
            if not self.org_id:
                data, self.cookies = api_request("/api/organizations", self.cookies)
                self.org_id = data[0]["uuid"]
                self.cfg["org_id"] = self.org_id
                self.cfg["cookies"] = self.cookies
                save_config(self.cfg)

            data, self.cookies = api_request(
                f"/api/organizations/{self.org_id}/usage", self.cookies
            )
            self.cfg["cookies"] = self.cookies
            save_config(self.cfg)

            fh = data.get("five_hour", {})
            self._update_bar("session", fh.get("utilization", 0), fh.get("resets_at"))

            sd = data.get("seven_day", {})
            self._update_bar("weekly", sd.get("utilization", 0), sd.get("resets_at"))

            sn = data.get("seven_day_sonnet") or {}
            self._update_bar("sonnet", sn.get("utilization", 0), sn.get("resets_at"))

            from datetime import datetime
            self.status_label.config(text=f"Updated {datetime.now().strftime('%H:%M:%S')}", fg=self.DIMMER)

        except PermissionError:
            self.cfg.pop("cookies", None)
            self.cookies = ""
            self.org_id = ""
            save_config(self.cfg)
            self._refreshing = False
            self._show_reauth()
            return
        except Exception as e:
            self.status_label.config(text=f"Error: {str(e)[:40]}", fg=self.RED)
        finally:
            self._refreshing = False

        self.root.after(REFRESH_MS, self._refresh)

    def _show_reauth(self):
        """Show the browser chooser with a Cancel button to return."""
        for w in self.root.winfo_children():
            w.destroy()
        self.root.resizable(False, False)
        self.root.geometry("340x310")
        self.root.title("Claude Usage \u2014 Reconnect")
        self._build_browser_chooser(can_cancel=bool(self.cookies))

    def _cancel_setup(self):
        for w in self.root.winfo_children():
            w.destroy()
        geom = self.cfg.get("geometry", self.MAIN_GEOM)
        self.root.geometry(geom)
        self.root.title("Claude Usage")
        self._build_ui()
        self._refresh()


if __name__ == "__main__":
    UsageWidget()
