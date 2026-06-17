from __future__ import annotations

import sys

from rich import box
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from git_why.git_analyzer import GitAnalysis, GitAnalysisError, read_target_lines

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

console = Console()

# Display label + accent color per provider. Colors are cosmetic only and
# degrade gracefully on terminals without truecolor support.
PROVIDER_STYLES: dict[str, tuple[str, str]] = {
    "claude": ("Claude", "#D97757"),
    "openai": ("OpenAI", "#74AA9C"),
    "gemini": ("Gemini", "#4C8BF5"),
    "openrouter": ("OpenRouter", "#8A63D2"),
    "ollama": ("Ollama", "#B0855A"),
    "offline": ("Offline", "#6E7681"),
}


def _target_label(analysis: GitAnalysis) -> str:
    if analysis.line_start is None or analysis.line_end is None:
        return analysis.file_path
    if analysis.line_start == analysis.line_end:
        return f"{analysis.file_path}:{analysis.line_start}"
    return f"{analysis.file_path}:{analysis.line_start}-{analysis.line_end}"


def _provider_badge(provider: str) -> Text:
    label, color = PROVIDER_STYLES.get(provider, (provider.title(), "#6E7681"))
    suffix = "  ·  offline / free, no network calls" if provider == "offline" else ""
    badge = Text(f" {label} ", style=f"bold white on {color}")
    if suffix:
        badge.append(suffix, style="dim on default")
    return badge


def _render_code_panel(analysis: GitAnalysis) -> Panel | None:
    try:
        shown_lines, start_line, highlighted = read_target_lines(
            analysis.file_path, analysis.line_start, analysis.line_end, analysis.context_lines
        )
    except GitAnalysisError:
        return None

    code = "\n".join(shown_lines)
    lexer = Syntax.guess_lexer(analysis.file_path, code=code)
    syntax = Syntax(
        code,
        lexer,
        theme="ansi_dark",
        line_numbers=True,
        start_line=start_line,
        highlight_lines=highlighted,
        word_wrap=False,
        indent_guides=True,
        background_color="default",
    )
    subtitle = None
    if analysis.line_start is None and len(shown_lines) >= 120:
        subtitle = "[dim]showing first 120 lines[/dim]"
    return Panel(
        syntax,
        title="[bold]Current code[/bold]",
        title_align="left",
        subtitle=subtitle,
        border_style="grey50",
        box=box.ROUNDED,
    )


def render_analysis(
    analysis: GitAnalysis,
    explanation: str,
    provider: str,
    verbose: bool = False,
) -> None:
    target = _target_label(analysis)

    console.print(Rule(f"[bold cyan]git-why[/bold cyan]  [white]{target}[/white]", style="grey50", align="left"))
    console.print(_provider_badge(provider))
    console.print()

    code_panel = _render_code_panel(analysis)
    if code_panel is not None:
        console.print(code_panel)
        console.print()

    table = Table(
        title=f"Commits analyzed ({len(analysis.commits)})",
        title_justify="left",
        box=box.SIMPLE_HEAVY,
        show_lines=False,
        row_styles=["", "dim"],
        header_style="bold cyan",
    )
    table.add_column("Commit", style="cyan", no_wrap=True)
    table.add_column("Date", no_wrap=True)
    table.add_column("Author")
    table.add_column("Message")
    for commit in analysis.commits[:6]:
        table.add_row(commit.short_hash, commit.date, commit.author, commit.message)
    if not analysis.commits:
        table.add_row("-", "-", "-", "No commits found")
    console.print(table)
    console.print()

    _, accent = PROVIDER_STYLES.get(provider, ("", "cyan"))
    console.print(
        Panel(
            Markdown(explanation),
            title="[bold]Explanation[/bold]",
            title_align="left",
            border_style=accent,
            box=box.ROUNDED,
        )
    )

    if verbose:
        console.print()
        console.print(
            Panel(
                analysis.raw_context,
                title="[dim]Raw context[/dim]",
                title_align="left",
                border_style="grey35",
                box=box.ROUNDED,
            )
        )
