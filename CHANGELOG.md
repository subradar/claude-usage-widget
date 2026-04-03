# Changelog

All notable changes to this project will be documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/).

## [1.2.0] - 2026-04-03

### Added
- Responsive horizontal layout: label, bar, %, and reset time on one line per metric
- Window is now resizable — bars stretch to fill available width
- Window size and position saved to config.json and restored on next launch

### Changed
- Compact default size (420x120) — much smaller desktop footprint
- Bar labels shortened (Session, Weekly, Sonnet) for horizontal fit
- Updated cookie expiry docs: sessions last 12+ hours with regular use, not 2-4 hours as originally documented

## [1.1.0] - 2026-04-03

### Added
- Browser chooser dialog on first launch — pick Firefox, Safari, or manual paste
- Firefox auto-detect: extracts claude.ai cookies from cookies.sqlite automatically (all platforms)
- Safari auto-detect: parses binary cookie store on macOS (experimental)
- "Back" button in manual paste view to return to browser chooser

### Changed
- Setup flow redesigned: browser chooser is now the first screen instead of manual paste
- Settings > "Switch account" now returns to browser chooser (can re-pick method)
- Bumped version to 1.1.0

## [1.0.0] - 2026-04-03

### Added
- Always-on-top desktop widget showing Claude.ai usage limits
- Three usage bars: Session (5h), Weekly (7d), Sonnet (7d)
- Auto-refresh every 60 seconds
- Cookie-based authentication with automatic sessionKey renewal
- Settings menu: manual refresh, always-on-top toggle, account switching
- Cross-platform support (Windows, macOS, Linux)
- Config file permission hardening on Unix systems
- Cookie input sanitization
- Network timeout protection (15s)
- Graceful recovery from corrupted config files
