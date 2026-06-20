from __future__ import annotations

import os

import click

from git_why.ai.base import ProviderError
from git_why.ai.prompt import build_prompt
from git_why.ai.router import VALID_PROVIDERS, provider_for
from git_why.display import console, render_analysis
from git_why.git_analyzer import GitAnalysisError, analyze_target


# ─── DefaultGroup ─────────────────────────────────────────────────────────────
# Routes `git-why <target>` to the `explain` subcommand transparently so the
# primary UX is unchanged, while still allowing `git-why completions` etc.

class _DefaultGroup(click.Group):
    """A Click Group that falls back to a default subcommand for unknown args."""

    default_cmd_name: str = "explain"

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        # If no args or the first arg looks like a flag/help, let Group handle it.
        if not args or args[0].startswith("-"):
            return super().parse_args(ctx, args)
        # If the first arg IS a known subcommand, let Group handle it normally.
        if args[0] in self.commands:
            return super().parse_args(ctx, args)
        # Otherwise, prepend the default subcommand name.
        args.insert(0, self.default_cmd_name)
        return super().parse_args(ctx, args)

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        return super().get_command(ctx, cmd_name) or super().get_command(ctx, self.default_cmd_name)


# ─── Target parsing ───────────────────────────────────────────────────────────

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
        start = end = None
    else:
        file_path = cleaned[:selector_index]
        selector = cleaned[selector_index + 1:]
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


# ─── File path completion ─────────────────────────────────────────────────────

def _complete_target(ctx: click.Context, param: click.Parameter, incomplete: str) -> list:
    from click.shell_completion import CompletionItem
    results = []
    try:
        base, _, _ = incomplete.rpartition(":")
        path_part = base if base else incomplete
        directory = os.path.dirname(path_part) or "."
        prefix = os.path.basename(path_part)
        for name in os.listdir(directory):
            if name.startswith(prefix):
                full = os.path.join(directory, name).lstrip("./")
                full_abs = os.path.join(directory, name)
                if os.path.isfile(full_abs):
                    results.append(CompletionItem(full, help="file"))
                elif os.path.isdir(full_abs):
                    results.append(CompletionItem(full + "/", help="dir"))
    except OSError:
        pass
    return results


# ─── explain command (primary UX) ─────────────────────────────────────────────

@click.command("explain", context_settings={"help_option_names": ["-h", "--help"]})
@click.argument("target", required=True, shell_complete=_complete_target)
@click.option("--depth", default=15, show_default=True, type=click.IntRange(min=1),
              help="Number of commits to inspect.")
@click.option("--context", "context_lines", default=8, show_default=True,
              type=click.IntRange(min=0), help="Lines of context around the target.")
@click.option(
    "--provider", default="auto", show_default=True,
    type=click.Choice(VALID_PROVIDERS, case_sensitive=False),
    help="AI provider to use for explanation.",
)
@click.option("--model", default=None, help="Override the selected provider model.")
@click.option("--verbose", "-v", is_flag=True, help="Show raw analysis context.")
@click.option(
    "--fetch-refs/--no-fetch-refs", default=True, show_default=True,
    help="Fetch PR/issue titles from GitHub/GitLab API (cached in git notes).",
)
def explain_cmd(
    target: str,
    depth: int,
    context_lines: int,
    provider: str,
    model: str | None,
    verbose: bool,
    fetch_refs: bool,
) -> None:
    """Explain why code exists using local git history."""
    try:
        file_path, line_start, line_end = parse_target(target)
        with console.status("[bold cyan]Reading git history...[/bold cyan]", spinner="dots"):
            analysis = analyze_target(
                file_path, line_start, line_end, depth, context_lines,
                fetch_refs=fetch_refs,
            )
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


# ─── completions command ──────────────────────────────────────────────────────

_SHELL_SNIPPETS: dict[str, tuple[str, str]] = {
    "bash": (
        'eval "$(_GIT_WHY_COMPLETE=bash_source git-why)"',
        "~/.bashrc",
    ),
    "zsh": (
        'eval "$(_GIT_WHY_COMPLETE=zsh_source git-why)"',
        "~/.zshrc",
    ),
    "fish": (
        "eval (env _GIT_WHY_COMPLETE=fish_source git-why)",
        "~/.config/fish/config.fish",
    ),
}


def _detect_shell() -> str | None:
    for name in ("fish", "zsh", "bash"):
        if name in os.environ.get("SHELL", ""):
            return name
    return None


@click.command("completions", context_settings={"help_option_names": ["-h", "--help"]})
@click.argument("shell", required=False, type=click.Choice(["bash", "zsh", "fish"]))
@click.option("--install", is_flag=True,
              help="Write the activation line directly to your shell config.")
def completions_cmd(shell: str | None, install: bool) -> None:
    """Print or install shell completion for git-why.

    \b
    Quick setup (add to your shell config and restart):
      bash:  eval "$(_GIT_WHY_COMPLETE=bash_source git-why)"
      zsh:   eval "$(_GIT_WHY_COMPLETE=zsh_source git-why)"
      fish:  eval (env _GIT_WHY_COMPLETE=fish_source git-why)

    \b
    Or let git-why write it for you:
      git-why completions --install
      git-why completions bash --install
    """
    detected = shell or _detect_shell()
    if detected is None:
        raise click.ClickException(
            "Could not detect your shell. "
            "Pass it explicitly: git-why completions bash|zsh|fish"
        )

    snippet, cfg = _SHELL_SNIPPETS[detected]

    if not install:
        console.print(f"\n[bold]Add this line to [cyan]{cfg}[/cyan]:[/bold]\n")
        console.print(f"  [green]{snippet}[/green]\n")
        console.print(f"[dim]Then restart your shell or: source {cfg}[/dim]")
        console.print(
            f"\n[dim]Or run [cyan]git-why completions {detected} --install[/cyan] "
            "to write it automatically.[/dim]"
        )
        return

    cfg_path = os.path.expanduser(cfg)
    try:
        existing = open(cfg_path, encoding="utf-8").read()
    except FileNotFoundError:
        existing = ""

    if snippet in existing:
        console.print(
            f"[yellow]Completion already installed in {cfg} — nothing to do.[/yellow]"
        )
        return

    with open(cfg_path, "a", encoding="utf-8") as f:
        f.write(f"\n# git-why shell completion\n{snippet}\n")

    console.print(f"[green]✓[/green] Installed completion → [cyan]{cfg}[/cyan]")
    console.print(f"[dim]Restart your shell or: source {cfg}[/dim]")


# ─── Entry point ──────────────────────────────────────────────────────────────

@click.group(
    cls=_DefaultGroup,
    invoke_without_command=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)
def main() -> None:
    """git-why — git blame tells you who. git-why tells you why.

    \b
    Usage:
      git-why src/auth.py          # whole file
      git-why src/auth.py:42       # single line
      git-why src/auth.py:40-55    # line range

    \b
    Shell completion:
      git-why completions --install
    """


main.add_command(explain_cmd)
main.add_command(completions_cmd)


if __name__ == "__main__":
    main()
