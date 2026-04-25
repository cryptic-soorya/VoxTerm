# PLAN.md — voxterm build roadmap

Everything you need to build this project from zero to GitHub-ready.
No paid APIs. No subscriptions. Fully free stack.

---

## The big picture

voxterm has one job: take voice input and safely run shell commands. Every design decision flows from two principles:

1. **Never surprise the user** — always show what you're about to do before doing it
2. **Free and local first** — Whisper on-device, Ollama as primary LLM, Gemini free tier as fallback

---

## Free stack summary

| Layer | Tool | Cost |
|-------|------|------|
| Transcription | faster-whisper (local) | Free, runs on your Mac |
| LLM (primary) | Ollama + Mistral or Llama3 (local) | Free, runs on your Mac |
| LLM (fallback) | Google Gemini 1.5 Flash API | Free tier: 1500 req/day |
| UI | Rich | Free, open source |
| Storage | SQLite (built into Python) | Free |
| CLI | Click | Free, open source |

Total cost to run: $0.

---

## Architecture overview

```
[Microphone]
     ↓
[audio.py] — PyAudio stream + WebRTCVAD silence detection
     ↓
  audio.wav (temp file, deleted after use)
     ↓
[transcribe.py] — faster-whisper local inference on Apple Silicon
     ↓
  "move all pdfs from downloads to documents"
     ↓
[context.py] — inject cwd, username, shell, OS, time
     ↓
[plugins/] — check for plugin trigger words (skip LLM if matched)
     ↓
[aliases.py] — check if transcript matches a saved alias (skip LLM if matched)
     ↓
[translate.py] — Ollama (primary) or Gemini Flash (fallback) → JSON
     ↓
  { command, risk, explanation, destructive, inverse_command, steps }
     ↓
[safety.py] — hardcoded risk overrides → confirmation UI
     ↓
  User confirms (or cancels)
     ↓
[executor.py] — subprocess.run() → stdout/stderr captured
     ↓
[undo.py] — push inverse_command to undo stack
     ↓
[history.py] — log to SQLite
     ↓
[ui.py] — display output in Rich panel
     ↓
[aliases.py] — check if this request should be offered as a new alias
```

---

## Phase 1 — Audio capture + transcription

**Goal:** speak into mic, see a text transcript printed in terminal.
**Files:** `audio.py`, `transcribe.py`
**Install:** `pip install pyaudio webrtcvad faster-whisper`

### How audio.py works

PyAudio opens a raw stream from your microphone. The key settings:
- **16kHz sample rate** — Whisper was trained on 16,000 samples per second. Higher rates waste compute.
- **Mono** — one channel. Stereo is pointless for speech.
- **16-bit PCM** — standard uncompressed audio format.

WebRTCVAD (Voice Activity Detection) watches incoming audio frames and returns True/False: "is someone speaking right now?" This is how the tool knows when you've stopped talking — it waits for 1.5 seconds of continuous silence after speech started.

A **frame** in this context is a tiny chunk of audio — 30ms worth, which at 16kHz = 480 samples. VAD works on frames, not continuous streams.

```python
# audio.py
import pyaudio
import webrtcvad
import wave
import tempfile
import os

SAMPLE_RATE = 16000
FRAME_DURATION_MS = 30
CHUNK = int(SAMPLE_RATE * FRAME_DURATION_MS / 1000)  # 480 samples
SILENCE_THRESHOLD_SECONDS = 1.5
SILENCE_FRAMES_NEEDED = int(SILENCE_THRESHOLD_SECONDS * 1000 / FRAME_DURATION_MS)  # 50 frames

def record_until_silence() -> str:
    """
    Opens mic, records until 1.5s of silence after speech detected.
    Returns path to a temporary .wav file.
    """
    vad = webrtcvad.Vad(3)  # aggressiveness 0-3, 3 = most aggressive (less ambient noise treated as speech)
    pa = pyaudio.PyAudio()

    stream = pa.open(
        rate=SAMPLE_RATE,
        channels=1,
        format=pyaudio.paInt16,
        input=True,
        frames_per_buffer=CHUNK
    )

    print("listening...")
    frames = []
    silent_frame_count = 0
    speech_detected = False

    while True:
        raw_frame = stream.read(CHUNK, exception_on_overflow=False)
        is_speech = vad.is_speech(raw_frame, SAMPLE_RATE)

        if is_speech:
            speech_detected = True
            silent_frame_count = 0
            frames.append(raw_frame)
        elif speech_detected:
            # we heard speech before, now silence — keep counting
            frames.append(raw_frame)
            silent_frame_count += 1
            if silent_frame_count >= SILENCE_FRAMES_NEEDED:
                break  # long enough silence, stop recording
        # if no speech detected yet, just keep waiting

    stream.stop_stream()
    stream.close()
    pa.terminate()

    # save to temp wav file
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    with wave.open(tmp.name, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(pa.get_sample_size(pyaudio.paInt16))
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(b"".join(frames))

    return tmp.name
```

### How transcribe.py works

faster-whisper is the same model as OpenAI's Whisper but runs through CTranslate2 — a runtime optimised for CPU inference. On Apple Silicon it uses the CPU efficiently (not GPU, but fast enough).

The model is loaded once at module level — loading takes ~1 second, but transcription itself is ~0.4 seconds per clip. Never reload the model on every call.

`int8` compute type = 8-bit integer quantization. The model weights are compressed. Slightly less precise but 2x faster and uses half the memory. Undetectable quality difference for speech.

```python
# transcribe.py
from faster_whisper import WhisperModel
import os

WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL", "base")

# load once at import time — expensive to load, cheap to run
_model = WhisperModel(WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")

def transcribe(wav_path: str) -> str:
    """
    Takes path to a .wav file.
    Returns transcribed text as a string.
    Deletes the wav file after transcription.
    """
    segments, info = _model.transcribe(wav_path, beam_size=5)
    # segments is a generator — we consume it to get all text
    text = " ".join(segment.text.strip() for segment in segments)

    # clean up temp file
    try:
        os.unlink(wav_path)
    except OSError:
        pass

    return text.strip()
```

**Milestone:** run these two together. Speak. See your words. Do not move to Phase 2 until this works reliably.

---

## Phase 2 — LLM translation (Ollama + Gemini)

**Goal:** take transcript string → return a parsed, validated JSON dict.
**Files:** `translate.py`, `context.py`, `prompts/system.txt`
**Install:** `pip install google-generativeai python-dotenv requests`
**Ollama setup:** download from ollama.com, then `ollama pull mistral`

### How context.py works

The LLM needs to know where you are in the filesystem to generate accurate commands. Without this, "delete the build folder" might generate `rm -rf /build` instead of `rm -rf /Users/soorya/projects/myapp/build`. Every LLM call gets this prepended.

```python
# context.py
import os
import platform
import datetime

def get_context() -> str:
    return (
        f"CWD: {os.getcwd()}\n"
        f"USER: {os.getenv('USER', 'unknown')}\n"
        f"SHELL: {os.getenv('SHELL', '/bin/zsh')}\n"
        f"OS: macOS {platform.mac_ver()[0]} (Apple Silicon)\n"
        f"TIME: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )
```

### prompts/system.txt — the brain of the whole tool

This is the most important file. Tune this to change the tool's behaviour. Both Ollama and Gemini receive this exact text as their system prompt.

```
You are a shell command translator for macOS running zsh.
You receive a plain English request and context about the user's environment.
Your job: translate the request into a safe, correct shell command.

CRITICAL: Return ONLY valid JSON. No explanation outside the JSON.
No markdown fences. No backticks. Just the raw JSON object.

JSON schema — always use this exact shape:
{
  "command": "the shell command string, or null if multi-step",
  "steps": ["step1", "step2"] or null if single command,
  "risk": "low" or "medium" or "high",
  "explanation": "one sentence in plain English describing what this does",
  "destructive": true or false,
  "inverse_command": "command to undo this, or null if not reversible"
}

Risk classification — follow these exactly:
- low: read-only. ls, cat, pwd, grep, find (no -delete), echo, which, df, du, ps, git status, git log
- medium: file moves, copies, renames, downloads, package installs, mkdir, touch, git add/commit/push
- high: any deletion, sudo, chmod, chown, recursive flags (-r -rf), writing to system paths, kill

Multi-step rules:
- If the request needs multiple commands, put each in "steps" and set "command" to null
- NEVER combine a destructive step with a safe step in a single command
- Each step is confirmed independently before running

Inverse command rules:
- mv a b → inverse is mv b a
- mkdir foo → inverse is rmdir foo
- cp a b → inverse is rm b
- git commit → inverse is git reset HEAD~1
- rm or any irreversible action → inverse_command is null

Use the provided context (CWD, USER) to make commands precise.
If the request is unsafe or impossible to translate safely, return:
{"error": "brief reason"}
```

### How translate.py works

Three functions: one for Ollama, one for Gemini, and one router that picks automatically.

**Ollama** runs a local HTTP server on port 11434. You POST a request to it with a model name and prompt, it streams back the response. We check if Ollama is running by pinging that port first.

**Gemini** uses Google's official Python SDK. The key trick: set `response_mime_type="application/json"` — this tells Gemini to output raw JSON without any markdown wrapping. Much more reliable than asking it nicely in the prompt alone.

```python
# translate.py
import json
import os
import requests
from pathlib import Path
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

SYSTEM_PROMPT = Path("prompts/system.txt").read_text()
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral")
OLLAMA_URL = "http://localhost:11434/api/generate"

def _is_ollama_running() -> bool:
    """Ping Ollama's local server. Returns True if it responds."""
    try:
        r = requests.get("http://localhost:11434", timeout=2)
        return r.status_code == 200
    except requests.exceptions.ConnectionError:
        return False

def _parse_json(raw: str) -> dict:
    """
    Parse JSON from LLM response.
    Strips markdown fences if the LLM added them anyway.
    """
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        # remove ```json ... ``` wrapper
        lines = cleaned.split("\n")
        cleaned = "\n".join(lines[1:-1])
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        return {"error": f"invalid JSON from LLM: {e}", "raw": raw}

def translate_ollama(transcript: str, context: str) -> dict:
    """
    Send transcript to local Ollama model.
    Ollama runs on your Mac, no internet needed.
    """
    full_prompt = f"{SYSTEM_PROMPT}\n\nEnvironment:\n{context}\n\nRequest: {transcript}"
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": full_prompt,
        "stream": False,       # wait for full response before returning
        "format": "json"       # Ollama's built-in JSON mode
    }
    response = requests.post(OLLAMA_URL, json=payload, timeout=60)
    raw = response.json()["response"]
    return _parse_json(raw)

def translate_gemini(transcript: str, context: str) -> dict:
    """
    Send transcript to Google Gemini 1.5 Flash (free tier).
    Used as fallback when Ollama isn't running.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return {"error": "GEMINI_API_KEY not set and Ollama is not running. See README for setup."}

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name="gemini-1.5-flash",
        system_instruction=SYSTEM_PROMPT,
        generation_config=genai.GenerationConfig(
            response_mime_type="application/json"  # forces raw JSON output
        )
    )
    user_message = f"Environment:\n{context}\n\nRequest: {transcript}"
    response = model.generate_content(user_message)
    return _parse_json(response.text)

def translate(transcript: str, context: str, force_offline=False, force_cloud=False) -> dict:
    """
    Router: picks Ollama or Gemini based on availability and flags.
    Order: force_offline → force_cloud → Ollama if running → Gemini fallback
    """
    if force_offline:
        if not _is_ollama_running():
            return {"error": "Ollama is not running. Start it with: ollama serve"}
        return translate_ollama(transcript, context)

    if force_cloud:
        return translate_gemini(transcript, context)

    # auto-select
    if _is_ollama_running():
        return translate_ollama(transcript, context)
    else:
        return translate_gemini(transcript, context)
```

**Milestone:** hardcode a transcript string, call `translate()`, print the dict. The JSON should parse cleanly. Test with Ollama running and with it stopped (to test Gemini fallback).

---

## Phase 3 — Safety gate

**Goal:** look at the JSON dict, apply hardcoded overrides, show confirmation UI.
**File:** `safety.py`
**Install:** `pip install rich` (also needed for ui.py)

The LLM's risk assessment is a *suggestion*. Your hardcoded rules are law. This separation is important — if someone crafts a tricky transcript that makes the LLM think a dangerous command is low risk, the hardcoded list catches it anyway.

```python
# safety.py
from rich.console import Console
from rich.panel import Panel

console = Console()

# these patterns always force HIGH risk, regardless of LLM assessment
FORCE_HIGH_PATTERNS = [
    "rm ",
    "rm\t",
    "sudo ",
    "chmod ",
    "chown ",
    " -rf",
    " -r ",
    "-r\t",
    " --recursive",
]

def _final_risk(result: dict) -> str:
    """Apply hardcoded overrides to LLM's risk assessment."""
    llm_risk = result.get("risk", "high")
    cmd = result.get("command") or " ".join(result.get("steps") or [])

    for pattern in FORCE_HIGH_PATTERNS:
        if pattern in cmd:
            return "high"

    return llm_risk

def confirm(result: dict, dry_run: bool = False) -> bool:
    """
    Shows appropriate UI based on risk level.
    Returns True if the user approves execution.
    Always returns False in dry_run mode.
    """
    risk = _final_risk(result)
    explanation = result.get("explanation", "no explanation provided")

    # build display command string
    if result.get("steps"):
        cmd_display = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(result["steps"]))
    else:
        cmd_display = result.get("command", "")

    if dry_run:
        console.print(Panel(
            f"[dim]{cmd_display}[/dim]\n\n[dim]{explanation}[/dim]",
            title="[dim]dry run — would execute[/dim]",
            border_style="dim"
        ))
        return False  # never runs in dry-run

    if risk == "low":
        # run immediately, no prompt needed
        console.print(f"[dim]running:[/dim] {cmd_display}")
        return True

    if risk == "medium":
        console.print(Panel(
            f"[bold]{cmd_display}[/bold]\n\n{explanation}",
            title="command to run",
            border_style="yellow"
        ))
        answer = console.input("[yellow]run this? [Y/n] [/yellow]").strip().lower()
        return answer in ("", "y", "yes")

    if risk == "high":
        console.print(Panel(
            f"[bold red]{cmd_display}[/bold red]\n\n[red]{explanation}[/red]",
            title="[red bold]warning — destructive command[/red bold]",
            border_style="red"
        ))
        answer = console.input('[red]type "yes" to confirm, anything else to cancel: [/red]').strip().lower()
        return answer == "yes"

    return False
```

---

## Phase 4 — Execution

**Goal:** run the approved command, capture output, handle errors.
**File:** `executor.py`

`subprocess.run()` is Python's way of running a shell command. Key parameters:
- `shell=True` — passes the command to /bin/zsh as a string (needed for pipes, wildcards etc.)
- `executable="/bin/zsh"` — use zsh specifically, not bash
- `capture_output=True` — capture stdout and stderr instead of printing them directly
- `text=True` — decode bytes to string automatically

Return code 0 = success. Anything else = some kind of error.

```python
# executor.py
import subprocess

def run(command: str) -> dict:
    """Run a single shell command. Returns stdout, stderr, success status."""
    result = subprocess.run(
        command,
        shell=True,
        executable="/bin/zsh",
        capture_output=True,
        text=True
    )
    return {
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
        "returncode": result.returncode,
        "success": result.returncode == 0,
        "command": command
    }

def run_steps(steps: list[str]) -> list[dict]:
    """
    Run a list of commands one at a time.
    Stops at the first failure — never continues a broken pipeline.
    """
    results = []
    for step in steps:
        r = run(step)
        results.append(r)
        if not r["success"]:
            break  # abort remaining steps
    return results
```

---

## Phase 5 — History logging

**Goal:** log every command run to SQLite so you can review and rerun.
**File:** `history.py`

SQLite is a file-based database built into Python — no server, no setup. The database is a single file: `data/history.db`. It's gitignored so your personal command history never gets committed.

```python
# history.py
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path("data/history.db")

def init():
    """Create the database and table if they don't exist yet."""
    DB_PATH.parent.mkdir(exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                transcript TEXT,
                command   TEXT,
                risk      TEXT,
                success   INTEGER,
                output    TEXT
            )
        """)

def log(transcript: str, command: str, risk: str, success: bool, output: str):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO history VALUES (NULL, ?, ?, ?, ?, ?, ?)",
            (datetime.now().isoformat(), transcript, command, risk, int(success), output)
        )

def recent(n: int = 20) -> list[tuple]:
    with sqlite3.connect(DB_PATH) as conn:
        return conn.execute(
            "SELECT timestamp, transcript, command, risk, success FROM history ORDER BY id DESC LIMIT ?",
            (n,)
        ).fetchall()
```

---

## Phase 6 — Undo stack

**Goal:** say "undo" to reverse the last reversible command.
**File:** `undo.py`

The undo stack is a simple Python list kept in memory. It resets when voxterm exits — intentionally. Persisting undo to disk would mean old destructive inverses could be replayed much later, which is risky.

```python
# undo.py
_stack: list[str | None] = []

def push(inverse_command: str | None):
    """Push an inverse command onto the stack after a successful run."""
    _stack.append(inverse_command)

def pop() -> str | None:
    """Get the last inverse command and remove it from the stack."""
    if _stack:
        return _stack.pop()
    return None

def can_undo() -> bool:
    """True if there's something to undo (and it's actually reversible)."""
    return bool(_stack) and _stack[-1] is not None

def peek() -> str | None:
    """See the top of the stack without removing it."""
    if _stack:
        return _stack[-1]
    return None
```

---

## Phase 7 — Rich UI

**Goal:** make the terminal output look polished and readable.
**File:** `ui.py`

Rich is a Python library for beautiful terminal output. Key components used here:
- `Console` — the main output object, like a fancy print()
- `Panel` — draws a bordered box around content
- `Syntax` — syntax-highlighted code blocks
- `Table` — formatted tables with columns
- `Live` + `Spinner` — animated loading indicators

```python
# ui.py
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.live import Live
from rich.spinner import Spinner

console = Console()

def show_listening():
    console.print("[dim]listening...[/dim]")

def show_transcribing():
    console.print("[dim]transcribing...[/dim]")

def show_thinking():
    console.print("[dim]thinking...[/dim]")

def show_transcript(text: str):
    console.print(f"\n[bold]you said:[/bold] {text}\n")

def show_command(cmd: str, explanation: str):
    console.print(Syntax(cmd, "bash", theme="monokai", word_wrap=True))
    console.print(f"[dim]{explanation}[/dim]\n")

def show_output(stdout: str, stderr: str, success: bool):
    if stdout:
        console.print(Panel(
            stdout,
            title="output",
            border_style="green" if success else "red"
        ))
    if stderr and not success:
        console.print(Panel(stderr, title="error", border_style="red"))
    if not stdout and not stderr:
        status = "[green]done[/green]" if success else "[red]failed with no output[/red]"
        console.print(status)

def show_history(rows: list[tuple]):
    table = Table(title="command history", show_lines=True)
    table.add_column("time", style="dim", width=16)
    table.add_column("you said", max_width=30)
    table.add_column("command", style="cyan", max_width=40)
    table.add_column("risk", width=8)
    table.add_column("ok", justify="center", width=4)
    for row in rows:
        ok = "[green]✓[/green]" if row[4] else "[red]✗[/red]"
        table.add_row(row[0][:16], row[1] or "", row[2] or "", row[3] or "", ok)
    console.print(table)

def show_error(message: str):
    console.print(f"[red]error:[/red] {message}")

def show_undo_unavailable():
    console.print("[dim]nothing to undo[/dim]")
```

---

## Phase 8 — Alias learning

**Goal:** remember repeated requests and offer to save them as named shortcuts.
**File:** `aliases.py`

```python
# aliases.py
import json
from pathlib import Path
from history import recent

ALIASES_PATH = Path("data/aliases.json")

def load() -> dict:
    if ALIASES_PATH.exists():
        return json.loads(ALIASES_PATH.read_text())
    return {}

def save(name: str, command: str):
    aliases = load()
    aliases[name] = command
    ALIASES_PATH.parent.mkdir(exist_ok=True)
    ALIASES_PATH.write_text(json.dumps(aliases, indent=2))

def match(transcript: str) -> str | None:
    """Return stored command if transcript contains a saved alias name."""
    for name, cmd in load().items():
        if name.lower() in transcript.lower():
            return cmd
    return None

def check_for_repeat(transcript: str) -> bool:
    """True if a very similar request has been made 3+ times."""
    rows = recent(50)
    count = sum(1 for r in rows if transcript[:25].lower() in (r[1] or "").lower())
    return count >= 3
```

---

## Phase 9 — Plugin system

**Goal:** custom shortcuts that run before the LLM — zero latency, zero API calls.
**Folder:** `plugins/`

```python
# plugins/example.py
TRIGGER = "deploy"
DESCRIPTION = "Run the project deploy pipeline"

def run(context: dict) -> str:
    return "npm run build && netlify deploy --prod"
```

Plugin loader in translate.py (add this before the LLM call):
```python
import importlib.util, os
from pathlib import Path

def check_plugins(transcript: str) -> str | None:
    plugins_dir = Path("plugins")
    if not plugins_dir.exists():
        return None
    for f in plugins_dir.glob("*.py"):
        if f.name == "example.py":
            continue
        spec = importlib.util.spec_from_file_location(f.stem, f)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if hasattr(mod, "TRIGGER") and mod.TRIGGER.lower() in transcript.lower():
            return mod.run({})
    return None
```

---

## Phase 10 — CLI with Click + main.py

**Goal:** wire everything together with professional CLI flags.

```python
# main.py
import click
from dotenv import load_dotenv
from audio import record_until_silence
from transcribe import transcribe
from translate import translate, check_plugins
from context import get_context
from safety import confirm
from executor import run, run_steps
from history import init as init_db, log, recent
from undo import push as push_undo, pop as pop_undo, can_undo
from aliases import match as match_alias, check_for_repeat, save as save_alias, load as load_aliases
from ui import (console, show_listening, show_transcribing, show_thinking,
                show_transcript, show_output, show_error, show_history, show_undo_unavailable)

load_dotenv()

@click.group(invoke_without_command=True)
@click.option("--dry-run", is_flag=True, help="Show commands without running them")
@click.option("--offline", is_flag=True, help="Force Ollama (error if not running)")
@click.option("--cloud", is_flag=True, help="Force Gemini free API")
@click.pass_context
def cli(ctx, dry_run, offline, cloud):
    if ctx.invoked_subcommand is not None:
        return

    init_db()
    ctx.ensure_object(dict)

    show_listening()
    wav_path = record_until_silence()

    show_transcribing()
    transcript = transcribe(wav_path)
    show_transcript(transcript)

    context_str = get_context()

    # plugins first — no LLM call if matched
    plugin_cmd = check_plugins(transcript)
    if plugin_cmd:
        result = {
            "command": plugin_cmd, "steps": None,
            "risk": "medium", "explanation": "plugin command",
            "destructive": False, "inverse_command": None
        }
    else:
        # aliases next — no LLM call if matched
        alias_cmd = match_alias(transcript)
        if alias_cmd:
            result = {
                "command": alias_cmd, "steps": None,
                "risk": "medium", "explanation": "saved alias",
                "destructive": False, "inverse_command": None
            }
        else:
            show_thinking()
            result = translate(transcript, context_str,
                               force_offline=offline, force_cloud=cloud)

    if "error" in result:
        show_error(result["error"])
        return

    if not confirm(result, dry_run=dry_run):
        console.print("[dim]cancelled[/dim]")
        return

    # execute
    if result.get("steps"):
        outputs = run_steps(result["steps"])
        for o in outputs:
            show_output(o["stdout"], o["stderr"], o["success"])
        success = all(o["success"] for o in outputs)
        cmd_str = " && ".join(result["steps"])
        output_str = "\n".join(o["stdout"] for o in outputs)
    else:
        output = run(result["command"])
        show_output(output["stdout"], output["stderr"], output["success"])
        push_undo(result.get("inverse_command"))
        success = output["success"]
        cmd_str = result["command"]
        output_str = output["stdout"]

    if not dry_run:
        log(transcript, cmd_str, result["risk"], success, output_str)

    # alias learning: offer to save if repeated
    if check_for_repeat(transcript):
        answer = console.input(f"\n[dim]you've run this a few times. save as alias? (name or enter to skip): [/dim]").strip()
        if answer:
            save_alias(answer, cmd_str)
            console.print(f"[green]saved alias '{answer}'[/green]")


@cli.command()
def undo():
    """Reverse the last reversible command."""
    if not can_undo():
        show_undo_unavailable()
        return
    cmd = pop_undo()
    result = {"command": cmd, "steps": None, "risk": "medium",
              "explanation": "undo last command", "destructive": False, "inverse_command": None}
    if confirm(result):
        output = run(cmd)
        show_output(output["stdout"], output["stderr"], output["success"])


@cli.command(name="history")
def show_history_cmd():
    """Show the last 20 commands."""
    init_db()
    show_history(recent(20))


@cli.group()
def alias():
    """Manage saved aliases."""
    pass


@alias.command(name="list")
def alias_list():
    """Show all saved aliases."""
    aliases = load_aliases()
    if not aliases:
        console.print("[dim]no aliases saved yet[/dim]")
        return
    for name, cmd in aliases.items():
        console.print(f"[bold]{name}[/bold]  →  {cmd}")


@alias.command(name="save")
@click.argument("name")
def alias_save(name):
    """Save the last command as an alias with the given name."""
    rows = recent(1)
    if not rows:
        show_error("no commands in history yet")
        return
    cmd = rows[0][2]
    save_alias(name, cmd)
    console.print(f"[green]saved:[/green] '{name}' → {cmd}")


if __name__ == "__main__":
    cli()
```

---

## Phase 11 — Polish and ship

**requirements.txt:**
```
pyaudio==0.2.14
webrtcvad==2.0.10
faster-whisper==1.0.3
google-generativeai>=0.7.0
python-dotenv==1.0.1
rich==13.7.1
click==8.1.7
requests==2.31.0
pyttsx3==2.90
```

**.env.example:**
```
# Get a free key at aistudio.google.com — no credit card needed
# Only needed if you want Gemini as fallback when Ollama isn't running
GEMINI_API_KEY=

# Ollama model to use (must be pulled first: ollama pull mistral)
OLLAMA_MODEL=mistral

# Whisper model size: tiny | base | small | medium
WHISPER_MODEL=base
```

**.gitignore:**
```
venv/
__pycache__/
*.pyc
.env
data/
*.wav
.DS_Store
```

**README.md must include:**
- Demo GIF at the very top (record with Kap or asciinema + agg)
- One-liner pitch
- "100% free — no paid APIs required"
- Copy-paste install instructions
- Two setup paths clearly separated: Ollama (offline) and Gemini (free cloud)
- Screenshots of each risk tier

**Demo script (what to record for the GIF):**
1. Say: "show me what's in my downloads folder" → low risk, runs instantly
2. Say: "move all the PDFs from downloads to documents" → medium, shows confirm
3. Say: "find all node_modules folders and show me how much space they use" → multi-step, shows plan

**GitHub release checklist:**
- [ ] .env never committed (only .env.example)
- [ ] data/ in .gitignore
- [ ] Works from fresh clone with just README instructions
- [ ] Tested with Ollama running
- [ ] Tested with Ollama stopped + GEMINI_API_KEY set
- [ ] Demo GIF recorded and embedded in README

---

## Post-MVP ideas

- Native macOS menu bar app with rumps (no terminal needed to activate)
- Wake word detection ("hey voxterm") using porcupine (free tier)
- Voice output via macOS built-in `say` command
- Web history dashboard
- Shell integration: source into existing terminal sessions
- Homebrew formula so users can `brew install voxterm`


---

## Phase 12 — GUI, packaging, and distribution

**Goal:** turn the Python CLI into a proper Mac app that anyone can download from a website, double-click, and use. No Terminal. No Python. No setup.

This phase has four sub-steps:
1. Add a menu bar GUI with rumps
2. Bundle everything into a `.app` with PyInstaller
3. Wrap the `.app` into a `.dmg` with create-dmg
4. Host it on GitHub Releases + build a landing page

---

### Step 12A — Menu bar GUI with rumps

Right now voxterm lives in Terminal. For a downloadable app, people expect something that sits in their menu bar — like how Dropbox or Bartender work. You click the icon, something happens, you go back to what you were doing.

**rumps** (Ridiculously Uncomplicated macOS Python Statusbar apps) is a Python library that creates native macOS menu bar apps. It wraps PyObjC (the Python-to-macOS bridge) in a dead-simple API. Your entire backend — audio.py, transcribe.py, translate.py, all of it — stays exactly the same. rumps is just a thin shell on top.

Install: `pip install rumps`

How rumps works: you subclass `rumps.App`, give it a name and an icon, define menu items, and run it. It creates a persistent process that lives in your menu bar. When the user clicks your icon they see a dropdown menu. Menu items are just Python functions decorated with `@rumps.clicked("Menu Item Name")`.

```python
# app_gui.py  ← new file, sits alongside main.py
import rumps
import threading
from audio import record_until_silence
from transcribe import transcribe
from translate import translate, check_plugins
from context import get_context
from safety import confirm_gui          # new GUI version of confirm (see below)
from executor import run, run_steps
from history import init as init_db, log, recent
from undo import push as push_undo, pop as pop_undo, can_undo
from aliases import match as match_alias
from dotenv import load_dotenv

load_dotenv()

class VoxTermApp(rumps.App):
    def __init__(self):
        super().__init__(
            name="voxterm",
            title="🎙",          # this is what shows in the menu bar
            quit_button="Quit voxterm"
        )
        self.menu = [
            "Listen",
            "Undo last command",
            None,                # separator line
            "History",
            "Preferences",
        ]
        self.is_listening = False
        init_db()

    @rumps.clicked("Listen")
    def listen(self, _):
        """
        Runs the full pipeline in a background thread.
        IMPORTANT: audio recording blocks — never run it on the main thread
        or the whole app freezes. Threading keeps the menu bar responsive.
        """
        if self.is_listening:
            return  # prevent double-tap
        self.is_listening = True
        self.title = "⏺"  # change icon to show we're recording
        threading.Thread(target=self._run_pipeline, daemon=True).start()

    def _run_pipeline(self):
        """Full voxterm pipeline. Runs on a background thread."""
        try:
            wav_path = record_until_silence()
            self.title = "⏳"

            transcript = transcribe(wav_path)
            context_str = get_context()

            plugin_cmd = check_plugins(transcript)
            if plugin_cmd:
                result = {"command": plugin_cmd, "steps": None, "risk": "medium",
                         "explanation": "plugin", "destructive": False, "inverse_command": None}
            else:
                alias_cmd = match_alias(transcript)
                if alias_cmd:
                    result = {"command": alias_cmd, "steps": None, "risk": "medium",
                             "explanation": "saved alias", "destructive": False, "inverse_command": None}
                else:
                    result = translate(transcript, context_str)

            if "error" in result:
                rumps.notification("voxterm", "could not translate", result["error"])
                return

            # confirm_gui shows a native macOS dialog instead of terminal prompts
            approved = confirm_gui(result)
            if not approved:
                return

            if result.get("steps"):
                outputs = run_steps(result["steps"])
                success = all(o["success"] for o in outputs)
                out_text = "\n".join(o["stdout"] for o in outputs if o["stdout"])
                cmd_str = " && ".join(result["steps"])
            else:
                output = run(result["command"])
                push_undo(result.get("inverse_command"))
                success = output["success"]
                out_text = output["stdout"] or output["stderr"]
                cmd_str = result["command"]

            log(transcript, cmd_str, result["risk"], success, out_text)

            # native macOS notification with result
            rumps.notification(
                title="voxterm",
                subtitle="done" if success else "failed",
                message=out_text[:100] if out_text else cmd_str
            )

        finally:
            self.title = "🎙"   # reset icon
            self.is_listening = False

    @rumps.clicked("Undo last command")
    def undo(self, _):
        if not can_undo():
            rumps.alert("nothing to undo")
            return
        cmd = pop_undo()
        rumps.notification("voxterm", "undoing", cmd)
        output = run(cmd)
        rumps.notification("voxterm", "undone" if output["success"] else "undo failed",
                          output["stdout"] or output["stderr"])

    @rumps.clicked("History")
    def show_history(self, _):
        rows = recent(10)
        if not rows:
            rumps.alert("no history yet")
            return
        text = "\n".join(f"{r[3].upper()}  {r[2]}" for r in rows)
        rumps.alert(title="recent commands", message=text)

    @rumps.clicked("Preferences")
    def preferences(self, _):
        """
        Opens a simple native dialog to set the Gemini API key.
        The key is saved to the .env file next to the app bundle.
        """
        response = rumps.Window(
            message="Gemini API key (free at aistudio.google.com)\nLeave blank to use Ollama only.",
            title="voxterm preferences",
            default_text="",
            ok="Save",
            cancel="Cancel"
        ).run()
        if response.clicked and response.text.strip():
            env_path = Path.home() / ".voxterm.env"
            env_path.write_text(f"GEMINI_API_KEY={response.text.strip()}\n")
            rumps.notification("voxterm", "saved", "API key saved to ~/.voxterm.env")


if __name__ == "__main__":
    VoxTermApp().run()
```

### confirm_gui — native dialogs instead of terminal prompts

The existing `safety.py` uses Rich to print to terminal and waits for keyboard input. That doesn't work in a GUI app where there's no terminal visible. You need a parallel function that uses native macOS dialogs instead.

Add this to `safety.py`:

```python
def confirm_gui(result: dict) -> bool:
    """
    GUI version of confirm() — uses native macOS alert dialogs.
    Returns True if user approves, False if they cancel.
    """
    import rumps
    risk = _final_risk(result)
    explanation = result.get("explanation", "")

    if result.get("steps"):
        cmd_display = "\n".join(f"{i+1}. {s}" for i, s in enumerate(result["steps"]))
    else:
        cmd_display = result.get("command", "")

    if risk == "low":
        return True  # no prompt needed for low risk

    if risk == "medium":
        response = rumps.alert(
            title="run this command?",
            message=f"{cmd_display}\n\n{explanation}",
            ok="Run",
            cancel="Cancel"
        )
        return response == 1  # 1 = OK button clicked

    if risk == "high":
        # two-step confirmation for destructive commands
        first = rumps.alert(
            title="⚠️ destructive command",
            message=f"{cmd_display}\n\n{explanation}\n\nThis cannot be undone.",
            ok="I understand, continue",
            cancel="Cancel"
        )
        if first != 1:
            return False
        second = rumps.alert(
            title="are you sure?",
            message=f"This will run:\n{cmd_display}",
            ok="Yes, run it",
            cancel="Cancel"
        )
        return second == 1

    return False
```

---

### Step 12B — Bundle into a .app with PyInstaller

PyInstaller analyzes your Python code, finds every import and dependency, and bundles it all — your code, all the libraries, and a self-contained Python runtime — into a single `.app` folder. The user's machine needs nothing installed.

Install: `pip install pyinstaller`

**The spec file** is PyInstaller's config. Instead of running pyinstaller with a hundred flags, you write a `.spec` file once and reuse it.

```python
# voxterm.spec
# run with: pyinstaller voxterm.spec

block_cipher = None

a = Analysis(
    ["app_gui.py"],              # entry point is the GUI, not main.py
    pathex=["."],
    binaries=[],
    datas=[
        ("prompts/system.txt", "prompts"),    # include the system prompt file
        ("plugins/*.py", "plugins"),           # include any plugins
        ("assets/icon.icns", "."),             # app icon (create this — see below)
    ],
    hiddenimports=[
        "faster_whisper",
        "webrtcvad",
        "google.generativeai",
        "rumps",
        "rich",
        "sqlite3",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="voxterm",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,               # False = no terminal window opens
)

coll = COLLECT(
    exe, a.trees, a.binaries, a.zipfiles, a.datas,
    strip=False,
    upx=False,
    name="voxterm"
)

app = BUNDLE(
    coll,
    name="voxterm.app",
    icon="assets/icon.icns",
    bundle_identifier="com.yourname.voxterm",   # reverse domain, make it yours
    info_plist={
        "NSMicrophoneUsageDescription": "voxterm needs mic access to hear your voice commands.",
        "LSUIElement": True,    # makes it a menu bar app (no Dock icon)
        "CFBundleShortVersionString": "1.0.0",
    },
)
```

Key things in that spec worth understanding:

`console=False` — tells PyInstaller not to open a Terminal window when the app launches. Without this, every time someone opens voxterm a black Terminal flashes open.

`LSUIElement: True` — this Info.plist key tells macOS "this is a menu bar app, don't show it in the Dock." Without it, voxterm shows up as a regular app with a Dock icon.

`NSMicrophoneUsageDescription` — macOS requires apps to declare why they need microphone access. This string shows up in the system permission dialog when the user first runs voxterm. Without it, macOS will silently deny mic access and your app won't work.

**Building the app:**
```bash
# from your project root, with venv activated
pyinstaller voxterm.spec

# your app appears at:
dist/voxterm.app
```

**The app icon** — you need a `.icns` file (macOS icon format). Make a 1024x1024 PNG of your logo, then convert it:
```bash
mkdir icon.iconset
sips -z 512 512 logo.png --out icon.iconset/icon_512x512.png
sips -z 256 256 logo.png --out icon.iconset/icon_256x256.png
sips -z 128 128 logo.png --out icon.iconset/icon_128x128.png
sips -z 64 64   logo.png --out icon.iconset/icon_64x64.png
sips -z 32 32   logo.png --out icon.iconset/icon_32x32.png
iconutil -c icns icon.iconset -o assets/icon.icns
```

`sips` and `iconutil` are built into macOS — no extra tools needed.

---

### Step 12C — Create the DMG

A DMG (Disk Image) is macOS's standard format for distributing apps. When someone opens it, they see a window with your app icon and an Applications folder shortcut — they drag your app in and they're done. Professional and familiar.

Install: `brew install create-dmg`

```bash
# run this after building the .app
create-dmg \
  --volname "voxterm" \
  --volicon "assets/icon.icns" \
  --window-pos 200 120 \
  --window-size 600 400 \
  --icon-size 100 \
  --icon "voxterm.app" 175 190 \
  --hide-extension "voxterm.app" \
  --app-drop-link 425 190 \
  --background "assets/dmg-background.png" \
  "dist/voxterm-1.0.0.dmg" \
  "dist/voxterm.app"
```

What each flag does:
- `--volname` — the name that appears when the DMG mounts
- `--window-size 600 400` — size of the installer window in pixels
- `--icon "voxterm.app" 175 190` — position of your app icon (x y from top-left)
- `--app-drop-link 425 190` — position of the Applications shortcut the user drags to
- `--background` — a PNG image shown behind the icons (make a simple 600x400 image with an arrow pointing right, very professional looking)

Result: `dist/voxterm-1.0.0.dmg` — this is the file you upload to GitHub and link from your website.

**DMG background image** — a 600x400 PNG. Keep it simple: dark or light background, your app name in big text, a subtle arrow pointing from left to right (app icon → Applications folder). You can make this in Figma, Canva, or even Preview. This single image makes your download look 10x more professional.

---

### Step 12D — Host on GitHub Releases

GitHub Releases is free file hosting built into every GitHub repo. You upload your DMG there and GitHub serves it. No S3, no server, no cost.

**Steps:**
1. Tag your release: `git tag v1.0.0 && git push origin v1.0.0`
2. Go to your repo on GitHub → Releases → Draft a new release
3. Select your tag, write release notes, drag and drop the `.dmg` file
4. Publish

GitHub generates a permanent download URL like:
`https://github.com/yourusername/voxterm/releases/download/v1.0.0/voxterm-1.0.0.dmg`

That's the URL your landing page download button points to.

---

### Step 12E — Landing page

A simple one-page site. Host it free on GitHub Pages (already attached to your repo) or Vercel.

**The page needs exactly these things:**
- App name + one-line description
- A short demo GIF or video (the most important thing on the page)
- A big "Download for Mac" button linking to the DMG
- "Free. No account. No subscription." — say this explicitly, people care
- System requirements: macOS 12+, Apple Silicon or Intel
- Two setup options clearly explained (Ollama offline vs Gemini free API)
- A note about the security warning and how to open anyway (right-click → Open)

**The security warning section** — this is important to include so users aren't scared off:

> "When you first open voxterm, macOS may show a warning that it's from an unidentified developer. This is normal for apps not distributed through the Mac App Store. To open it: right-click the app → Open → Open. You'll only need to do this once."

**Website setup (React, replaces static docs/):**
The landing page is a full React app in `website/` using Vite, Tailwind CSS, and Framer Motion. Components: Nav, Hero, Features, HowItWorks, Safety, Privacy, Download, Footer.

```bash
cd website
npm install
npm run dev      # local preview at localhost:5173
npm run build    # outputs to website/dist/
# deploy dist/ to GitHub Pages (gh-pages branch) or Vercel
```

---

### Full distribution build script

Put this in `build.sh` so you can rebuild and re-release with one command:

```bash
#!/bin/bash
set -e  # stop on any error

VERSION="1.0.0"

echo "cleaning previous build..."
rm -rf build/ dist/

echo "building .app..."
pyinstaller voxterm.spec

echo "creating DMG..."
create-dmg \
  --volname "voxterm" \
  --volicon "assets/icon.icns" \
  --window-pos 200 120 \
  --window-size 600 400 \
  --icon-size 100 \
  --icon "voxterm.app" 175 190 \
  --hide-extension "voxterm.app" \
  --app-drop-link 425 190 \
  --background "assets/dmg-background.png" \
  "dist/voxterm-${VERSION}.dmg" \
  "dist/voxterm.app"

echo "done: dist/voxterm-${VERSION}.dmg"
echo "upload this file to GitHub Releases"
```

Run with: `chmod +x build.sh && ./build.sh`

---

### Updated folder structure (Phase 12 additions)

```
voxterm/
├── app_gui.py           ← NEW: rumps menu bar app (GUI entry point)
├── voxterm.spec         ← NEW: PyInstaller config
├── build.sh             ← NEW: one-command build script
├── assets/
│   ├── icon.icns        ← NEW: app icon (macOS format)
│   ├── icon.png         ← NEW: source PNG for the icon
│   └── dmg-background.png  ← NEW: DMG installer background image
├── website/             ← NEW: React landing page (Vite + Tailwind + Framer Motion)
│   ├── src/components/  ← Nav, Hero, Features, HowItWorks, Safety, Privacy, Download, Footer
│   ├── package.json
│   └── dist/            ← generated by `npm run build`, deploy this to GitHub Pages or Vercel
├── dist/                ← generated by PyInstaller, gitignored
│   ├── voxterm.app
│   └── voxterm-1.0.0.dmg
├── build/               ← generated by PyInstaller, gitignored
... (all existing files unchanged)
```

Add to `.gitignore`:
```
dist/
build/
*.spec.bak
```

---

### Phase 12 checklist

- [ ] Install rumps: `pip install rumps`
- [ ] Create app_gui.py with menu bar UI
- [ ] Add confirm_gui() to safety.py
- [ ] Test app_gui.py runs as a menu bar app: `python app_gui.py`
- [ ] Create assets/ folder
- [ ] Make icon PNG (1024x1024) and convert to .icns
- [ ] Make DMG background PNG (600x400)
- [ ] Install PyInstaller: `pip install pyinstaller`
- [ ] Write voxterm.spec
- [ ] Test PyInstaller build: `pyinstaller voxterm.spec`
- [ ] Test the built .app opens and works (no Terminal)
- [ ] Install create-dmg: `brew install create-dmg`
- [ ] Build DMG: run build.sh
- [ ] Open the DMG, drag to Applications, test the installed app
- [ ] Write release notes
- [ ] Upload DMG to GitHub Releases
- [x] Build landing page (React website in website/ — Vite + Tailwind + Framer Motion)
- [ ] Run `cd website && npm run build` and deploy dist/ to GitHub Pages or Vercel
- [ ] Test download link end to end


---

## Phase 13 — Intelligence upgrades

These aren't "nice to have" features — each one directly fixes a real failure mode of the tool. Add them in order of impact.

---

### 13A — History injection into LLM context (highest impact, do this first)

**The problem it solves:** right now the LLM is completely stateless. Every call starts from zero. "Do that again" or "same but for the documents folder" means nothing to it.

**How it works:** before every LLM call, pull the last 5-10 commands from SQLite and inject them as text into the user message. The LLM now has your session history as context and can reason about references, repetitions, and continuations.

This is a pattern called RAG (Retrieval Augmented Generation) — you retrieve relevant data from external storage and augment the LLM's context with it before generating a response.

Add this to `translate.py`:

```python
# translate.py — add this function
from history import recent

def build_user_message(transcript: str, context: str) -> str:
    """
    Builds the full user message with context + history + transcript.
    The LLM sees this instead of just the raw transcript.
    """
    rows = recent(7)  # last 7 commands

    history_block = ""
    if rows:
        history_block = "Commands you ran recently (most recent last):\n"
        for row in reversed(rows):  # oldest first so it reads naturally
            status = "succeeded" if row[4] else "failed"
            history_block += f"  User said: '{row[1]}'\n"
            history_block += f"  Ran: {row[2]} ({status})\n\n"
    else:
        history_block = "No previous commands this session.\n"

    return (
        f"Environment:\n{context}\n\n"
        f"{history_block}"
        f"Current request: {transcript}"
    )
```

Then in `translate_ollama()` and `translate_gemini()`, replace the raw transcript with:
```python
user_message = build_user_message(transcript, context)
```

Now the LLM can handle:
- "do that again" → it sees the last command and repeats it
- "same but for ~/Desktop" → it adapts the last command to a new path
- "delete the thing I just moved" → it knows what was just moved
- "undo what I did before" → it can generate the inverse even without the undo stack

---

### 13B — Clarification follow-ups

**The problem it solves:** when a request is ambiguous, the tool currently returns an error and you have to start over. That's frustrating and breaks the flow.

**How it works:** add a `clarification` field to the LLM JSON schema. If the LLM can't confidently translate the request, it returns a question instead of an error. Your app reads that question, speaks it back, listens for an answer, then re-runs the full pipeline with both the original transcript and the answer combined.

Update `prompts/system.txt` — add this to the JSON schema:

```
"clarification": "a question to ask the user if the request is ambiguous, or null if confident"
```

And add this rule to the system prompt:
```
If the request is ambiguous but answerable with one clarifying question, 
return clarification with your question and set command to null.
Example: user says "delete the old files" →
{"command": null, "clarification": "Which folder should I look in for old files?", ...}
Only use clarification when truly necessary — prefer making a reasonable assumption.
```

Add this to `main.py`:

```python
# in the main pipeline, after getting result from translate()

if result.get("clarification"):
    question = result["clarification"]
    
    # speak the question back (optional, uses macOS say command)
    import subprocess
    subprocess.run(["say", question])  # built-in macOS TTS, free
    
    console.print(f"\n[yellow]voxterm:[/yellow] {question}")
    console.print("[dim]listening for your answer...[/dim]")
    
    # listen for the answer
    answer_wav = record_until_silence()
    answer = transcribe(answer_wav)
    console.print(f"[dim]you answered:[/dim] {answer}")
    
    # combine original request + answer into one new transcript
    combined = f"{transcript}. To clarify: {answer}"
    
    # re-run translation with the combined transcript
    result = translate(combined, context_str, force_offline=offline, force_cloud=cloud)
```

This creates a natural back-and-forth. "Delete the old files" → "Which folder?" → "Downloads" → runs the correct command. One conversation turn, no starting over.

---

### 13C — Filesystem awareness

**The problem it solves:** the LLM knows your current directory path but not what's *inside* it. "Compress the build folder" fails if the folder is actually called `dist` or `build_output`.

**How it works:** scan the current directory before each LLM call and inject a lightweight file listing. Not recursive — just one level deep, with file sizes for large files.

Add this to `context.py`:

```python
import os

def get_filesystem_context(max_items: int = 20) -> str:
    """
    Returns a compact listing of the current directory.
    Helps the LLM know what's actually here before generating commands.
    """
    try:
        entries = os.scandir(".")
        items = []
        for entry in sorted(entries, key=lambda e: e.name):
            if entry.name.startswith("."):
                continue  # skip hidden files — reduces noise
            if entry.is_dir():
                items.append(f"  {entry.name}/")
            else:
                size = entry.stat().st_size
                if size > 1_000_000:  # only show size if > 1MB
                    mb = size / 1_000_000
                    items.append(f"  {entry.name} ({mb:.1f}MB)")
                else:
                    items.append(f"  {entry.name}")
            if len(items) >= max_items:
                items.append(f"  ... and more")
                break
        return "Current directory contents:\n" + "\n".join(items)
    except PermissionError:
        return "Current directory contents: (permission denied)"

def get_context() -> str:
    base = (
        f"CWD: {os.getcwd()}\n"
        f"USER: {os.getenv('USER', 'unknown')}\n"
        f"SHELL: {os.getenv('SHELL', '/bin/zsh')}\n"
        f"OS: macOS {platform.mac_ver()[0]} (Apple Silicon)\n"
        f"TIME: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )
    fs = get_filesystem_context()
    return f"{base}\n\n{fs}"
```

Now the LLM sees:
```
CWD: /Users/soorya/projects/myapp
...

Current directory contents:
  dist/
  node_modules/ 
  src/
  package.json
  README.md (2.1MB)
  server.log
```

"Delete the build output" now correctly targets `dist/` because the LLM can see it's there.

---

### 13D — Smart Whisper initial prompt

**The problem it solves:** Whisper sometimes mishears technical vocabulary — "git" becomes "get", "chmod" becomes "cheemod", "npm" becomes "NPM" or "engine-pm". For a terminal tool this is a real accuracy problem.

**How it works:** Whisper accepts an `initial_prompt` parameter — a string of words it biases its transcription toward. It's like telling it "these are the kinds of words you're likely to hear." One line change, measurable accuracy improvement on developer vocabulary.

Update `transcribe.py`:

```python
# add this constant
DEVELOPER_VOCAB_PROMPT = (
    "git commit push pull merge branch checkout rebase "
    "npm install run build start test node python pip brew "
    "mkdir rmdir chmod chown sudo grep find cat ls pwd cd mv cp rm "
    "ssh curl wget docker compose kubectl terraform ansible "
    "homebrew virtualenv conda jupyter pandas numpy "
    "localhost port server database postgres mongo redis "
    "API JSON config environment variable export source "
    "zsh bash shell terminal command flag argument"
)

def transcribe(wav_path: str) -> str:
    model = get_model()
    segments, _ = model.transcribe(
        wav_path,
        beam_size=5,
        initial_prompt=DEVELOPER_VOCAB_PROMPT  # ← add this line
    )
    text = " ".join(seg.text.strip() for seg in segments)
    try:
        os.unlink(wav_path)
    except OSError:
        pass
    return text.strip()
```

---

### 13E — Global hotkey activation

**The problem it solves:** having to type `python main.py` or click a menu bar icon kills the flow. A global hotkey lets you trigger voxterm from anywhere on your Mac — mid-browser, mid-editor, anywhere — without switching windows.

**How it works:** `pynput` is a Python library that registers a global keyboard listener that works even when your app isn't focused. When the hotkey is detected, it triggers the pipeline.

Install: `pip install pynput`

Add to `app_gui.py`:

```python
from pynput import keyboard as kb

# inside VoxTermApp.__init__():
self._start_hotkey_listener()

def _start_hotkey_listener(self):
    """
    Registers a global hotkey: Cmd + Shift + Space
    Works even when the app is not in focus.
    Runs in a background thread automatically (pynput handles this).
    """
    hotkey = kb.HotKey(
        kb.HotKey.parse("<cmd>+<shift>+space"),
        self._on_hotkey
    )

    def on_press(key):
        try:
            hotkey.press(kb.Key.normalize(key))  # normalize modifier keys
        except Exception:
            pass

    def on_release(key):
        try:
            hotkey.release(kb.Key.normalize(key))
        except Exception:
            pass

    listener = kb.Listener(on_press=on_press, on_release=on_release)
    listener.daemon = True
    listener.start()

def _on_hotkey(self):
    """Called when the hotkey is pressed. Triggers the listen pipeline."""
    if not self.is_listening:
        # rumps doesn't allow direct UI calls from non-main threads
        # use a timer with 0 delay to schedule on the main thread
        rumps.Timer(self.listen, 0).start()
```

Add to `.env.example`:
```
VOCTERM_HOTKEY=<cmd>+<shift>+space   # change to whatever you prefer
```

---

### 13F — Command explanation mode

**The problem it solves:** users learn nothing from just watching commands run. This feature makes voxterm genuinely educational — every command teaches you something.

**How it works:** if the user says "explain that" or "what did that do" after a command runs, a special pipeline runs — no new command is generated, the LLM just narrates what the previous command did in plain English.

Add to `translate.py`:

```python
EXPLAIN_TRIGGERS = [
    "explain that", "what did that do", "what just happened",
    "what does that mean", "break that down", "explain the command"
]

def is_explain_request(transcript: str) -> bool:
    return any(t in transcript.lower() for t in EXPLAIN_TRIGGERS)

def explain_last_command(command: str, output: str, context: str) -> str:
    """
    Ask the LLM to explain a command and its output in plain English.
    Returns a plain text explanation (not JSON).
    """
    prompt = (
        f"A user just ran this shell command:\n{command}\n\n"
        f"It produced this output:\n{output[:500]}\n\n"  # cap at 500 chars
        f"Explain in 2-3 sentences what this command does and what the output means. "
        f"Use plain English. No markdown. Assume the user is learning."
    )
    # reuse your existing LLM call but expect plain text, not JSON
    if _is_ollama_running():
        payload = {"model": OLLAMA_MODEL, "prompt": prompt, "stream": False}
        r = requests.post(OLLAMA_URL, json=payload, timeout=60)
        return r.json()["response"].strip()
    else:
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        model = genai.GenerativeModel("gemini-1.5-flash")
        return model.generate_content(prompt).text.strip()
```

In `main.py`, before the normal pipeline:
```python
# check if user wants an explanation of the last command
if is_explain_request(transcript):
    rows = recent(1)
    if rows:
        last_cmd = rows[0][2]
        last_output = rows[0][6] if len(rows[0]) > 6 else ""
        explanation = explain_last_command(last_cmd, last_output, context_str)
        console.print(Panel(explanation, title="explanation", border_style="blue"))
        subprocess.run(["say", explanation])  # read it aloud
    else:
        console.print("[dim]no previous command to explain[/dim]")
    return  # don't run the normal pipeline
```

---

### 13G — Output summarisation

**The problem it solves:** commands like `find`, `ps aux`, `git log`, or `ls -la` on a big directory dump walls of text. Raw output is often useless — a summary is what you actually want.

**How it works:** after a command runs, if the output is long (more than ~10 lines), pass it to the LLM and ask for a one-sentence summary. Show the summary prominently, keep the raw output available but collapsed.

Add to `executor.py`:

```python
SUMMARISE_THRESHOLD_LINES = 10

def should_summarise(output: str) -> bool:
    return output.count("\n") >= SUMMARISE_THRESHOLD_LINES
```

Add to `translate.py`:

```python
def summarise_output(command: str, output: str) -> str:
    """
    Summarises long command output into 1-2 readable sentences.
    """
    prompt = (
        f"Command: {command}\n"
        f"Output (first 1000 chars):\n{output[:1000]}\n\n"
        f"Summarise what this output is telling the user in 1-2 sentences. "
        f"Be specific with numbers and names. No markdown."
    )
    if _is_ollama_running():
        payload = {"model": OLLAMA_MODEL, "prompt": prompt, "stream": False}
        r = requests.post(OLLAMA_URL, json=payload, timeout=30)
        return r.json()["response"].strip()
    else:
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        model = genai.GenerativeModel("gemini-1.5-flash")
        return model.generate_content(prompt).text.strip()
```

In `ui.py`:

```python
def show_output(stdout: str, stderr: str, success: bool, summary: str = None):
    if summary:
        # show summary first, prominently
        console.print(f"\n[bold]{summary}[/bold]")

    if stdout and stdout.count("\n") > 10:
        # long output — show collapsed with option to expand
        lines = stdout.split("\n")
        console.print(f"[dim]({len(lines)} lines of output)[/dim]")
        # show first 5 lines as preview
        console.print("\n".join(lines[:5]))
        if len(lines) > 5:
            console.print(f"[dim]... {len(lines)-5} more lines[/dim]")
    elif stdout:
        console.print(Panel(stdout, border_style="green" if success else "red"))

    if stderr and not success:
        console.print(Panel(stderr, title="error", border_style="red"))
```

---

### 13H — Automatic error recovery

**The problem it solves:** when a command fails, you're left staring at a cryptic error message and have to figure out the fix yourself. This is the most frustrating moment in using any terminal tool.

**How it works:** when `executor.py` gets a non-zero return code, automatically send the failed command + its error message back to the LLM and ask "what went wrong and what's the fix?" The LLM diagnoses the error and suggests a corrected command. You confirm and run it.

Add to `executor.py`:

```python
def run(command: str) -> dict:
    result = subprocess.run(
        command, shell=True, executable="/bin/zsh",
        capture_output=True, text=True
    )
    return {
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
        "returncode": result.returncode,
        "success": result.returncode == 0,
        "command": command
    }
```

Add to `translate.py`:

```python
def diagnose_error(command: str, error: str, context: str) -> dict:
    """
    When a command fails, ask the LLM to diagnose and suggest a fix.
    Returns the same JSON schema as translate() — a corrected command.
    """
    prompt = (
        f"Environment:\n{context}\n\n"
        f"This command failed:\n{command}\n\n"
        f"Error message:\n{error}\n\n"
        f"Diagnose what went wrong and return a corrected command. "
        f"Use the same JSON schema as always."
    )
    return translate(prompt, context)  # reuses the same translate logic
```

In `main.py`, after a failed run:

```python
if not output["success"] and output["stderr"]:
    console.print("[yellow]command failed — diagnosing...[/yellow]")
    fix = diagnose_error(result["command"], output["stderr"], context_str)
    
    if "error" not in fix and fix.get("command"):
        console.print(f"\n[yellow]suggested fix:[/yellow]")
        if confirm(fix):  # show the fix and ask to run it
            fixed_output = run(fix["command"])
            show_output(fixed_output["stdout"], fixed_output["stderr"], fixed_output["success"])
            log(f"[auto-fix] {transcript}", fix["command"],
                fix["risk"], fixed_output["success"], fixed_output["stdout"])
```

---

### Phase 13 updated folder impact

No new files needed. All changes are additions to existing files:

| File | What changes |
|------|-------------|
| `translate.py` | + `build_user_message()`, `is_explain_request()`, `explain_last_command()`, `summarise_output()`, `diagnose_error()` |
| `context.py` | + `get_filesystem_context()`, merged into `get_context()` |
| `transcribe.py` | + `DEVELOPER_VOCAB_PROMPT` added to `transcribe()` call |
| `safety.py` | + `clarification` field handling |
| `app_gui.py` | + global hotkey with pynput |
| `ui.py` | + summary display, collapsed long output |
| `main.py` | + clarification loop, explain mode, error recovery |
| `prompts/system.txt` | + `clarification` field in schema |

### New dependency

```
pynput==1.7.7    # global hotkey detection
```

### Build order for Phase 13

Do these in order — each one is independently testable:

1. History injection (13A) — test by saying "do that again" after any command
2. Smart Whisper prompt (13D) — immediate, one line, test by saying technical words
3. Filesystem awareness (13C) — test by saying "delete the [thing in your directory]"
4. Error recovery (13H) — test by running a command on a file that doesn't exist
5. Output summarisation (13G) — test with `find / -name "*.log"` or similar
6. Clarification follow-ups (13B) — test with an intentionally vague request
7. Explanation mode (13F) — test by saying "explain that" after any command
8. Global hotkey (13E) — test last, needs the GUI app running

