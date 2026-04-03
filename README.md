# Claude Usage Monitor

A tiny always-on-top desktop widget that shows your Claude.ai session and weekly usage limits in real-time. No browser tab required.

![Python](https://img.shields.io/badge/python-3.10%2B-green)
![License](https://img.shields.io/badge/license-MIT-orange)

## What It Does

Displays three usage bars that auto-refresh every 60 seconds:

- **Session (5h)** - Your rolling 5-hour usage limit
- **Weekly (7d)** - Your rolling 7-day usage limit
- **Sonnet (7d)** - Your rolling 7-day Sonnet usage limit

Each bar shows utilization percentage, a color-coded progress bar (turns red above 80%), and a countdown timer until the limit resets.

## Requirements

- **Python 3.10+** with tkinter (included in standard Python installs)
- **curl_cffi** - Required for Cloudflare TLS fingerprint impersonation
- No additional dependencies for Firefox/Safari auto-detect (uses Python stdlib)

### Platform Notes

- **Windows**: Console window is automatically hidden on startup. Fully supported.
- **macOS / Linux**: Works with tkinter. The console-hide feature is skipped automatically. On some Linux distros you may need to install tkinter separately (e.g. `sudo apt install python3-tk`).

## Installation

```bash
git clone https://github.com/subradar/claude-usage-widget.git
cd claude-usage-widget
pip install -r requirements.txt
```

## Usage

```bash
python claude_usage.py
```

Or with `pythonw` on Windows to avoid the console window entirely:

```bash
pythonw claude_usage.py
```

### First Run Setup

On first launch, you'll see a browser chooser with three options:

#### Firefox (auto-detect)
Cookies are extracted automatically from Firefox's local cookie database. Just make sure you're logged into [claude.ai](https://claude.ai) in Firefox first. No manual steps required.

- Works on Windows, macOS, and Linux
- Reads from `cookies.sqlite` (copied to a temp file to avoid lock conflicts)
- Firefox does **not** encrypt cookies at rest, so no master password is needed

#### Safari (auto-detect, macOS only)
Cookies are parsed automatically from Safari's binary cookie store. Log into [claude.ai](https://claude.ai) in Safari first.

- macOS only (button is disabled on other platforms)
- May require Full Disk Access permission for your terminal/Python in System Settings > Privacy & Security
- Experimental — please report issues

#### Chrome / Other (manual paste)
For Chrome, Edge, Brave, Arc, and any other Chromium-based browser, cookies must be pasted manually from DevTools:

1. Open [claude.ai](https://claude.ai) in your browser and log in
2. Open DevTools (`F12`) > **Network** tab
3. Reload the page
4. Click any request > **Headers** tab > find the `cookie:` request header > copy the full value
5. Paste it into the widget and click **Connect**

<details>
<summary>Why can't Chrome cookies be auto-detected?</summary>

Chrome 127+ (July 2024) uses App-Bound Encryption for cookies. The encryption key is locked inside Chrome's elevation service and cannot be read by external tools. This affects all Chromium-based browsers (Edge, Brave, Arc, etc.).
</details>

### Cookie Renewal

The `sessionKey` cookie auto-renews on each API call and typically lasts weeks. Cloudflare cookies (`cf_clearance`) have a nominal expiry of 2-4 hours, but the widget's regular API calls appear to keep them alive much longer — sessions lasting 12+ hours without re-authentication have been observed.

When cookies do eventually expire:

- **Firefox users**: Click Settings > Switch account, then click "Firefox (auto-detect)" again. Fresh cookies are pulled automatically.
- **Chrome/manual users**: Re-paste cookies from DevTools.

### Settings

Click **Settings** in the bottom-left corner:

- **Refresh now** - Trigger an immediate data refresh
- **Always on top** - Toggle whether the widget stays above other windows
- **Switch account** - Return to browser chooser to reconnect or switch methods

### Why `curl_cffi`?

Cloudflare's bot protection on claude.ai checks TLS fingerprints. Python's default TLS stack gets blocked with HTTP 403 even with valid cookies. `curl_cffi` impersonates Chrome's exact TLS handshake to bypass this.

## Configuration

The widget saves its state to `config.json` (auto-generated, gitignored):

- Session cookies (auto-renewed on each API call)
- Organization ID (auto-detected)
- Window preferences (always-on-top)

## Troubleshooting

### "Auth failed (HTTP 403)" error
Your Cloudflare cookies have expired. Use Settings > Switch account to reconnect via your browser of choice.

### Firefox auto-detect: "No claude.ai cookies found"
Make sure you've opened [claude.ai](https://claude.ai) in Firefox and logged in. The cookies only exist after a successful login.

### Firefox auto-detect: "Firefox profile directory not found"
Firefox may be installed in a non-standard location, or you may be using a Snap/Flatpak version with a different profile path. Use the manual paste method instead.

### Safari auto-detect fails with permission error
On macOS, go to System Settings > Privacy & Security > Full Disk Access and grant access to your terminal app (Terminal, iTerm2, etc.) or Python.

### Widget shows 0% on all bars
The API response format may have changed, or the initial fetch failed silently. Click **Settings > Refresh now**. If it persists, reconnect.

### `ModuleNotFoundError: No module named 'curl_cffi'`
Make sure you installed into the correct Python environment: `pip install curl_cffi`. If you have multiple Python versions, use `python -m pip install curl_cffi` with the same `python` you use to launch the widget.

### Widget won't start (config error)
If `config.json` becomes corrupted, delete it and restart. The widget will show the setup screen.

### Linux: `No module named '_tkinter'`
Install tkinter for your distro: `sudo apt install python3-tk` (Debian/Ubuntu) or `sudo dnf install python3-tkinter` (Fedora).

## Security

- **Cookies are stored locally** in `config.json` in the same directory as the script. This file is gitignored and never committed.
- On Unix systems, `config.json` is automatically restricted to owner-only permissions (`chmod 600`).
- Cookie input is sanitized to strip control characters before use.
- Firefox cookies are read from a temporary copy of the database — the original is never modified.
- No data is sent anywhere except `claude.ai` — there is no telemetry, analytics, or third-party communication.

## Disclaimer

This tool uses claude.ai's internal, undocumented API. It is not affiliated with or endorsed by Anthropic. The API could change at any time, which may break this tool. Use at your own discretion.

## Limitations

- **Cloudflare cookies eventually expire**, requiring reconnection (typically lasts 12+ hours with regular use)
- **Chrome/Chromium auto-detect not possible** due to App-Bound Encryption
- **Unofficial API** - Uses claude.ai's internal API which could change without notice
- **Font rendering** - Uses Segoe UI (Windows default). Falls back to system default on other platforms.

## License

MIT
