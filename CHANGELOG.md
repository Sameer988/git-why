# Changelog

All notable changes to this project are documented here.

## [0.1.0] - 2026-06-17

Initial release.

### Added

- Core CLI: `git-why FILE`, `git-why FILE:LINE`, `git-why FILE:START-END` — explains why code exists by reading local git blame and log history.
- Offline mode (`--provider offline`): a heuristic, non-AI explanation built from commit messages, authorship, and diffs. No API key, no network calls, always available.
- AI provider support: Claude, OpenAI, Gemini, OpenRouter, and Ollama, selectable via `--provider` or auto-detected via `auto` (the default) based on which API keys/services are present.
- `--depth`, `--context`, `--model`, and `--verbose` flags for tuning how much history is pulled in and how it's displayed.
- Rich terminal output: syntax-highlighted code panel with the target line(s) highlighted, a commit table, a color-coded provider badge, and a loading spinner while git history is read or an AI provider is queried.
- Full test suite (24 tests) covering target parsing, git analysis helpers, the offline explainer, and provider auto-detection.
- GitHub Actions CI matrix across Ubuntu/Windows/macOS and Python 3.10–3.13.

### Notes

- PyPI publishing has not happened yet; install via `pip install -e .` from a local checkout.
- Offline explanations are heuristic, not AI-generated — treat them as a grounded starting point, not a definitive historical record.
