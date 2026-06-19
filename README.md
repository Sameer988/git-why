# git-why

[![CI](https://github.com/Sameer988/git-why/actions/workflows/ci.yml/badge.svg)](https://github.com/Sameer988/git-why/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/git-why.svg)](https://pypi.org/project/git-why/)
[![Stars](https://img.shields.io/github/stars/Sameer988/git-why.svg?style=flat)](https://github.com/Sameer988/git-why/stargazers)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![MIT License](https://img.shields.io/badge/License-MIT-yellow.svg)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

**`git blame` tells you who broke it. `git-why` tells you why it's there in the first place.**

It's 11pm. You've found a six-line guard clause that looks paranoid, maybe even wrong. `git blame` says Dave wrote it three years ago. Dave doesn't work here anymore. Do you delete it and hope, or burn twenty minutes in `git log -p` praying the commit message isn't just "fix"?

`git-why` does that archaeology for you — in under a second, completely offline, no API key, no setup beyond `pip install`.

```bash
git-why src/auth.py:42
```

![git-why demo](assets/demo.gif)

It reads the actual commits and diffs around that line and reconstructs the story nobody wrote down anywhere else — or hands the same context to Claude/GPT/Gemini/Ollama/OpenRouter if you want a richer, AI-narrated version.

⭐ **If this saves you a Slack message to a teammate who left the company two years ago, consider starring it** — it helps other people stumbling through the same archaeology find this instead of reinventing it.

## Install

```bash
pip install git-why
```

Or with an AI provider extra:

```bash
pip install "git-why[claude]"    # Anthropic Claude
pip install "git-why[openai]"    # OpenAI GPT
pip install "git-why[gemini]"    # Google Gemini
pip install "git-why[all]"       # all providers
```

## Quick Start

```bash
git-why src/auth.py
git-why src/auth.py:42
git-why src/auth.py:42-60
git-why src/auth.py:42 --depth 30
git-why src/auth.py:42 --context 15
git-why src/auth.py:42 --verbose
git-why src/auth.py:42 --provider offline
```

Targets use `FILE`, `FILE:LINE`, or `FILE:START-END`. See the demo above for what the output actually looks like.

## Offline And Free Mode

Offline mode is always available:

```bash
git-why src/auth.py:42 --provider offline
```

It reads the current file, runs local git commands, summarizes commit messages and diffs, and produces a non-AI markdown explanation. It does not need an API key and does not make internet calls.

The default provider is `auto`. Auto tries configured AI providers first and always falls back to offline.

## Provider Setup

Provider order in `auto` mode:

1. Claude when `ANTHROPIC_API_KEY` exists and `anthropic` is installed
2. OpenAI when `OPENAI_API_KEY` exists and `openai` is installed
3. Gemini when `GEMINI_API_KEY` exists and `google-genai` is installed
4. OpenRouter when `OPENROUTER_API_KEY` exists
5. Ollama when local Ollama is running
6. Offline

Claude:

```bash
pip install "git-why[claude]"
set ANTHROPIC_API_KEY=your-key
git-why src/auth.py:42 --provider claude
```

OpenAI:

```bash
pip install "git-why[openai]"
set OPENAI_API_KEY=your-key
git-why src/auth.py:42 --provider openai
```

Gemini:

```bash
pip install "git-why[gemini]"
set GEMINI_API_KEY=your-key
git-why src/auth.py:42 --provider gemini
```

OpenRouter:

```bash
set OPENROUTER_API_KEY=your-key
git-why src/auth.py:42 --provider openrouter
```

Ollama:

```bash
ollama serve
ollama pull qwen2.5-coder
git-why src/auth.py:42 --provider ollama
```

PowerShell examples use `set` for brevity. Use your shell's normal environment variable syntax if needed.

## Models

Override the model with `--model`:

```bash
git-why src/auth.py:42 --provider openai --model gpt-5.4-mini
git-why src/auth.py:42 --provider ollama --model qwen2.5-coder
```

Default models:

| Provider | Default model |
| --- | --- |
| Claude | `claude-sonnet-4-6` |
| OpenAI | `gpt-5.4-mini` |
| Gemini | `gemini-3.5-flash` |
| OpenRouter | `openrouter/free` |
| Ollama | `qwen2.5-coder` |

Model names change over time. Defaults are centralized in `git_why/ai/defaults.py`. If a model fails, pass `--model`.

## Windows PATH Note

On Windows, `pip install -e .` may install `git-why.exe` into a Scripts directory that is not on PATH, for example:

```text
%LOCALAPPDATA%\Programs\Python\Python313\Scripts
```

Add that Scripts directory to PATH, or run the script with its full path.

## Examples

Explain a whole file:

```bash
git-why src/auth.py
```

Explain one line:

```bash
git-why src/auth.py:42 --provider offline
```

Explain a range with more history:

```bash
git-why src/auth.py:42-60 --depth 30
```

Show raw git context:

```bash
git-why src/auth.py:42 --verbose
```

## Development

```bash
pip install -e ".[dev]"
python -m pytest
```

## Limitations

- Offline explanations are heuristic and based only on local git history.
- Deleted or renamed files depend on what git can resolve from the current working tree.
- Whole-file mode caps the displayed current code preview.
- Binary files are detected and shown as a placeholder rather than raw bytes; commit history still comes from `git log`, but line-level `git blame` is skipped since line numbers aren't meaningful for binary content.
- AI providers require their respective SDKs, keys, or local services only when explicitly selected or available in `auto`.

## Roadmap

- Add CI for automated PyPI publishing on release tags (done — `.github/workflows/publish.yml`).
- Improve provider response parsing and error reporting.
- Add PR/issue linking when commit messages reference GitHub/GitLab/Jira.
- Smarter diff heuristics for repos with low-quality commit messages.
- VS Code extension — inline "Why?" on any line.
- Shell completions for zsh/bash/fish.
