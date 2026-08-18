"""
executor.py — shell command execution with output capture

Runs approved commands via /bin/zsh with full stdout/stderr capture.
Never called directly — always gated through safety.confirm() first.

Key design:
- shell=True + executable="/bin/zsh": supports pipes, globs, aliases,
  and zsh-specific syntax the user might rely on.
- timeout: prevents runaway commands from hanging the tool forever.
- run_steps(): aborts the entire sequence on first failure — never
  continues a half-broken multi-step pipeline.
"""

import subprocess
import os
import re
from pathlib import Path

DEFAULT_TIMEOUT = int(os.getenv("VOXTERM_EXEC_TIMEOUT", "30"))  # seconds

# Shell wrapper reads this file after each run to pick up any cd request.
# Placed in $TMPDIR (user-private on macOS, e.g. /var/folders/.../T/) rather
# than /tmp (world-writable), so other users on the machine can't write a
# crafted path to it and redirect the shell's working directory.
_CD_SIGNAL_FILE = Path(os.getenv("TMPDIR", "/tmp")) / ".voxterm_cd"

# Output longer than this many lines gets an LLM-generated summary (13G).
SUMMARISE_THRESHOLD_LINES = 10


def should_summarise(output: str) -> bool:
    """True if output is long enough to warrant an LLM summary."""
    return bool(output) and output.count("\n") >= SUMMARISE_THRESHOLD_LINES


def _extract_cd_target(command: str) -> str | None:
    """
    If the command is purely a `cd`, return the resolved target path.
    Returns None for anything that isn't a plain cd invocation.

    Handles: cd, cd ~, cd ~/foo, cd /abs/path, cd $HOME/foo
    Does NOT intercept cd that's part of a larger pipeline (cd foo && ls).
    """
    stripped = command.strip()
    # Reject anything that's part of a pipeline or command chain.
    if any(op in stripped for op in ("&&", "||", ";", "|")):
        return None
    m = re.fullmatch(r'cd(?:\s+(.+))?', stripped)
    if not m:
        return None
    raw = (m.group(1) or "~").strip().strip("'\"")
    expanded = os.path.expanduser(os.path.expandvars(raw))
    return str(Path(expanded).resolve())


def run(command: str, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """
    Run a single shell command in /bin/zsh.

    Args:
        command: the shell command string to execute
        timeout: max seconds to wait before killing the process

    Returns:
        {
            "command":    the command that was run,
            "stdout":     captured standard output (stripped),
            "stderr":     captured standard error (stripped),
            "returncode": integer exit code,
            "success":    True if returncode == 0,
        }
    """
    # cd is a shell built-in — it only affects the child process, not the
    # parent shell. Intercept it: resolve the path, signal the shell wrapper,
    # and return success without spawning a subprocess.
    cd_target = _extract_cd_target(command)
    if cd_target is not None:
        if os.path.isdir(cd_target):
            _CD_SIGNAL_FILE.write_text(cd_target)
            os.chdir(cd_target)  # update process CWD immediately so subsequent steps see the new directory
            return {
                "command": command,
                "stdout": cd_target,
                "stderr": "",
                "returncode": 0,
                "success": True,
                "cd": cd_target,   # extra key — main.py uses this to update context CWD
            }
        else:
            return {
                "command": command,
                "stdout": "",
                "stderr": f"cd: {cd_target}: No such file or directory",
                "returncode": 1,
                "success": False,
            }

    # SECURITY NOTE: shell=True means the safety gate in safety.py checks the
    # command *string*, but the shell interprets it. Shell encoding tricks like
    # $'rm\x20-rf' or $(rm ...) can bypass substring pattern checks. The
    # _FORCE_HIGH list in safety.py now blocks "$(" and "`" to catch the most
    # common substitution forms, but shell=True is inherently a wide surface.
    # Never call this function without safety.confirm() having returned True.
    try:
        result = subprocess.run(
            command,
            shell=True,
            executable="/bin/zsh",
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "command": command,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "returncode": result.returncode,
            "success": result.returncode == 0,
        }
    except subprocess.TimeoutExpired:
        return {
            "command": command,
            "stdout": "",
            "stderr": f"command timed out after {timeout}s",
            "returncode": -1,
            "success": False,
        }
    except Exception as exc:
        return {
            "command": command,
            "stdout": "",
            "stderr": f"executor error: {exc}",
            "returncode": -1,
            "success": False,
        }


def run_steps(steps: list[str], timeout: int = DEFAULT_TIMEOUT) -> list[dict]:
    """
    Run a sequence of commands one at a time.
    Stops immediately on the first failure — never continues a broken pipeline.

    Args:
        steps:   list of shell command strings
        timeout: per-command timeout in seconds

    Returns:
        List of result dicts (same shape as run()). May be shorter than
        `steps` if an early command failed.
    """
    results = []
    for step in steps:
        result = run(step, timeout=timeout)
        results.append(result)
        if not result["success"]:
            break
    return results


# ---------------------------------------------------------------------------
# Quick smoke test: python executor.py
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    print("=== executor.py smoke test ===\n")
    all_pass = True

    def check(desc, result, expect_success, expect_in_stdout="", expect_in_stderr=""):
        global all_pass
        ok = result["success"] == expect_success
        if expect_in_stdout and expect_in_stdout not in result["stdout"]:
            ok = False
        if expect_in_stderr and expect_in_stderr not in result["stderr"]:
            ok = False
        status = "PASS" if ok else "FAIL"
        if not ok:
            all_pass = False
        print(f"  [{status}] {desc}")
        if not ok:
            print(f"         stdout={result['stdout']!r}")
            print(f"         stderr={result['stderr']!r}")
            print(f"         returncode={result['returncode']}")

    # Basic success
    r = run("echo hello")
    check("echo hello → success + stdout", r, True, expect_in_stdout="hello")

    # Non-zero exit code
    r = run("exit 1")
    check("exit 1 → failure", r, False)

    # Stderr capture
    r = run("echo err >&2")
    check("stderr capture", r, True, expect_in_stderr="err")

    # Pipe support (needs shell=True)
    r = run("echo 'hello world' | tr '[:lower:]' '[:upper:]'")
    check("pipe support", r, True, expect_in_stdout="HELLO WORLD")

    # Zsh glob (needs zsh)
    r = run("echo *.py | grep -c py")
    check("zsh glob expands", r, True)

    # Timeout
    r = run("sleep 10", timeout=1)
    check("timeout kills command", r, False, expect_in_stderr="timed out")

    # run_steps: all succeed
    results = run_steps(["echo a", "echo b", "echo c"])
    ok = len(results) == 3 and all(r["success"] for r in results)
    print(f"  [{'PASS' if ok else 'FAIL'}] run_steps all succeed (3 results)")
    if not ok:
        all_pass = False

    # run_steps: stops at first failure
    results = run_steps(["echo a", "exit 1", "echo c"])
    ok = len(results) == 2 and not results[-1]["success"]
    print(f"  [{'PASS' if ok else 'FAIL'}] run_steps stops at failure (2 results, not 3)")
    if not ok:
        all_pass = False

    print()
    if all_pass:
        print("All executor tests: PASS")
    else:
        print("Some tests FAILED")
        sys.exit(1)
