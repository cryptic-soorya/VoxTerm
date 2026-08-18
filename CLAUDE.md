# CLAUDE.md — VoxTerm

This file tells Claude everything about this project so we can pick up exactly where we left off in any session.

---

## What this project is

**VoxTerm** is a voice-controlled terminal assistant for macOS (Apple Silicon). The user speaks plain English, the tool transcribes it locally using Whisper, translates it into a shell command using an LLM, assesses the risk level, and asks for confirmation before running anything destructive. Everything runs on-device by default. No paid APIs. No subscriptions.

**One-liner for explaining it:** "It's like GitHub Copilot for your terminal, but voice-first and completely free."

---

## Important: no paid APIs

This project uses **zero paid services**. The LLM layer has two modes:

| Mode | Tool | Cost | Requires |
|------|------|------|----------|
| Default (offline) | Ollama + Mistral/Llama3 | Free forever | Ollama installed locally |
| Fallback (free cloud) | Google Gemini 2.0 Flash | Free tier: 1500 req/day | Google account, free API key |

There is no Anthropic/OpenAI API key anywhere in this project. If you see one, remove it.

**Why Gemini and not others?**
- Gemini Flash free tier is genuinely generous (1500 requests/day, no credit card)
- Google AI Studio issues free keys instantly at aistudio.google.com
- The `google-genai` Python SDK (the new one — `google-generativeai` is deprecated) is simple and well-maintained
- Gemini follows structured JSON instructions reliably

---

## Project status

- [x] Phase 1: audio capture + transcription (audio.py + transcribe.py)
- [x] Phase 2: LLM translation + JSON parsing (translate.py)
- [x] Phase 3: safety gate + confirmation UI (safety.py)
- [x] Phase 4: execution + output capture (executor.py)
- [x] Phase 5: history logging (history.py)
- [x] Phase 6: undo stack (undo.py)
- [x] Phase 7: Rich terminal UI polish (ui.py)
- [x] Phase 8: alias learning system (aliases.py)
- [x] Phase 9: plugin system (plugins/)
- [x] Phase 10: CLI flags via Click (main.py)
- [ ] Phase 11: README + demo GIF + GitHub release (README done; demo GIF + release pending)
- [x] Phase 12: distribution (app_gui.py, PyInstaller, DMG, website)
- [x] Phase 13: intelligence upgrades (history RAG, clarifications, filesystem context, …)
- [x] Phase 14: pip packaging — code moved into `voxterm/` package, `pyproject.toml`, `voxterm` console script

Update this checklist as phases are completed.

---

## Folder structure

As of Phase 14, all source code lives in the `voxterm/` package (installable via `pip install -e .`; console script `voxterm` → `voxterm.main:cli`). User data lives in `~/.voxterm/`, not in the repo.

```
terminaltalker/              ← repo root
├── voxterm/                 ← the Python package
│   ├── __init__.py          ← package docstring + __version__
│   ├── main.py              ← entry point, wires everything together, Click CLI
│   ├── audio.py             ← mic recording + WebRTCVAD silence detection
│   ├── transcribe.py        ← faster-whisper model wrapper (local inference)
│   ├── translate.py         ← LLM call (Ollama primary, Gemini fallback), JSON parsing
│   ├── safety.py            ← risk gate logic, confirmation UI, hard overrides (_FORCE_HIGH)
│   ├── executor.py          ← subprocess runner, output capture, dry-run mode
│   ├── history.py           ← SQLite read/write for command history
│   ├── undo.py              ← undo stack: stores inverse commands for reversible ops
│   ├── aliases.py           ← alias learning: detects repeated requests, saves shortcuts
│   ├── context.py           ← system context: cwd, username, OS version, shell type
│   ├── ui.py                ← Rich terminal display: panels, colors, spinners, prompts
│   ├── prompts/
│   │   └── system.txt       ← the LLM system prompt (edit this to tune behaviour)
│   └── plugins/
│       └── example.py       ← example plugin
├── app_gui.py               ← rumps menu bar app (GUI entry point, PyInstaller target)
├── voxterm.sh               ← shell wrapper sourced by the linked-terminal feature
├── voxterm.spec             ← PyInstaller config
├── build.sh                 ← PyInstaller → create-dmg build script
├── pyproject.toml           ← packaging metadata, deps, console script
├── setup.cfg                ← per-tool config (pytest, flake8)
├── requirements.txt         ← pinned deps for dev installs
├── assets/                  ← icon.icns, dmg-background.png
├── website/                 ← React landing page (Vite + Tailwind)
├── LICENSE                  ← MIT
├── CLAUDE.md / PLAN.md      ← project docs (gitignored)
└── README.md                ← public-facing docs

~/.voxterm/                  ← user data (created at runtime)
├── history.db               ← SQLite command history
└── aliases.json             ← saved aliases
```

Imports inside the package are relative (`from .history import recent`). Entry points from outside the package (app_gui.py, `__main__` smoke tests) use absolute `voxterm.` imports. Run the CLI as `voxterm` (installed) or `python -m voxterm.main`.

---

## Tech stack

| Tool | Purpose | Why this one |
|------|---------|-------------|
| Python 3.11+ | Language | Best ecosystem for audio + ML + CLI |
| PyAudio | Mic capture | Low-level audio stream access |
| WebRTCVAD | Voice activity detection | Google's VAD library, accurate and fast |
| faster-whisper | Transcription | 4x faster than openai-whisper, CTranslate2 backend optimised for Apple Silicon |
| Ollama | LLM inference (primary) | Runs Mistral/Llama3 locally, free forever, no internet needed |
| google-genai | LLM inference (fallback) | Gemini 2.0 Flash free tier, 1500 req/day, no payment required |
| subprocess | Shell execution | Python built-in, captures stdout/stderr |
| SQLite3 | History storage | Built into Python, zero setup, local |
| Rich | Terminal UI | Beautiful output, panels, spinners, colors |
| Click | CLI framework | Professional CLI flags and commands |
| python-dotenv | Env var loading | Keeps API key out of code |
| pyttsx3 | Text-to-speech (optional) | Read command output back to user |

---

## LLM mode selection logic

In translate.py, mode is selected in this order:

1. If `--offline` flag is passed → use Ollama, error if Ollama not running
2. If Ollama is running (checked via ping to localhost:11434) → use Ollama automatically
3. If Ollama is not running and GEMINI_API_KEY exists in .env → use Gemini Flash
4. If neither → print a helpful error explaining how to set up either option

This means offline-first by default, Gemini only as an automatic fallback. The user never has to think about it.

---

## The system prompt (summary)

The full prompt lives in `prompts/system.txt`. Key rules it enforces:

1. Always return valid JSON only — no prose, no markdown fences, no backticks
2. Assess risk as low / medium / high using defined rules
3. For multi-step requests, return steps as an array, command as null
4. Never combine a destructive step with a safe step in one command string
5. If the request is ambiguous or unsafe, return an error object
6. Always use the context (cwd, username, shell) to make commands accurate

JSON schema the LLM must return:
```json
{
  "command": "string or null",
  "steps": ["cmd1", "cmd2"] or null,
  "risk": "low | medium | high",
  "explanation": "one sentence plain English",
  "destructive": true or false,
  "inverse_command": "undo command or null if not reversible"
}
```

---

## Safety rules (hardcoded, LLM cannot override)

These are enforced in safety.py regardless of what risk level the LLM returns:

- Any command containing `rm` → forced to HIGH
- Any command containing `sudo` → forced to HIGH
- Any command containing `chmod` or `chown` → forced to HIGH
- Any command with `-r` or `-rf` flag → forced to HIGH
- Any command touching home directory root directly → forced to HIGH
- HIGH risk commands require typing "yes" in full — never a single keypress

---

## Risk gate behaviour

| Risk | What happens |
|------|-------------|
| low | Runs immediately. Logs to history. |
| medium | Shows command + explanation. Waits for Y keypress. |
| high | Full warning panel. Must type "yes" to proceed. |
| dry-run mode | Shows everything, runs nothing. All risk levels. |

---

## Context injected into every LLM call

Collected in context.py and prepended to the user message:

```
CWD: /Users/soorya/projects/myapp
USER: soorya
SHELL: zsh
OS: macOS 15.0 (Apple Silicon)
TIME: 2026-04-03 14:32
```

---

## Undo system

- After every reversible command runs, `inverse_command` from the JSON is pushed to an in-memory undo stack
- User can say "undo that" or run `voxterm undo`
- Undo commands are always treated as MEDIUM risk (shown, confirmed before running)
- Non-reversible commands (rm etc.) push null — undo is disabled for those
- Undo stack is in-memory only — resets when voxterm exits (intentional, safer this way)

---

## Alias learning

- aliases.json stores named shortcuts: `{"clean": "rm -rf node_modules && npm install"}`
- If the LLM detects a transcript matches a saved alias, it uses the stored command directly
- If the same intent appears 3+ times in history, the tool offers to save it as an alias
- User can also manually save: `voxterm alias save <name>`

---

## Plugin system

Plugins live in `plugins/`. Each plugin is a Python file with:
```python
TRIGGER = "deploy"
DESCRIPTION = "Deploy the app"

def run(context: dict) -> str:
    return "npm run build && netlify deploy --prod"
```

Plugins are checked before calling any LLM — zero latency, zero API usage.

---

## CLI flags

```
voxterm              ← default: listen, auto-select Ollama or Gemini
voxterm --dry-run    ← full pipeline, no execution
voxterm --offline    ← force Ollama, error if not running
voxterm --cloud      ← force Gemini, error if no GEMINI_API_KEY
voxterm --history    ← show last 20 commands
voxterm undo         ← run the inverse of the last command
voxterm alias list   ← show saved aliases
voxterm alias save <name>  ← save last command as alias
```

---

## Key decisions and why

**Why Ollama as primary, not Gemini?**
Privacy. Your terminal commands reveal a lot about your project structure, file names, and workflow. Keeping that local by default is the right call. Gemini only sees your commands if Ollama isn't available.

**Why Gemini over other free options?**
Gemini 2.0 Flash free tier is the most generous free LLM API available right now — 1500 requests/day, no credit card, instant key from aistudio.google.com. Groq is also free but rate-limited more aggressively. Gemini follows JSON instructions very reliably.

**Why faster-whisper instead of openai-whisper?**
faster-whisper uses CTranslate2 as its inference backend, optimised for CPU and Apple Silicon. Runs the same Whisper models 2-4x faster with less memory. On an M4 MacBook, the base model transcribes a 5-second clip in ~0.4 seconds.

**Why JSON output from the LLM?**
Structured output means your app reads `result["risk"]` reliably every time without parsing prose. The system prompt must say "no markdown, no backticks" or both Ollama and Gemini will wrap JSON in fences.

**Why SQLite for history?**
Zero setup, file-based, built into Python. Gitignored. Users own their data completely.

**Why keep the system prompt in a text file?**
So you can tweak LLM behaviour without touching Python code. Changing how risk is assessed is just editing a text file.

---

## Things to be careful about

- Never run subprocess commands without the safety gate having approved them first
- The `.env` file must be in `.gitignore` — GEMINI_API_KEY must never be committed
- User data (history.db, aliases.json) lives in `~/.voxterm/` — never in the repo
- The undo stack is in-memory only — do not persist it to disk (too risky)
- Test all new executor logic with `--dry-run` first
- When calling Gemini, explicitly set `response_mime_type="application/json"` — this forces JSON output without fences

---

## How to run (once built)

```bash
python3 -m venv venv
source venv/bin/activate
pip install -e ".[all]"      # editable install with GUI + hotkey extras

# Option A: fully offline (install Ollama first from ollama.com)
ollama pull llama3.2:3b
voxterm

# Option B: free cloud fallback (get free key from aistudio.google.com)
cp .env.example .env   # add your GEMINI_API_KEY
voxterm

# Other modes
voxterm --dry-run     # safe demo mode
voxterm --offline     # force Ollama
voxterm --cloud       # force Gemini
voxterm shell-setup   # print the cd shell wrapper (append to ~/.zshrc)

# Equivalent without the console script: python -m voxterm.main
```

---

## Environment variables

```
GEMINI_API_KEY=your_free_key_from_aistudio.google.com
OLLAMA_MODEL=llama3.2:3b      # or mistral, phi3, gemma2 etc. (default: llama3.2:3b)
WHISPER_MODEL=base            # tiny | base | small | medium
VOCTERM_CONFIRM_TIMEOUT=30    # seconds before medium-risk auto-cancels
```

GEMINI_API_KEY is optional — only needed if you want the cloud fallback when Ollama isn't running.

---

## Phase 12 additions (distribution)

**New files:**

| File | Purpose |
|------|---------|
| `app_gui.py` | rumps menu bar app — GUI entry point for the distributable app |
| `voxterm.spec` | PyInstaller config — tells it how to bundle the app |
| `build.sh` | one-command script: PyInstaller → create-dmg → ready to upload |
| `assets/icon.icns` | app icon in macOS format |
| `assets/dmg-background.png` | background image shown in the DMG installer window |
| `website/` | React landing page (Vite + Tailwind + Framer Motion) — replaces the static `docs/index.html` approach |

**New dependencies:**
```
rumps==0.4.0        # menu bar GUI
pyinstaller==6.5.0  # app bundler
```
create-dmg is installed via Homebrew, not pip.

**Two entry points:**
- `voxterm` (or `python -m voxterm.main`) — CLI mode for developers
- `python app_gui.py` — GUI mode (menu bar app), used by PyInstaller
Both use the same backend. app_gui.py is just a different shell on top.

**Key Info.plist keys in voxterm.spec:**
- `LSUIElement: True` — makes it a menu bar app, no Dock icon
- `NSMicrophoneUsageDescription` — required for mic permission on macOS
- `CFBundleShortVersionString` — version number shown in Finder

**Distribution flow:**
```
build.sh
  → PyInstaller bundles Python + deps → dist/voxterm.app
  → create-dmg wraps .app → dist/voxterm-1.0.0.dmg
  → upload DMG to GitHub Releases
  → landing page (website/) links to GitHub Releases download URL
  → build website with `cd website && npm run build` → deploy dist/ to GitHub Pages or Vercel
```

**Security warning note:**
Without Apple code signing ($99/yr Apple Developer account), macOS shows
"unidentified developer" on first open. Fix: right-click → Open → Open.
Document this clearly on the landing page. It's a one-time step.
For the CLI / developer audience this is completely normal and expected.

**Gemini as primary for GUI users:**
Non-technical users won't have Ollama installed. In app_gui.py, flip the
default: try Gemini first (if key exists), fall back to Ollama. The
Preferences menu item lets users paste their free Gemini key into a native
dialog — no Terminal, no .env file editing.


---

## Phase 13 — Intelligence upgrades summary

Eight targeted improvements that fix real failure modes. All are additions to existing files — no new modules needed except `pynput` for hotkeys.

### Features added

| Feature | File(s) changed | What it fixes |
|---------|----------------|---------------|
| History injection (RAG) | `translate.py`, `history.py` | LLM is stateless — can't handle "do that again" or "same but for X" |
| Clarification follow-ups | `translate.py`, `safety.py`, `main.py`, `prompts/system.txt` | Ambiguous requests fail hard instead of asking one question |
| Filesystem awareness | `context.py` | LLM doesn't know what files/folders actually exist in cwd |
| Smart Whisper prompt | `transcribe.py` | Technical vocabulary (git, npm, chmod) gets misheard |
| Global hotkey | `app_gui.py` | User must click menu bar icon — kills the flow |
| Explanation mode | `translate.py`, `main.py` | Tool teaches nothing — just runs commands silently |
| Output summarisation | `executor.py`, `translate.py`, `ui.py` | Long output (find, ps, git log) is dumped raw, unreadable |
| Error recovery | `executor.py`, `translate.py`, `main.py` | Failed commands leave user with a cryptic error, no help |

### New JSON schema field

`clarification` added to the LLM response schema:
```json
{
  "command": null,
  "clarification": "Which folder should I look in?",
  "risk": "low",
  "explanation": "",
  "destructive": false,
  "inverse_command": null,
  "steps": null
}
```
When `clarification` is non-null, the app speaks the question, listens for an answer, combines original + answer into a new transcript, and re-runs the pipeline. No starting over.

### How history injection works (RAG pattern)

Every LLM call now includes the last 7 commands from SQLite, formatted as text, prepended to the user message. The model can reason about references ("that", "the same", "before") because it has the actual history in its context window. This is the same pattern used by Cursor, ChatGPT memory, and every "AI that knows about you" product.

### Key constants to know

```python
# transcribe.py
DEVELOPER_VOCAB_PROMPT = "git commit push pull..."  # biases Whisper toward dev vocab

# executor.py  
SUMMARISE_THRESHOLD_LINES = 10  # output longer than this gets summarised

# translate.py
EXPLAIN_TRIGGERS = ["explain that", "what did that do", ...]  # triggers explanation mode
```

### New dependency

```
pynput==1.7.7    # global hotkey — add to requirements.txt
```

### macOS `say` command

Used for speaking clarification questions and explanations back to the user.
Built into macOS — no installation needed, completely free.
```python
import subprocess
subprocess.run(["say", "Which folder did you mean?"])
```
This is optional — wrap in a user preference to enable/disable voice output.

