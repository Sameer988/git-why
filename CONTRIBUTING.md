# Contributing

Thanks for helping improve `git-why`.

## Development Setup

```bash
pip install -e ".[dev]"
python -m pytest
```

## Guidelines

- Keep offline mode working without API keys or internet access.
- Do not make Claude, OpenAI, Gemini, OpenRouter, or Ollama required for basic use.
- Keep provider defaults centralized in `git_why/ai/defaults.py`.
- Prefer focused changes with tests for parser, provider routing, git analysis, and display behavior.
- Avoid committing generated files such as `dist/`, `build/`, `*.egg-info/`, `__pycache__/`, or `.pytest_cache/`.

## Release Checklist

- Run `python -m pytest`.
- Check `git-why --help`.
- Confirm README examples match current CLI behavior.
- Confirm no API keys, personal paths, or temporary test repositories are committed.
