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

You need to copy the `cookie:` header from your browser's DevTools. This works in **any browser** — Chrome, Firefox, Edge, Brave, Arc, etc.

1. Open [claude.ai](https://claude.ai) in your browser and log in
2. Open DevTools (`F12`) > **Network** tab
3. Reload the page
4. Click any request to `claude.ai` > **Headers** tab > find the `cookie:` request header > copy the full value
5. Paste it into the widget and click **Connect**

<details>
<summary>Browser-specific tips</summary>

- **Chrome / Edge / Brave / Arc**: F12 > Network > click any request > Headers > scroll to `cookie:` under Request Headers
- **Firefox**: F12 > Network > click any request > Headers > scroll to `Cookie` under Request Headers. (Firefox shows it as `Cookie` with a capital C — both formats work.)
- **Safari**: Develop menu > Show Web Inspector > Network > click a request > Headers > look for `Cookie`

</details>

The widget will auto-detect your organization and start showing usage data.

### Why Manual Cookie Paste?

Modern browsers encrypt their cookie storage, making automatic extraction impossible for external tools. The manual paste from DevTools is the only reliable cross-browser method. You'll need to re-paste every few hours when the Cloudflare cookies (`cf_clearance`) expire.

### Settings

Click **Settings** in the bottom-left corner:

- **Refresh now** - Trigger an immediate data refresh
- **Always on top** - Toggle whether the widget stays above other windows
- **Switch account** - Paste cookies for a different account

### Why `curl_cffi`?

Cloudflare's bot protection on claude.ai checks TLS fingerprints. Python's default TLS stack gets blocked with HTTP 403 even with valid cookies. `curl_cffi` impersonates Chrome's exact TLS handshake to bypass this.

## Configuration

The widget saves its state to `config.json` (auto-generated, gitignored):

- Session cookies (auto-renewed on each API call)
- Organization ID (auto-detected)
- Window preferences (always-on-top)

## Troubleshooting

### "Auth failed (HTTP 403)" error
Your Cloudflare cookies have expired. This happens every 2-4 hours. Paste fresh cookies from Chrome DevTools.

### Widget shows 0% on all bars
The API response format may have changed, or the initial fetch failed silently. Click **Settings > Refresh now**. If it persists, re-paste cookies.

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
- No data is sent anywhere except `claude.ai` — there is no telemetry, analytics, or third-party communication.

## Disclaimer

This tool uses claude.ai's internal, undocumented API. It is not affiliated with or endorsed by Anthropic. The API could change at any time, which may break this tool. Use at your own discretion.

## Limitations

- **Cloudflare cookies expire** every 2-4 hours, requiring a fresh paste
- **Unofficial API** - Uses claude.ai's internal API which could change without notice
- **Font rendering** - Uses Segoe UI (Windows default). Falls back to system default on other platforms.

## License

MIT
