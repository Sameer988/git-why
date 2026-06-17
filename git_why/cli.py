from __future__ import annotations

import click

from git_why.ai.base import ProviderError
from git_why.ai.prompt import build_prompt
from git_why.ai.router import VALID_PROVIDERS, provider_for
from git_why.display import console, render_analysis
from git_why.git_analyzer import GitAnalysisError, analyze_target


def _looks_like_windows_drive_path(target: str) -> bool:
    return len(target) >= 3 and target[1] == ":" and target[0].isalpha() and target[2] in "\\/"


def parse_target(target: str) -> tuple[str, int | None, int | None]:
    if not target or not target.strip():
        raise click.BadParameter("target must not be empty")

    cleaned = target.strip()
    search_from = 2 if _looks_like_windows_drive_path(cleaned) else 0
    selector_index = cleaned.rfind(":")
    has_line_selector = selector_index >= search_from
    if not has_line_selector:
        file_path = cleaned
        start = None
        end = None
    else:
        file_path = cleaned[:selector_index]
        selector = cleaned[selector_index + 1 :]
        if "-" in selector:
            start, end = selector.split("-", 1)
        else:
            start, end = selector, None

    if not file_path:
        raise click.BadParameter("file path must not be empty")

    if start is None:
        return file_path, None, None

    try:
        line_start = int(start)
        line_end = int(end) if end is not None else line_start
    except ValueError as exc:
        raise click.BadParameter("line numbers must be positive integers") from exc

    if line_start <= 0 or line_end <= 0:
        raise click.BadParameter("line numbers must be positive integers")
    if line_start > line_end:
        raise click.BadParameter("range start must be less than or equal to range end")
    return file_path, line_start, line_end


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.argument("target", required=True)
@click.option("--depth", default=15, show_default=True, type=click.IntRange(min=1))
@click.option("--context", "context_lines", default=8, show_default=True, type=click.IntRange(min=0))
@click.option(
    "--provider",
    default="auto",
    show_default=True,
    type=click.Choice(VALID_PROVIDERS, case_sensitive=False),
)
@click.option("--model", default=None, help="Override the selected provider model.")
@click.option("--verbose", "-v", is_flag=True, help="Show raw analysis context.")
def main(
    target: str,
    depth: int,
    context_lines: int,
    provider: str,
    model: str | None,
    verbose: bool,
) -> None:
    """Explain why code exists using local git history."""
    try:
        file_path, line_start, line_end = parse_target(target)
        with console.status("[bold cyan]Reading git history...[/bold cyan]", spinner="dots"):
            analysis = analyze_target(file_path, line_start, line_end, depth, context_lines)
        selected_provider = provider_for(provider)
        prompt = build_prompt(analysis)
        if selected_provider.name == "offline":
            explanation = selected_provider.explain(prompt, model=model, analysis=analysis)
        else:
            with console.status(
                f"[bold cyan]Asking {selected_provider.name}...[/bold cyan]", spinner="dots"
            ):
                explanation = selected_provider.explain(prompt, model=model, analysis=analysis)
        render_analysis(analysis, explanation, provider=selected_provider.name, verbose=verbose)
    except click.BadParameter:
        raise
    except ProviderError as exc:
        raise click.ClickException(str(exc)) from exc
    except GitAnalysisError as exc:
        raise click.ClickException(str(exc)) from exc


if __name__ == "__main__":
    main()
