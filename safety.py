"""
safety.py — risk gate + confirmation UI

The LLM's risk assessment is a suggestion. The hardcoded patterns here are law.
Even if the LLM returns "low" for `rm -rf`, the gate forces it to HIGH.

Risk levels:
  low    → runs immediately, no prompt
  medium → shows command + explanation, Y/n prompt
  high   → full warning panel, must type "yes" in full

dry_run → shows everything, runs nothing regardless of risk.
"""

import sys
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

console = Console()

# ---------------------------------------------------------------------------
# Hardcoded force-HIGH patterns
# These override the LLM's risk assessment unconditionally.
# Checked against the full command string (or all steps joined).
# ---------------------------------------------------------------------------
_FORCE_HIGH: list[str] = [
    "rm ",
    "rm\t",
    "sudo ",
    "chmod ",
    "chown ",
    " -rf",
    "-rf ",
    " -r ",
    "-r\t",
    " --recursive",
    "> /",       # redirect writes to system paths
    "mkfs",      # format a filesystem
    ":(){:|:&}", # fork bomb pattern
]

# Patterns that touch the home directory root (e.g. rm ~/file but not rm ~/projects/foo)
import re, os
_HOME = os.path.expanduser("~")


def _touches_home_root(cmd: str) -> bool:
    """
    True if the command targets a file directly in ~/ (not a subdirectory).
    e.g. `rm ~/important.txt` → True, `rm ~/projects/foo` → False
    """
    # Match ~ or $HOME followed by / and a filename (no second /)
    pattern = rf'(?:~|{re.escape(_HOME)})/[^/\s]+'
    return bool(re.search(pattern, cmd))


def final_risk(result: dict) -> str:
    """
    Return the final risk level after applying hardcoded overrides.
    Public so ui.py and tests can call it directly.
    """
    llm_risk = str(result.get("risk", "high")).lower()

    # Collect all command text to check against.
    cmd = result.get("command") or ""
    steps = result.get("steps") or []
    all_cmds = cmd + " " + " ".join(steps)

    for pattern in _FORCE_HIGH:
        if pattern in all_cmds:
            return "high"

    if _touches_home_root(all_cmds):
        return "high"

    return llm_risk if llm_risk in ("low", "medium", "high") else "high"


def _build_cmd_display(result: dict) -> str:
    """Format the command or steps list for display."""
    if result.get("steps"):
        return "\n".join(
            f"  {i + 1}. {s}" for i, s in enumerate(result["steps"])
        )
    return result.get("command", "")


def _render_command(cmd_display: str, style: str) -> Text:
    """Return a Rich Text object with the command coloured appropriately."""
    t = Text(cmd_display)
    t.stylize(style)
    return t


def confirm(result: dict, dry_run: bool = False) -> bool:
    """
    Show the appropriate confirmation UI and return True if execution should proceed.

    Args:
        result:   validated dict from translate.translate()
        dry_run:  if True, shows UI but always returns False (never executes)

    Returns:
        True  → caller should execute the command
        False → caller should abort
    """
    risk = final_risk(result)
    explanation = result.get("explanation", "no explanation provided")
    cmd_display = _build_cmd_display(result)

    # ── Dry-run ──────────────────────────────────────────────────────────────
    if dry_run:
        console.print(Panel(
            f"[dim]{cmd_display}[/dim]\n\n[dim]{explanation}[/dim]",
            title="[dim]dry run — would execute[/dim]",
            border_style="dim",
        ))
        return False

    # ── Low risk: run immediately, no prompt ──────────────────────────────────
    if risk == "low":
        console.print(f"[dim]› {cmd_display}[/dim]")
        return True

    # ── Medium risk: show panel, Y/n ─────────────────────────────────────────
    if risk == "medium":
        console.print(Panel(
            Syntax(cmd_display, "bash", theme="monokai", word_wrap=True),
            title="[yellow]command to run[/yellow]",
            subtitle=f"[dim]{explanation}[/dim]",
            border_style="yellow",
        ))
        try:
            answer = console.input("[yellow]run this? \\[Y/n] [/yellow]").strip().lower()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]cancelled[/dim]")
            return False
        return answer in ("", "y", "yes")

    # ── High risk: full warning, must type "yes" ──────────────────────────────
    if risk == "high":
        console.print(Panel(
            Syntax(cmd_display, "bash", theme="monokai", word_wrap=True),
            title="[bold red]⚠ destructive command[/bold red]",
            subtitle=f"[red]{explanation}[/red]",
            border_style="red",
        ))
        try:
            answer = console.input('[red]type "yes" to confirm, anything else cancels: [/red]').strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]cancelled[/dim]")
            return False
        return answer == "yes"

    return False


# ---------------------------------------------------------------------------
# Quick smoke test: python safety.py
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import json

    print("=== safety.py smoke test ===\n")

    cases = [
        # (description, result_dict, expected_final_risk)
        ("ls -la",
         {"command": "ls -la", "risk": "low", "explanation": "list files"},
         "low"),
        ("mkdir foo (LLM says low, should stay low)",
         {"command": "mkdir foo", "risk": "low", "explanation": "make dir"},
         "low"),
        ("git push (LLM says medium)",
         {"command": "git push", "risk": "medium", "explanation": "push commits"},
         "medium"),
        ("rm file.txt (LLM says low → forced HIGH)",
         {"command": "rm file.txt", "risk": "low", "explanation": "delete file"},
         "high"),
        ("sudo apt install (LLM says medium → forced HIGH)",
         {"command": "sudo apt install vim", "risk": "medium", "explanation": "install"},
         "high"),
        ("chmod 755 script.sh (LLM says low → forced HIGH)",
         {"command": "chmod 755 script.sh", "risk": "low", "explanation": "chmod"},
         "high"),
        ("steps with rm (LLM says medium → forced HIGH)",
         {"command": None, "steps": ["ls", "rm -rf node_modules"], "risk": "medium", "explanation": "clean"},
         "high"),
        (f"touch {_HOME}/test.txt (touches home root → forced HIGH)",
         {"command": f"touch {_HOME}/test.txt", "risk": "low", "explanation": "touch"},
         "high"),
        (f"rm ~/projects/foo/bar.txt (subdir of home → stays LOW)",
         {"command": "rm ~/projects/foo/bar.txt", "risk": "low", "explanation": "rm subdir"},
         "high"),  # still forced HIGH because rm is in _FORCE_HIGH
    ]

    all_pass = True
    for desc, result, expected in cases:
        got = final_risk(result)
        status = "PASS" if got == expected else "FAIL"
        if status == "FAIL":
            all_pass = False
        print(f"  [{status}] {desc}")
        if status == "FAIL":
            print(f"         expected={expected!r}, got={got!r}")

    print()
    if all_pass:
        print("All risk override tests: PASS")
    else:
        print("Some tests FAILED")
        sys.exit(1)

    print()
    print("--- Interactive demo (Ctrl+C to skip any) ---")
    demos = [
        {"command": "ls -la", "risk": "low", "explanation": "list all files with details"},
        {"command": "git push origin main", "risk": "medium", "explanation": "push commits to remote"},
        {"command": "rm -rf dist/", "risk": "low", "explanation": "delete dist folder"},  # forced HIGH
    ]
    for d in demos:
        print(f"\nRisk input: {d['risk']!r} → final: {final_risk(d)!r}")
        try:
            result = confirm(d, dry_run="--dry-run" in sys.argv)
            print(f"confirm() returned: {result}")
        except KeyboardInterrupt:
            print(" skipped")
