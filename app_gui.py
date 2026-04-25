"""
app_gui.py — rumps menu bar app for voxterm

This is the GUI entry point used by PyInstaller when building the distributable
.app bundle. It wraps the same backend as main.py (audio → transcribe → translate
→ safety → executor) but surfaces everything through macOS-native UI:

  • Menu bar icon with state labels (idle / listening / thinking)
  • rumps.alert() dialogs for medium/high-risk confirmation
  • macOS notifications for command output
  • Preferences window for Gemini API key (no .env editing needed)
  • Global hotkey: ⌘⇧Space to trigger a listen cycle from anywhere

LLM mode: GUI users are unlikely to have Ollama installed, so the default
is flipped here — Gemini first (if GEMINI_API_KEY is set), Ollama as fallback.
The Preferences menu lets users paste their free key from aistudio.google.com.
"""

from __future__ import annotations

import fcntl
import multiprocessing
import os
import sys
import tempfile
import threading
from pathlib import Path

# True when launched from a terminal (stdout is a tty).
# In terminal mode we use Rich/stdin I/O so commands and output are visible
# there, just like main.py — menus/notifications are still shown alongside.
_IS_TERMINAL = sys.stdout.isatty()

# ---------------------------------------------------------------------------
# PyInstaller freeze_support — MUST come before any other code.
# When ctranslate2/faster-whisper spawns multiprocessing workers in a frozen
# app, each worker re-runs the executable. freeze_support() intercepts those
# re-launches and routes the worker to the correct target instead of starting
# a new menu bar app. Without this being first, every transcription call
# spawns another full VoxTerm instance.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # Explicit spawn prevents ctranslate2 from using fork (unsafe on macOS).
    multiprocessing.set_start_method("spawn", force=True)
    multiprocessing.freeze_support()

# Prevent ctranslate2 from spawning OpenMP threads that PyInstaller mistakes
# for new processes and re-launches the app to handle.
os.environ.setdefault("OMP_NUM_THREADS", "1")

# ---------------------------------------------------------------------------
# Single-instance lock — prevents multiple copies running simultaneously.
# fcntl.flock() is automatically released when the process exits (even on
# SIGKILL), so there are no stale-lock issues.
# ---------------------------------------------------------------------------
_LOCK_PATH = Path(tempfile.gettempdir()) / "voxterm.lock"
_lock_fh = None


def _acquire_single_instance_lock() -> None:
    """Exit immediately if another VoxTerm instance is already running."""
    global _lock_fh
    _lock_fh = open(_LOCK_PATH, "w")
    try:
        fcntl.flock(_lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        import rumps as _rumps
        _rumps.alert(
            title="VoxTerm already running",
            message="VoxTerm is already in your menu bar. Look for the 🎙 icon.",
        )
        sys.exit(0)
    _lock_fh.write(str(os.getpid()))
    _lock_fh.flush()


# Load .env before anything else so translate.py picks up the key.
_ENV_PATH = Path(__file__).parent / ".env"

from dotenv import load_dotenv, set_key  # noqa: E402
load_dotenv(dotenv_path=_ENV_PATH)

import rumps  # noqa: E402

# ---------------------------------------------------------------------------
# Heavy backend modules are imported lazily (inside _run_pipeline_inner).
# Importing them here would load ctranslate2 at startup, which:
#   a) adds ~1-2s to the time before the icon appears in the menu bar, and
#   b) causes ctranslate2's internal worker processes to fire before
#      freeze_support() can intercept them in the frozen app, resulting in
#      the "multiple clones" cascade the user sees in Activity Monitor.
# ---------------------------------------------------------------------------

# context and safety are lightweight — safe to import at module level.
from context import get_context  # noqa: E402
from safety import final_risk    # noqa: E402

# AppHelper.callAfter dispatches a callable onto the main run loop, which is
# how rumps.alert / rumps.Window must be invoked — Cocoa UI is not thread-safe.
try:
    from PyObjCTools import AppHelper as _AppHelper  # noqa: E402
except ImportError:
    _AppHelper = None


def _on_main(fn, *args, **kwargs):
    """Schedule fn(*args, **kwargs) on the main run loop. Safe from any thread."""
    if _AppHelper is not None:
        _AppHelper.callAfter(lambda: fn(*args, **kwargs))
    else:
        # Last-resort fallback: call directly. May still work if we are on main.
        fn(*args, **kwargs)


def _alert_sync(**kwargs) -> int:
    """
    Run rumps.alert on the main run loop and BLOCK the caller until the
    user dismisses the dialog. Returns 1 for OK, 0 for cancel.

    Required because rumps.alert is a Cocoa modal — calling it from a
    background thread either crashes or returns garbage. The pipeline
    runs on a worker thread, so every confirmation goes through here.
    """
    if threading.current_thread() is threading.main_thread():
        return rumps.alert(**kwargs)

    holder = {"value": 0}
    done = threading.Event()

    def runner():
        try:
            holder["value"] = rumps.alert(**kwargs)
        finally:
            done.set()

    if _AppHelper is not None:
        _AppHelper.callAfter(runner)
    else:
        runner()
    done.wait()
    return holder["value"]


def _window_sync(**kwargs):
    """Same pattern as _alert_sync but for rumps.Window (text input)."""
    if threading.current_thread() is threading.main_thread():
        return rumps.Window(**kwargs).run()

    holder = {"value": None}
    done = threading.Event()

    def runner():
        try:
            holder["value"] = rumps.Window(**kwargs).run()
        finally:
            done.set()

    if _AppHelper is not None:
        _AppHelper.callAfter(runner)
    else:
        runner()
    done.wait()
    return holder["value"]

# ---------------------------------------------------------------------------
# Try to import pynput for global hotkey — graceful fallback if not installed
# ---------------------------------------------------------------------------
try:
    from pynput import keyboard as _kb
    _PYNPUT_AVAILABLE = True
except ImportError:
    _PYNPUT_AVAILABLE = False


# ---------------------------------------------------------------------------
# Icons (text-based — works without .icns during development)
# ---------------------------------------------------------------------------
_ICON_IDLE       = "🎙"
_ICON_LISTENING  = "🔴"
_ICON_THINKING   = "⏳"
_ICON_ERROR      = "⚠️"

# ---------------------------------------------------------------------------
# Risk colours for alert dialogs
# ---------------------------------------------------------------------------
_RISK_EMOJI = {"low": "🟢", "medium": "🟡", "high": "🔴"}

# ---------------------------------------------------------------------------
# Active `say` process — killed before starting a new one so overlapping
# speech calls don't garble each other.
# ---------------------------------------------------------------------------
_say_proc = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _alert_error(title: str, message: str):
    """Show an error as a modal alert that can't be missed or dismissed silently.
    Always dispatched onto the main run loop — rumps.alert touches Cocoa UI."""
    _on_main(rumps.alert, title=title, message=message[:512] if message else "")


def _notify(title: str, message: str, subtitle: str = ""):
    """
    Send a macOS notification for non-critical results (success, output).
    For errors use _alert_error() — notifications require OS permission
    and may be silently dropped if the user hasn't granted it yet.
    """
    rumps.notification(
        title=title,
        subtitle=subtitle,
        message=message[:256] if message else "",
        sound=False,
    )


def _open_linked_terminal():
    """
    Open Terminal.app with a session ready to run voxterm interactively.
    Falls back to a guidance alert if Terminal.app cannot be controlled.

    The linked terminal shares state with the menu bar app via the on-disk
    history DB, aliases JSON, and cd-signal file in $TMPDIR — both processes
    point at the same data directory.
    """
    import shlex
    import subprocess

    # Detect whether we're running from source or the frozen .app bundle.
    # When frozen, sys.frozen is set by PyInstaller. The bundled Python
    # executable can't be re-invoked as a regular interpreter, so we tell
    # the user to use the system Python in this case.
    is_frozen = getattr(sys, "frozen", False)

    repo_root = Path(__file__).resolve().parent
    voxterm_sh = repo_root / "voxterm.sh"
    main_py = repo_root / "main.py"

    if is_frozen or not voxterm_sh.exists() or not main_py.exists():
        _on_main(
            rumps.alert,
            title="Open VoxTerm in Terminal",
            message=(
                "To use VoxTerm in your existing terminal alongside the menu "
                "bar app, clone the repo and run:\n\n"
                "  cd ~/voxterm\n"
                "  source voxterm.sh\n"
                "  vt\n\n"
                "Both processes share history, aliases, and cd state."
            ),
        )
        return

    # Use the same Python interpreter that's running this script so the
    # spawned terminal has the right venv — no manual activation needed.
    python_bin = shlex.quote(sys.executable)
    repo_quoted = shlex.quote(str(repo_root))

    # Compose the shell command Terminal.app will execute. We:
    #   1. cd into the repo
    #   2. source voxterm.sh so `vt` is defined (cd propagation)
    #   3. start an interactive zsh; user runs `vt` whenever they want
    #
    # VOXTERM_SHELL_WRAPPER=1 disables the cd-wrapper hint inside main.py
    # because voxterm.sh handles cd in this session.
    inner = (
        f"cd {repo_quoted} && "
        f"export VOXTERM_PYTHON={python_bin} && "
        f"export VOXTERM_SHELL_WRAPPER=1 && "
        f"source ./voxterm.sh && "
        f'echo "VoxTerm linked terminal — type \\`vt\\` to start a voice command." && '
        f"exec zsh -i"
    )

    osa = (
        'tell application "Terminal"\n'
        '  activate\n'
        f'  do script "{inner}"\n'
        'end tell'
    )

    try:
        subprocess.run(["osascript", "-e", osa], check=False)
    except Exception as exc:  # noqa: BLE001
        _alert_error("VoxTerm — couldn't open Terminal", str(exc))


def _say(text: str):
    """Speak text aloud using the built-in macOS `say` command.
    Kills any still-running previous call so speech doesn't overlap."""
    global _say_proc
    import subprocess
    try:
        if _say_proc is not None and _say_proc.poll() is None:
            _say_proc.terminate()
        _say_proc = subprocess.Popen(["say", text])
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Confirmation dialogs
# ---------------------------------------------------------------------------

def _confirm_medium(result: dict) -> bool:
    """
    Show a rumps.alert() for medium-risk commands.
    Returns True if the user clicks Run.
    """
    risk_emoji = _RISK_EMOJI.get(result.get("risk", "low"), "🟡")
    cmd = result.get("command") or " → ".join(result.get("steps") or [])
    explanation = result.get("explanation", "")

    response = _alert_sync(
        title=f"{risk_emoji} Run this command?",
        message=f"{explanation}\n\n$ {cmd}",
        ok="Run",
        cancel="Cancel",
    )
    return bool(response)


def _confirm_high(result: dict) -> bool:
    """
    Show a two-step rumps.alert() for high-risk commands.
    First alert warns; second alert asks for explicit confirmation.
    """
    cmd = result.get("command") or " → ".join(result.get("steps") or [])
    explanation = result.get("explanation", "")

    # First: warn
    _alert_sync(
        title="🔴 HIGH RISK command",
        message=(
            f"{explanation}\n\n"
            f"$ {cmd}\n\n"
            "This command is destructive or requires elevated privileges."
        ),
        ok="I understand — show confirmation",
    )

    # Second: confirm with a window that requires the user to type "yes"
    # rumps doesn't have a text-input dialog, so use a two-button confirm.
    response = _alert_sync(
        title="⚠️ Are you absolutely sure?",
        message=f"This will run:\n\n$ {cmd}\n\nThis action may be irreversible.",
        ok="Yes, run it",
        cancel="Cancel",
    )
    return bool(response)


def _confirm(result: dict, dry_run: bool = False) -> bool:
    """Route to the appropriate confirmation dialog based on risk level."""
    if dry_run:
        _notify("VoxTerm — dry run", result.get("command") or "multi-step command")
        return False

    risk = final_risk(result)
    result["risk"] = risk

    if risk == "low":
        return True
    elif risk == "medium":
        return _confirm_medium(result)
    else:
        return _confirm_high(result)


# ---------------------------------------------------------------------------
# Core pipeline — runs in a background thread
# ---------------------------------------------------------------------------

def _run_pipeline(app: "VoxtermApp", dry_run: bool = False):
    """
    Full voice → command pipeline.
    Runs on a worker thread so the menu bar stays responsive.
    Sends state updates back to the app via app._set_state().

    The outer try/finally guarantees _busy is always reset to False even if
    an unexpected exception escapes any step. Without this, a single unhandled
    exception leaves _busy=True forever, making the Listen button silently do
    nothing on every subsequent click.
    """
    try:
        _run_pipeline_inner(app, dry_run)
    except Exception as exc:  # noqa: BLE001
        # Catch-all safety net — log to stderr so it shows up when running
        # from source, and notify the user in the menu bar app.
        import traceback
        traceback.print_exc()
        _notify("VoxTerm — unexpected error", str(exc))
    finally:
        # Always release the busy lock so the button works again.
        app._set_state("idle")


def _run_pipeline_inner(app: "VoxtermApp", dry_run: bool = False):
    """Inner pipeline — called exclusively by _run_pipeline's try/finally wrapper."""
    # Lazy imports: loaded here (not at module level) so that ctranslate2 and
    # pyaudio are only initialised when a listen cycle actually starts.
    # This keeps the menu bar icon appearing instantly and prevents the
    # multiprocessing fork-bomb in the frozen app.
    from audio import record_until_silence
    from transcribe import transcribe
    from translate import translate, check_plugins, is_explain_request, explain_last_command
    from executor import run, run_steps
    from history import log, recent_full
    from undo import push as push_undo
    from aliases import match as match_alias

    # In terminal mode, use the Rich UI layer so the user can see and interact
    # with the pipeline directly in their shell session.
    if _IS_TERMINAL:
        import ui as _ui

    # ── 1. Record ─────────────────────────────────────────────────────────
    app._set_state("listening")
    if _IS_TERMINAL:
        _ui.show_banner()
    try:
        wav_path = record_until_silence()
    except Exception as exc:
        _alert_error("VoxTerm — microphone error", str(exc))
        print(f"[voxterm] mic error: {exc}", flush=True)
        return

    # ── 2. Transcribe ──────────────────────────────────────────────────────
    app._set_state("thinking")
    try:
        transcript = transcribe(wav_path)
    except Exception as exc:
        _alert_error("VoxTerm — transcription error", str(exc))
        if _IS_TERMINAL:
            _ui.show_error(f"transcription failed: {exc}")
        return

    if not transcript:
        _notify("VoxTerm", "No speech detected — try again.")
        if _IS_TERMINAL:
            print("[voxterm] no speech detected", flush=True)
        return

    if _IS_TERMINAL:
        _ui.show_transcript(transcript)

    # ── 3. Explain mode ────────────────────────────────────────────────────
    context_str = get_context()

    if is_explain_request(transcript):
        rows = recent_full(1)
        if rows:
            last_cmd = rows[0][2] or ""
            last_output = rows[0][5] or ""
            explanation = explain_last_command(last_cmd, last_output, context_str)
            if explanation:
                _notify("VoxTerm — explanation", explanation, subtitle=last_cmd)
                if _IS_TERMINAL:
                    _ui.show_explanation(explanation)
                _say(explanation)
            else:
                _notify("VoxTerm", "Couldn't generate explanation.")
        else:
            _notify("VoxTerm", "No previous command to explain.")
        return

    # ── 4. Resolve command (plugins → aliases → LLM) ───────────────────────
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
            "clarification": None,
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
                "clarification": None,
            }

    if result is None:
        result = translate(transcript, context_str)

    # NOTE: do NOT call _set_state("idle") here — that would prematurely release
    # _busy=False and allow a second Listen to start before confirmation/execution
    # finish. The finally block in _run_pipeline() is the sole place that resets
    # idle and releases the busy lock.

    # ── 5. Handle LLM errors ───────────────────────────────────────────────
    if "error" in result:
        _alert_error("VoxTerm — error", result["error"])
        if _IS_TERMINAL:
            _ui.show_error(result["error"])
        return

    # ── 6. Clarification ──────────────────────────────────────────────────
    if result.get("clarification"):
        _say(result["clarification"])
        if _IS_TERMINAL:
            _ui.show_clarification(result["clarification"])
            app._set_state("listening")
            try:
                answer_wav = record_until_silence()
            except RuntimeError:
                return
            app._set_state("thinking")
            try:
                answer = transcribe(answer_wav)
            except Exception:
                return
        else:
            response = _alert_sync(
                title="VoxTerm — clarification needed",
                message=result["clarification"],
                ok="Listen for answer",
                cancel="Cancel",
            )
            if not response:
                return
            app._set_state("listening")
            try:
                answer_wav = record_until_silence()
            except RuntimeError:
                return
            app._set_state("thinking")
            try:
                answer = transcribe(answer_wav)
            except Exception:
                return

        if answer:
            combined = f"{transcript}. To clarify: {answer}"
            result = translate(combined, context_str)
            # Do NOT reset idle here — same reason as step 4.
            if "error" in result:
                _alert_error("VoxTerm — error", result["error"])
                if _IS_TERMINAL:
                    _ui.show_error(result["error"])
                return

    # ── 7. Confirm ─────────────────────────────────────────────────────────
    # In terminal mode use the Rich/stdin confirmation so the user can interact
    # in their shell; in pure GUI mode use rumps dialogs.
    if _IS_TERMINAL:
        from safety import confirm as _terminal_confirm
        confirmed = _terminal_confirm(result, dry_run=dry_run)
    else:
        confirmed = _confirm(result, dry_run=dry_run)

    if not confirmed:
        if _IS_TERMINAL:
            _ui.show_cancelled()
        return

    if dry_run:
        return

    # ── 8. Execute ─────────────────────────────────────────────────────────
    if result.get("steps"):
        outputs = run_steps(result["steps"])
        success = all(o["success"] for o in outputs)
        cmd_str = " && ".join(result["steps"])
        out_text = "\n".join(o["stdout"] for o in outputs if o["stdout"])
        err_text = "\n".join(o["stderr"] for o in outputs if o["stderr"])
        if _IS_TERMINAL:
            for o in outputs:
                _ui.show_output(o["stdout"], o["stderr"], o["success"])
    else:
        output = run(result["command"])
        push_undo(result.get("inverse_command"))
        success = output["success"]
        cmd_str = result["command"]
        out_text = output["stdout"]
        err_text = output["stderr"]
        if output.get("cd"):
            try:
                os.chdir(output["cd"])
            except OSError:
                pass
        if _IS_TERMINAL:
            _ui.show_output(out_text, err_text, success)

    # ── 9. Notify result ───────────────────────────────────────────────────
    # Always send a notification (useful even in terminal mode for background
    # confirmation that the command finished while the user switched windows).
    if success:
        body = out_text.strip() if out_text.strip() else "Done."
        _notify("VoxTerm ✓", body, subtitle=cmd_str)
    else:
        body = err_text.strip() if err_text.strip() else "Command failed."
        _notify("VoxTerm ✗", body, subtitle=cmd_str)

    # ── 10. Log ────────────────────────────────────────────────────────────
    log(transcript, cmd_str, result.get("risk", "low"), success, out_text)


# ---------------------------------------------------------------------------
# Preferences window
# ---------------------------------------------------------------------------

class PreferencesWindow:
    """
    Lightweight preferences dialog built from rumps primitives.
    Lets non-technical users paste their free Gemini API key without
    touching a terminal or .env file.
    """

    @staticmethod
    def show():
        current_key = os.getenv("GEMINI_API_KEY", "")
        masked = f"...{current_key[-6:]}" if len(current_key) > 6 else "(not set)"

        response = _alert_sync(
            title="VoxTerm — Preferences",
            message=(
                f"Gemini API key: {masked}\n\n"
                "To get a free key (1500 req/day, no credit card):\n"
                "aistudio.google.com → Get API key\n\n"
                "Paste your key in the input below, then click Save.\n"
                "(If you have Ollama running locally, no key is needed.)"
            ),
            ok="Enter key",
            cancel="Close",
        )

        if not response:
            return

        result = _window_sync(
            title="Enter Gemini API Key",
            message="Paste your free key from aistudio.google.com:",
            default_text=current_key,
            ok="Save",
            cancel="Cancel",
            dimensions=(400, 24),
        )
        if result and result.clicked and result.text.strip():
            new_key = result.text.strip()
            os.environ["GEMINI_API_KEY"] = new_key
            # Persist to .env so it survives restarts.
            _ENV_PATH.touch(exist_ok=True)
            set_key(str(_ENV_PATH), "GEMINI_API_KEY", new_key)
            _on_main(
                rumps.alert,
                title="VoxTerm",
                message="API key saved. voxterm will use Gemini on the next command.",
            )


# ---------------------------------------------------------------------------
# Undo dialog
# ---------------------------------------------------------------------------

def _run_undo():
    from undo import can_undo, pop as pop_undo
    from executor import run
    if not can_undo():
        _on_main(rumps.alert, title="VoxTerm", message="Nothing to undo.")
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
    if _confirm_medium(result):
        output = run(cmd)
        if output["success"]:
            _notify("VoxTerm ✓ undo", output["stdout"].strip() or "Done.", subtitle=cmd)
        else:
            _alert_error("VoxTerm — undo failed", output["stderr"].strip() or "Command failed.")


# ---------------------------------------------------------------------------
# Main rumps app
# ---------------------------------------------------------------------------

class VoxtermApp(rumps.App):

    def __init__(self):
        # Use a text label as the menu bar title while developing without .icns.
        # PyInstaller will swap in the real icon via voxterm.spec.
        super().__init__(
            name="VoxTerm",
            title=_ICON_IDLE,
            quit_button=None,   # we add our own so we can control placement
        )

        self._busy = False          # prevents concurrent listen cycles
        self._lock = threading.Lock()

        self.menu = [
            rumps.MenuItem("Listen", callback=self._on_listen, key="l"),
            None,                   # separator
            rumps.MenuItem("Open in Terminal…", callback=self._on_open_terminal),
            rumps.MenuItem("Undo last command", callback=self._on_undo),
            None,
            rumps.MenuItem("Preferences…", callback=self._on_preferences),
            None,
            rumps.MenuItem("Quit voxterm", callback=rumps.quit_application),
        ]

        # Global hotkey: ⌘⇧Space
        if _PYNPUT_AVAILABLE:
            self._start_hotkey_listener()

        # Startup LLM check — warn immediately if no backend is reachable so
        # the user isn't left wondering why Listen does nothing.
        threading.Thread(target=self._check_llm_on_startup, daemon=True).start()

    # ── State management ───────────────────────────────────────────────────

    def _set_state(self, state: str):
        """Update the menu bar icon. Called from background threads."""
        icons = {
            "idle":      _ICON_IDLE,
            "listening": _ICON_LISTENING,
            "thinking":  _ICON_THINKING,
            "error":     _ICON_ERROR,
        }
        self.title = icons.get(state, _ICON_IDLE)
        if state == "idle":
            with self._lock:
                self._busy = False

    def _check_llm_on_startup(self):
        """
        Run once at startup (background thread). Pings Ollama and checks for
        a Gemini key. If neither is available, shows a modal alert immediately
        so the user isn't left wondering why Listen does nothing.
        """
        import time, requests as _req
        # Give the menu bar a moment to fully appear before showing dialogs.
        time.sleep(1.5)

        ollama_ok = False
        try:
            r = _req.get("http://localhost:11434", timeout=2)
            ollama_ok = r.status_code == 200
        except Exception:
            pass

        gemini_ok = bool(os.getenv("GEMINI_API_KEY", "").strip())

        if not ollama_ok and not gemini_ok:
            _on_main(
                rumps.alert,
                title="VoxTerm — no LLM configured",
                message=(
                    "VoxTerm needs an LLM to translate voice into commands.\n\n"
                    "Option A — free, offline (recommended):\n"
                    "  1. Download Ollama from ollama.com\n"
                    "  2. Run: ollama pull llama3.2:3b\n"
                    "  3. Run: ollama serve\n\n"
                    "Option B — free cloud fallback:\n"
                    "  1. Get a free key at aistudio.google.com\n"
                    "  2. Open Preferences in this menu and paste it.\n\n"
                    "Until one is set up, Listen will return an error."
                ),
            )

    # ── Menu callbacks ─────────────────────────────────────────────────────

    def _on_listen(self, _sender=None):
        with self._lock:
            if self._busy:
                _notify("VoxTerm", "Already listening — please wait.")
                return
            self._busy = True

        thread = threading.Thread(target=_run_pipeline, args=(self,), daemon=True)
        thread.start()

    def _on_undo(self, _sender=None):
        thread = threading.Thread(target=_run_undo, daemon=True)
        thread.start()

    def _on_preferences(self, _sender=None):
        PreferencesWindow.show()

    def _on_open_terminal(self, _sender=None):
        """
        Open a Terminal.app window linked to the menu bar app.

        The new terminal session shares the SQLite history DB and aliases
        with the menu bar app (both read/write data/history.db and
        data/aliases.json), and the cd-signal file so directory changes
        in the linked terminal propagate as expected.

        Two launch modes:
          • Source dist (running `python app_gui.py`): we know the repo
            path and the venv that's already imported; just spawn a Terminal
            window that sources voxterm.sh and starts an interactive shell.
          • Frozen .app bundle: we don't ship a separate `vt` binary, so
            we point the user at running the open-source CLI alongside.
        """
        _open_linked_terminal()

    # ── Global hotkey ──────────────────────────────────────────────────────

    def _start_hotkey_listener(self):
        """
        Listen for ⌘⇧Space globally. Runs on its own daemon thread.
        pynput requires macOS Accessibility permission — handled by Info.plist.
        If the listener fails to start (e.g. permission not yet granted),
        we log and carry on — the menu item still works.
        """
        HOTKEY = {
            _kb.Key.cmd,
            _kb.Key.shift,
            _kb.Key.space,
        }
        pressed: set = set()

        def on_press(key):
            pressed.add(key)
            if all(k in pressed for k in HOTKEY):
                self._on_listen()

        def on_release(key):
            pressed.discard(key)

        try:
            listener = _kb.Listener(on_press=on_press, on_release=on_release)
            listener.daemon = True
            listener.start()
        except Exception as exc:
            print(f"[voxterm] hotkey listener failed (no Accessibility permission?): {exc}", flush=True)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    _acquire_single_instance_lock()

    # Init DB lazily in a thread so it doesn't delay the icon appearing.
    def _init_db_background():
        from history import init as init_db
        init_db()

    threading.Thread(target=_init_db_background, daemon=True).start()

    VoxtermApp().run()
