# Contributing

Thanks for your interest in contributing!

## Bug Reports

Open a GitHub Issue with:
- What happened vs. what you expected
- Your OS and Python version
- Any error messages shown in the widget

## Feature Requests

Open an Issue with the `enhancement` label describing your use case.

## Pull Requests

1. Fork the repo
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make your changes (the app is a single file: `claude_usage.py`)
4. Test locally: `python claude_usage.py`
5. Submit a PR with a clear description

## Development Setup

```bash
git clone https://github.com/subradar/claude-usage-widget.git
cd claude-usage-widget
pip install -r requirements.txt
python claude_usage.py
```

## Code Style

- Follow PEP 8
- Keep it simple — this is intentionally a single-file tool
