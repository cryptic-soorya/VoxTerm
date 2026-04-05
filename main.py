"""
main.py — CLI entry point

Wires every module together behind a Click CLI.

Usage:
    python main.py                  # listen, translate, confirm, run
    python main.py --dry-run        # full pipeline, no execution
    python main.py --offline        # force Ollama
    python main.py --cloud          # force Gemini
    python main.py history          # show last 20 commands
    python main.py undo             # reverse last reversible command
    python main.py alias list       # show saved aliases
    python main.py alias save NAME  # save last command as alias NAME
"""

import sys
from dotenv import load_dotenv

load_dotenv()

import click

import os

import ui
from audio import record_until_silence
from transcribe import transcribe
from translate import translate, check_plugins
from context import get_context
from safety import confirm, final_risk
from executor import run, run_steps, _CD_SIGNAL_FILE
from history import init as init_db, log, recent
from undo import push as push_undo, pop as pop_undo, can_undo
from aliases import match as match_alias, check_for_repeat, save as save_alias, load as load_aliases, delete as delete_alias


# ---------------------------------------------------------------------------
# cd helper — updates os.getcwd() so subsequent LLM calls get the right CWD
# ---------------------------------------------------------------------------

def _handle_cd(output: dict):
    """
    If a cd command succeeded, update the process CWD so that the next
    context.get_context() call reflects the new location.
    The shell wrapper reads _CD_SIGNAL_FILE to actually cd in the parent shell.
    """
    if output.get("cd"):
        try:
            os.chdir(output["cd"])
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Main listen command
# ---------------------------------------------------------------------------

@click.group(invoke_without_command=True)
@click.option("--dry-run",  is_flag=True, help="Show commands without running them.")
@click.option("--offline",  is_flag=True, help="Force Ollama; error if not running.")
@click.option("--cloud",    is_flag=True, help="Force Gemini free API.")
@click.pass_context
def cli(ctx, dry_run, offline, cloud):
    """vocterm — voice-controlled terminal assistant."""
    if ctx.invoked_subcommand is not None:
        return

    init_db()
    ui.show_banner()

    # ── 1. Record ─────────────────────────────────────────────────────────
    with ui.listening():
        try:
            wav_path = record_until_silence()
        except RuntimeError as exc:
            ui.show_error(str(exc))
            sys.exit(1)

    # ── 2. Transcribe ─────────────────────────────────────────────────────
    with ui.transcribing():
        try:
            transcript = transcribe(wav_path)
        except Exception as exc:
            ui.show_error(f"transcription failed: {exc}")
            sys.exit(1)

    if not transcript:
        ui.show_error("no speech detected — try again")
        sys.exit(0)

    ui.show_transcript(transcript)

    # ── 3. Resolve command (plugins → aliases → LLM) ──────────────────────
    context_str = get_context()
    result = None

    plugin_cmd = check_plugins(transcript)
    if plugin_cmd:
        result = {
            "command": plugin_cmd,
            "steps": None,
            "risk": "medium",
            "explanation": "plugin command",
            "destructive": False,
            "inverse_command": None,
        }

    if result is None:
        alias_cmd = match_alias(transcript)
        if alias_cmd:
            result = {
                "command": alias_cmd,
                "steps": None,
                "risk": "medium",
                "explanation": "saved alias",
                "destructive": False,
                "inverse_command": None,
            }

    if result is None:
        with ui.thinking():
            result = translate(
                transcript,
                context_str,
                force_offline=offline,
                force_cloud=cloud,
            )

    # ── 4. Handle LLM errors ──────────────────────────────────────────────
    if "error" in result:
        ui.show_error(result["error"])
        sys.exit(1)

    # ── 5. Safety gate + confirmation ─────────────────────────────────────
    if not confirm(result, dry_run=dry_run):
        ui.show_cancelled()
        return

    if dry_run:
        return

    # ── 6. Execute ────────────────────────────────────────────────────────
    if result.get("steps"):
        outputs = run_steps(result["steps"])
        for output in outputs:
            _handle_cd(output)
            ui.show_output(output["stdout"], output["stderr"], output["success"])
        success  = all(o["success"] for o in outputs)
        cmd_str  = " && ".join(result["steps"])
        out_text = "\n".join(o["stdout"] for o in outputs if o["stdout"])
    else:
        output   = run(result["command"])
        _handle_cd(output)
        push_undo(result.get("inverse_command"))
        success  = output["success"]
        cmd_str  = result["command"]
        out_text = output["stdout"]
        ui.show_output(output["stdout"], output["stderr"], output["success"])

    # ── 7. Log to history ─────────────────────────────────────────────────
    log(transcript, cmd_str, result.get("risk", "low"), success, out_text)

    # ── 8. Offer alias if request is repeated ─────────────────────────────
    if success and check_for_repeat(transcript):
        name = ui.show_alias_prompt()
        if name:
            save_alias(name, cmd_str)
            ui.show_alias_saved(name)


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

@cli.command()
def undo():
    """Reverse the last reversible command."""
    if not can_undo():
        ui.show_undo_unavailable()
        return

    cmd = pop_undo()
    result = {
        "command": cmd,
        "steps": None,
        "risk": "medium",
        "explanation": "undo last command",
        "destructive": False,
        "inverse_command": None,
    }

    if confirm(result):
        output = run(cmd)
        ui.show_output(output["stdout"], output["stderr"], output["success"])


@cli.command(name="history")
def history_cmd():
    """Show the last 20 commands."""
    init_db()
    ui.show_history(recent(20))


@cli.group()
def alias():
    """Manage saved command aliases."""
    pass


@alias.command(name="list")
def alias_list():
    """Show all saved aliases."""
    ui.show_aliases(load_aliases())


@alias.command(name="save")
@click.argument("name")
def alias_save(name):
    """Save the last command from history as alias NAME."""
    init_db()
    rows = recent(1)
    if not rows:
        ui.show_error("no commands in history yet")
        return
    cmd = rows[0][2]
    save_alias(name, cmd)
    ui.show_alias_saved(name)
    ui.console.print(f"  [grey46]command:[/grey46]  {cmd}\n")


@alias.command(name="delete")
@click.argument("name")
def alias_delete(name):
    """Delete a saved alias by NAME."""
    if delete_alias(name):
        ui.console.print(f"\n  [grey46]deleted alias[/grey46] [grey93]{name}[/grey93]\n")
    else:
        ui.show_error(f"no alias named '{name}'")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cli()
