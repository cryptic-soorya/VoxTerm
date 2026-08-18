<div align="center">

# VoxTerm

**Voice-controlled terminal for macOS. Speak plain English. Review the command. Run it.**

[voxterm.pages.dev](https://voxterm.pages.dev)

[![PyPI version](https://img.shields.io/pypi/v/voxterm?color=blue&label=pip%20install%20voxterm)](https://pypi.org/project/voxterm/)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-macOS%20%28Apple%20Silicon%29-lightgrey)](https://www.apple.com/mac/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Cost](https://img.shields.io/badge/cost-completely%20free-brightgreen)](https://ollama.com)
[![GitHub stars](https://img.shields.io/github/stars/cryptic-soorya/VoxTerm?style=flat&color=yellow)](https://github.com/cryptic-soorya/VoxTerm/stargazers)
[![Downloads](https://img.shields.io/github/downloads/cryptic-soorya/VoxTerm/total?label=DMG%20downloads&color=orange)](https://github.com/cryptic-soorya/VoxTerm/releases)

<!-- demo GIF goes here — record with Kap or asciinema, save as demo.gif, then uncomment: -->
<!-- ![VoxTerm demo](demo.gif) -->

</div>

---

## What it does

You say: *"find all Python files modified in the last day"*

VoxTerm transcribes it locally with Whisper, converts it to a real shell command with a local LLM, shows you the command and its risk level, and runs it after you confirm.

```
$ voxterm
[●] Listening...
[✓] "find all Python files modified in the last day"

  Command   find . -name "*.py" -mtime -1
  Risk      low — read-only search
  
./voxterm/main.py
./voxterm/translate.py
./voxterm/safety.py
```

High-risk commands require typing `"yes"` in full. You stay in control.

---

## Why this exists

Every voice-to-terminal tool I found either:
- Required a paid API (OpenAI, Anthropic)
- Ran your voice through someone's cloud
- Didn't have a safety layer

VoxTerm runs entirely on your machine by default. Your terminal commands never leave your laptop. It's free forever.

---

## Zero paid APIs

| Mode | Backend | Cost | Requires |
|------|---------|------|----------|
| **Default (offline)** | Ollama + Mistral / Llama 3 | Free forever | [Ollama](https://ollama.com) installed locally |
| **Fallback (cloud)** | Google Gemini 2.0 Flash | Free tier: 1500 req/day | Free key from [aistudio.google.com](https://aistudio.google.com) |

VoxTerm auto-detects which backend to use — Ollama if it's running, Gemini if you have a key set, clear error if neither.

---

## Install

**Using the `.app` DMG?** VoxTerm isn't code-signed or notarized by Apple (that requires a paid Apple Developer account), so Gatekeeper will show *"VoxTerm Not Opened"* on first launch. This isn't malware — just right-click the app → **Open** → **Open** again, or run:
```bash
xattr -dr com.apple.quarantine /Applications/VoxTerm.app
```

**Using pip?**

```bash
brew install portaudio
pip install voxterm
```

**Pick an LLM backend:**

```bash
# Option A — fully offline (recommended)
brew install ollama
ollama pull llama3.2:3b
voxterm

# Option B — free cloud fallback
export GEMINI_API_KEY=your_free_key_from_aistudio
voxterm
```

**Optional — so `cd` actually changes your shell's directory**, install the shell wrapper:

```bash
voxterm shell-setup >> ~/.zshrc
source ~/.zshrc
```

This wraps `voxterm` (and adds a short `vt` alias) so directory changes made by voice propagate to your shell.

---

## Safety layer

Every command is classified before it runs. Hardcoded rules always win over the LLM.

| Risk | When | What happens |
|------|------|-------------|
| **low** | `ls`, `cat`, `git status`, `find` | Runs immediately |
| **medium** | `git push`, `mkdir`, `npm install` | Shows command + reason, waits for `y` |
| **high** | Any `rm`, `sudo`, `chmod`, `chown`, `-rf` | Full warning panel, must type `"yes"` |

The LLM cannot talk its way out of HIGH risk. If the command string contains `rm`, it's HIGH. Period.

```
╔══════════════════════════════════════════╗
║  ⚠  HIGH RISK                           ║
║                                          ║
║  Command   rm -rf build/                ║
║  Why       permanently deletes files    ║
║                                          ║
║  This cannot be undone.                 ║
╚══════════════════════════════════════════╝

Type "yes" to continue:
```

---

## Features

- **Local Whisper transcription** — faster-whisper with CTranslate2 backend, ~0.4s on Apple Silicon
- **Context-aware commands** — injects your cwd, shell type, OS version, and last 7 commands into every LLM call
- **Filesystem awareness** — tells the LLM what files actually exist in your cwd so commands are accurate
- **Undo stack** — say "undo that" to reverse the last reversible command
- **Alias learning** — repeat the same intent 3 times and VoxTerm offers to save it as a named shortcut
- **Plugin system** — drop a `.py` file in `plugins/` to handle specific phrases before any LLM call
- **Clarification loop** — ambiguous requests trigger a follow-up question instead of failing
- **Output summarisation** — long output from `find`, `ps`, `git log` is summarised, not dumped raw
- **Error recovery** — failed commands get an automatic retry suggestion
- **Menu bar app** — `python app_gui.py` runs as a native macOS menu bar icon with a global hotkey

---

## Usage

```
voxterm              listen and run (auto-selects backend)
voxterm --dry-run    full pipeline, no execution — safe for demos
voxterm --offline    force Ollama, error if not running
voxterm --cloud      force Gemini, error if no key
voxterm history      last 20 commands
voxterm undo         reverse the last reversible command
voxterm alias list   show saved shortcuts
voxterm alias save NAME     save last command as a named shortcut
voxterm alias delete NAME   remove a saved shortcut
voxterm shell-setup  print the cd shell wrapper (append to ~/.zshrc)
```

---

## How it works

```
mic input
  → audio.py        PyAudio capture + WebRTCVAD silence detection
  → transcribe.py   faster-whisper (local, no internet)
  → context.py      injects cwd, shell, OS, last 7 commands, filesystem snapshot
  → plugins/        checked first — zero LLM cost if matched
  → translate.py    Ollama or Gemini → structured JSON
  → safety.py       risk override + confirmation UI
  → executor.py     subprocess, output capture, optional summarisation
  → history.py      SQLite log
```

The LLM returns structured JSON every time:

```json
{
  "command": "find . -name '*.py' -mtime -1",
  "risk": "low",
  "explanation": "read-only search, no side effects",
  "destructive": false,
  "inverse_command": null,
  "steps": null
}
```

No prose parsing. `result["risk"]` is always a string.

---

## Tech stack

| Tool | Purpose |
|------|---------|
| [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | Local speech-to-text, 4× faster than openai-whisper |
| [Ollama](https://ollama.com) | Local LLM inference (Mistral, Llama 3, Phi 3, Gemma 2) |
| [Gemini 2.0 Flash](https://aistudio.google.com) | Free cloud fallback (1500 req/day, no credit card) |
| [WebRTCVAD](https://github.com/wiseman/py-webrtcvad) | Google's voice activity detection |
| [Rich](https://github.com/Textualize/rich) | Terminal UI — panels, spinners, colors |
| [Click](https://click.palletsprojects.com) | CLI flags and subcommands |
| SQLite3 | History storage — built into Python, zero setup |

---

## Extending VoxTerm

**Add a plugin** — handles a phrase before any LLM call:

```python
# voxterm/plugins/deploy.py
TRIGGER = "deploy"
DESCRIPTION = "Deploy to production"

def run(context: dict) -> str:
    return "npm run build && netlify deploy --prod"
```

**Tune LLM behaviour** — edit `voxterm/prompts/system.txt`, no Python needed.

**Adjust risk rules** — `voxterm/safety.py`, `_FORCE_HIGH` list.

---

## Contributing

```bash
git clone https://github.com/cryptic-soorya/VoxTerm
cd VoxTerm
brew install portaudio
python3 -m venv venv && source venv/bin/activate
pip install -e ".[all]"
```

Test all changes with `--dry-run` first. PRs that weaken the safety gate need a strong justification.

---

## Roadmap

- [ ] Windows support (via SoundDevice + WSL)
- [ ] Web dashboard for command history
- [ ] More Whisper model options in preferences
- [ ] Shell completion for alias names
- [ ] MCP server mode (use as a tool from Claude / other agents)

---

<div align="center">

MIT License · Built by [@cryptic-soorya](https://github.com/cryptic-soorya)

*No subscriptions. No cloud required. Your terminal stays yours.*

</div>
