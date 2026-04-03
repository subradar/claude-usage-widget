# Changelog

All notable changes to this project will be documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/).

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
