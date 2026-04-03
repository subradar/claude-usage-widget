"""
Claude Usage Monitor — Standalone Desktop Widget
A tiny always-on-top window showing Claude session/weekly usage.
No browser required. Auto-refreshes every 60 seconds.

First run: paste the full cookie header from any claude.ai request.
  (DevTools > Network > click a request > Headers > cookie value)
The sessionKey auto-renews on each API call.

Requires: pip install curl_cffi
"""

__version__ = "1.0.0"

import tkinter as tk
import json
import os
import sys
import re
import stat
import webbrowser
from curl_cffi import requests as curl_requests

# Hide console window when launched from .bat / shortcut (Windows only)
if sys.platform == "win32":
    import ctypes
    ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.json")
REFRESH_MS = 60_000  # 60 seconds


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
        # Restrict file permissions on Unix (owner read/write only)
        if sys.platform != "win32":
            os.chmod(CONFIG_FILE, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def sanitize_cookies(raw):
    """Strip newlines and control characters from cookie input."""
    return re.sub(r'[\x00-\x1f\x7f]', '', raw).strip()


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
        # Use plain string replace to avoid regex injection from cookie values
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
        self.root.resizable(False, False)
        self.root.geometry("240x245")
        self.root.overrideredirect(False)

        if not self.cookies:
            self._prompt_cookies()
            return

        self._build_ui()
        self._refresh()
        self.root.mainloop()

    def _prompt_cookies(self):
        self.root.geometry("420x250")
        self.root.title("Claude Usage \u2014 Setup")
        self._build_setup_ui()
        self.root.mainloop()

    def _on_connect(self):
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

            for w in self.root.winfo_children():
                w.destroy()
            self.root.geometry("240x245")
            self.root.title("Claude Usage")
            self._build_ui()
            self._refresh()

        except PermissionError as e:
            self.setup_status.config(text=str(e), fg=self.RED)
        except Exception as e:
            self.setup_status.config(text=f"Error: {e}", fg=self.RED)

    def _build_ui(self):
        main = tk.Frame(self.root, bg=self.BG, padx=12, pady=10)
        main.pack(fill="both", expand=True)

        self.bars = {}
        configs = [
            ("session", "Session (5h)", self.BLUE),
            ("weekly", "Weekly (7d)", self.AMBER),
            ("sonnet", "Sonnet (7d)", self.GREEN),
        ]

        for key, label, color in configs:
            row = tk.Frame(main, bg=self.BG)
            row.pack(fill="x", pady=(0, 8))

            header = tk.Frame(row, bg=self.BG)
            header.pack(fill="x")
            tk.Label(header, text=label, bg=self.BG, fg=self.DIM,
                     font=("Segoe UI", 9), anchor="w").pack(side="left")
            pct_label = tk.Label(header, text="--", bg=self.BG, fg=self.TEXT,
                                 font=("Segoe UI", 10, "bold"), anchor="e")
            pct_label.pack(side="right")

            bar_outer = tk.Frame(row, bg=self.BAR_BG, height=12)
            bar_outer.pack(fill="x", pady=(2, 0))
            bar_outer.pack_propagate(False)

            bar_inner = tk.Frame(bar_outer, bg=color, height=12, width=0)
            bar_inner.place(x=0, y=0, relheight=1.0)

            reset_label = tk.Label(row, text="", bg=self.BG, fg=self.DIMMER,
                                   font=("Segoe UI", 8), anchor="w")
            reset_label.pack(fill="x")

            self.bars[key] = {
                "pct": pct_label,
                "bar_outer": bar_outer,
                "bar_inner": bar_inner,
                "reset": reset_label,
                "color": color,
            }

        sep = tk.Frame(main, bg=self.BAR_BG, height=1)
        sep.pack(fill="x", pady=(2, 4))

        footer = tk.Frame(main, bg=self.BG)
        footer.pack(fill="x")

        gear_btn = tk.Label(footer, text="Settings", bg=self.BG, fg="#666666",
                            font=("Segoe UI", 8, "underline"), cursor="hand2")
        gear_btn.pack(side="left")
        gear_btn.bind("<Button-1>", lambda e: self._show_settings())

        self.status_label = tk.Label(footer, text="Loading...", bg=self.BG, fg=self.DIMMER,
                                     font=("Segoe UI", 8))
        self.status_label.pack(side="right")

    def _update_bar(self, key, utilization, resets_at):
        info = self.bars[key]
        pct = utilization if utilization is not None else 0
        info["pct"].config(text=f"{pct}%")

        # Update bar width
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
        """Show a small settings popup menu."""
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
        """Show setup UI without clearing cookies yet (cleared on new connect)."""
        self._show_reauth(can_cancel=True)

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

    def _show_reauth(self, can_cancel=False):
        for w in self.root.winfo_children():
            w.destroy()
        self.root.geometry("420x200")
        self.root.title("Claude Usage \u2014 Session Expired" if not can_cancel else "Claude Usage \u2014 Switch Account")
        self._build_setup_ui(can_cancel=can_cancel)

    def _cancel_setup(self):
        """Return to metrics view with existing cookies."""
        for w in self.root.winfo_children():
            w.destroy()
        self.root.geometry("240x245")
        self.root.title("Claude Usage")
        self._build_ui()
        self._refresh()

    def _build_setup_ui(self, can_cancel=False):
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
                        command=self._on_connect)
        btn.pack(side="left")

        if can_cancel:
            cancel_btn = tk.Button(btn_row, text="Cancel", bg=self.BAR_BG, fg=self.DIM,
                                   font=("Segoe UI", 9), relief="flat", padx=12, pady=4,
                                   command=self._cancel_setup)
            cancel_btn.pack(side="left", padx=(8, 0))

        self.root.bind("<Return>", lambda e: self._on_connect())
        if can_cancel:
            self.root.bind("<Escape>", lambda e: self._cancel_setup())



if __name__ == "__main__":
    UsageWidget()
