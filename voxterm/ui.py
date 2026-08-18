"""
ui.py — Rich terminal UI

All display logic lives here. Nothing else in the codebase prints directly.
Callers use context managers for animated states and plain functions for
one-shot output.

Design principles:
  - One consistent palette, never garish
  - Animations via Live + custom renderable classes (frame advances on each render)
  - Rounded panels with interior padding throughout
  - Syntax-highlighted commands in every context they appear
  - transient=True on Live blocks so animations erase themselves cleanly
"""

from __future__ import annotations

import itertools
from contextlib import contextmanager

from rich import box
from rich.align import Align
from rich.console import Console, ConsoleOptions, RenderResult
from rich.live import Live
from rich.padding import Padding
from rich.panel import Panel
from rich.rule import Rule
from rich.spinner import Spinner
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

# ---------------------------------------------------------------------------
# Palette — all colour decisions live here
# ---------------------------------------------------------------------------
_ACCENT  = "#A78BFA"   # violet  — brand colour, headers
_CYAN    = "#67E8F9"   # cyan    — listening / active state
_GREEN   = "#34D399"   # emerald — success
_YELLOW  = "#FCD34D"   # amber   — medium risk
_RED     = "#F87171"   # rose    — high risk / error
_DIM     = "grey46"    # muted   — secondary text
_WHITE   = "grey93"    # near-white — primary text

# Box style used on every panel
_BOX = box.ROUNDED

console = Console(highlight=False)


# ---------------------------------------------------------------------------
# Animated state renderable classes
# Each advances its own frame counter on every render — no external threads.
# Combined with Live(refresh_per_second=N, transient=True) this gives smooth,
# self-erasing animations.
# ---------------------------------------------------------------------------

class _WaveRenderable:
    """
    Audio waveform bars that animate left-to-right.
    Used for the "listening" state.
    """
    _FRAMES = [
        "▁▂▃▄▅▄▃▂",
        "▂▃▄▅▆▅▄▃",
        "▃▄▅▆▇▆▅▄",
        "▄▅▆▇█▇▆▅",
        "▃▄▅▆▇▆▅▄",
        "▂▃▄▅▆▅▄▃",
        "▁▂▃▄▅▄▃▂",
        "▁▁▂▃▄▃▂▁",
    ]

    def __init__(self):
        self._cycle = itertools.cycle(self._FRAMES)

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        frame = next(self._cycle)
        yield Text.assemble(
            ("  ", ""),
            (frame, f"bold {_CYAN}"),
            ("   ", ""),
            ("listening", f"bold {_CYAN}"),
            ("  ", ""),
        )


class _SpinnerRenderable:
    """
    Dot spinner with a label. Used for transcribing / thinking states.
    """
    _DOTS = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, label: str, colour: str):
        self._label = label
        self._colour = colour
        self._cycle = itertools.cycle(self._DOTS)

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        dot = next(self._cycle)
        yield Text.assemble(
            ("  ", ""),
            (dot, f"bold {self._colour}"),
            ("  ", ""),
            (self._label, self._colour),
            ("  ", ""),
        )


# ---------------------------------------------------------------------------
# Animated context managers
# ---------------------------------------------------------------------------

@contextmanager
def listening():
    """
    Show an animated audio waveform while waiting for the user to speak.

    Usage:
        with ui.listening():
            wav_path = audio.record_until_silence()
    """
    with Live(
        _WaveRenderable(),
        refresh_per_second=8,
        transient=True,
        console=console,
    ):
        yield


@contextmanager
def transcribing():
    """
    Show a spinner while Whisper processes the audio clip.

    Usage:
        with ui.transcribing():
            text = transcribe.transcribe(wav_path)
    """
    with Live(
        _SpinnerRenderable("transcribing", _ACCENT),
        refresh_per_second=12,
        transient=True,
        console=console,
    ):
        yield


@contextmanager
def thinking():
    """
    Show a spinner while the LLM generates the command.

    Usage:
        with ui.thinking():
            result = translate.translate(transcript, context)
    """
    with Live(
        _SpinnerRenderable("thinking", _ACCENT),
        refresh_per_second=12,
        transient=True,
        console=console,
    ):
        yield


@contextmanager
def summarising():
    """Show a spinner while the LLM summarises long output (13G)."""
    with Live(
        _SpinnerRenderable("summarising", _DIM),
        refresh_per_second=12,
        transient=True,
        console=console,
    ):
        yield


# ---------------------------------------------------------------------------
# One-shot display functions
# ---------------------------------------------------------------------------

def show_banner():
    """App header — printed once at startup."""
    console.print()
    console.print(Rule(Text("  VoxTerm  ", style=f"bold {_ACCENT}"), style=_DIM))
    console.print()


def show_transcript(text: str):
    """Display what the user said, after the waveform clears."""
    console.print()
    console.print(
        Panel(
            Text(text, style=f"bold {_WHITE}"),
            title=Text("you said", style=_DIM),
            border_style=_DIM,
            box=_BOX,
            padding=(0, 2),
        )
    )
    console.print()


def show_output(stdout: str, stderr: str, success: bool, summary: str = ""):
    """
    Display command output. Green border on success, red on failure.

    If summary is provided it's shown prominently above the raw output.
    Long output (>10 lines) is shown collapsed to 5 lines with a line count.
    """
    if summary:
        console.print()
        console.print(f"  [{_ACCENT}]summary:[/{_ACCENT}]  [{_WHITE}]{summary}[/{_WHITE}]")

    if stdout:
        console.print(
            Panel(
                Text(stdout, style=_WHITE),
                title=Text("output", style=_GREEN if success else _RED),
                border_style=_GREEN if success else _RED,
                box=_BOX,
                padding=(0, 2),
            )
        )

    if stderr and not success:
        console.print(
            Panel(
                Text(stderr, style=_RED),
                title=Text("stderr", style=_RED),
                border_style=_RED,
                box=_BOX,
                padding=(0, 2),
            )
        )

    if not stdout and not stderr:
        if success:
            console.print(f"  [{_GREEN}]✓[/{_GREEN}]  [grey60]done[/grey60]")
        else:
            console.print(f"  [{_RED}]✗[/{_RED}]  [grey60]failed with no output[/grey60]")

    console.print()


def show_error(message: str):
    """Display a top-level error (LLM failure, mic error, etc.)."""
    console.print()
    console.print(
        Panel(
            Text(message, style=_RED),
            title=Text("error", style=f"bold {_RED}"),
            border_style=_RED,
            box=_BOX,
            padding=(0, 2),
        )
    )
    console.print()


def show_clarification(question: str):
    """Display a clarification question from the LLM (13B)."""
    console.print()
    console.print(
        Panel(
            Text(question, style=f"bold {_YELLOW}"),
            title=Text("clarification needed", style=_YELLOW),
            border_style=_YELLOW,
            box=_BOX,
            padding=(0, 2),
        )
    )
    console.print(f"  [{_DIM}]listening for your answer...[/{_DIM}]")
    console.print()


def show_explanation(explanation: str):
    """Display an LLM explanation of the last command (13F)."""
    console.print()
    console.print(
        Panel(
            Text(explanation, style=_WHITE),
            title=Text("explanation", style=f"bold {_ACCENT}"),
            border_style=_ACCENT,
            box=_BOX,
            padding=(0, 2),
        )
    )
    console.print()


def show_error_recovery(suggested_fix: str):
    """Display a suggested fix after a failed command (13H)."""
    console.print(f"\n  [{_YELLOW}]command failed — diagnosing...[/{_YELLOW}]")
    console.print()


def show_cd_wrapper_hint(path: str):
    """Warn once when cd worked in-process but the shell wrapper isn't active."""
    console.print(
        f"\n  [{_YELLOW}]cd[/{_YELLOW}] [{_DIM}]changed to[/{_DIM}] [{_WHITE}]{path}[/{_WHITE}] "
        f"[{_DIM}](only inside voxterm — your terminal hasn't moved)[/{_DIM}]"
    )
    console.print(
        f"  [{_DIM}]to propagate cd to your shell, add to ~/.zshrc:[/{_DIM}]\n"
        f"  [{_CYAN}]source /Users/soorya/terminaltalker/voxterm.sh[/{_CYAN}]\n"
        f"  [{_DIM}]then use[/{_DIM}] [{_WHITE}]vt[/{_WHITE}] [{_DIM}]instead of[/{_DIM}] [{_WHITE}]python main.py[/{_WHITE}]\n"
    )


def show_cancelled():
    console.print(f"\n  [{_DIM}]cancelled[/{_DIM}]\n")


def show_undo_unavailable():
    console.print(f"\n  [{_DIM}]nothing to undo[/{_DIM}]\n")


def show_alias_saved(name: str):
    console.print(f"\n  [{_GREEN}]✓[/{_GREEN}]  saved alias [{_WHITE}]{name}[/{_WHITE}]\n")


def show_alias_prompt() -> str:
    """Ask the user if they want to save a repeated command as an alias."""
    console.print()
    return console.input(
        f"  [{_DIM}]you've run this a few times — save as alias? "
        f"(name or enter to skip):[/{_DIM}]  "
    ).strip()


def show_history(rows: list[tuple]):
    """
    Render the command history as a styled table.
    Each row: (timestamp, transcript, command, risk, success)
    """
    if not rows:
        console.print(f"\n  [{_DIM}]no history yet[/{_DIM}]\n")
        return

    table = Table(
        box=_BOX,
        border_style=_DIM,
        header_style=f"bold {_ACCENT}",
        show_lines=True,
        padding=(0, 1),
        title=Text("command history", style=f"bold {_WHITE}"),
        title_justify="left",
    )

    table.add_column("time",     style=_DIM,    width=17,  no_wrap=True)
    table.add_column("you said", style=_WHITE,  max_width=32)
    table.add_column("command",  style=_CYAN,   max_width=44)
    table.add_column("risk",     justify="center", width=8)
    table.add_column("",         justify="center", width=3)

    _risk_style = {"low": _GREEN, "medium": _YELLOW, "high": _RED}

    for ts, transcript, command, risk, success in rows:
        risk_colour = _risk_style.get(risk or "", _DIM)
        ok_mark = Text("✓", style=f"bold {_GREEN}") if success else Text("✗", style=_RED)
        table.add_row(
            (ts or "")[:16],
            transcript or "",
            command or "",
            Text(risk or "", style=risk_colour),
            ok_mark,
        )

    console.print()
    console.print(Padding(table, pad=(0, 0, 1, 2)))


def show_aliases(aliases: dict[str, str]):
    """Render saved aliases as a table."""
    if not aliases:
        console.print(f"\n  [{_DIM}]no aliases saved yet[/{_DIM}]\n")
        return

    table = Table(
        box=_BOX,
        border_style=_DIM,
        header_style=f"bold {_ACCENT}",
        padding=(0, 1),
        title=Text("saved aliases", style=f"bold {_WHITE}"),
        title_justify="left",
    )
    table.add_column("name",    style=f"bold {_WHITE}", width=20)
    table.add_column("command", style=_CYAN)

    for name, cmd in aliases.items():
        table.add_row(name, cmd)

    console.print()
    console.print(Padding(table, pad=(0, 0, 1, 2)))


# ---------------------------------------------------------------------------
# Quick visual demo: python ui.py
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import time

    show_banner()

    # Animated states
    console.print(f"  [{_DIM}]— animated states (1s each) —[/{_DIM}]\n")

    with listening():
        time.sleep(1.5)

    with transcribing():
        time.sleep(1.2)

    with thinking():
        time.sleep(1.2)

    # Transcript
    show_transcript("move all the PDFs from downloads to documents")

    # Output variants
    show_output("total 48\n-rw-r--r--  1 soorya  staff   420 Apr  4 03:12 audio.py\n-rw-r--r--  1 soorya  staff  1820 Apr  4 03:12 translate.py", "", True)
    show_output("", "git: 'psh' is not a git command. Did you mean push?", False)
    show_output("", "", True)
    show_output("", "", False)

    # Error
    show_error("Ollama is not running. Start it with: ollama serve")

    # History table
    show_history([
        ("2026-04-04T03:10:00", "list my files",          "ls -la",           "low",    1),
        ("2026-04-04T03:11:00", "make a new folder",       "mkdir test-output", "low",   1),
        ("2026-04-04T03:12:00", "push my changes",         "git push",          "medium", 0),
        ("2026-04-04T03:13:00", "delete the dist folder",  "rm -rf dist/",      "high",  1),
    ])

    # Aliases table
    show_aliases({
        "clean":  "rm -rf node_modules && npm install",
        "deploy": "npm run build && netlify deploy --prod",
    })

    show_cancelled()
    show_undo_unavailable()
