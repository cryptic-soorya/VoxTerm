# vocterm

> Speak a command. See it. Confirm it. Done.

<!-- demo GIF goes here — record with Kap or asciinema -->
<!-- ![demo](docs/demo.gif) -->

**vocterm** is a voice-controlled terminal assistant for macOS (Apple Silicon). Speak plain English, get a shell command, review it, run it. Everything runs on your machine — no cloud, no subscriptions, no API fees.

```
100% free  ·  works offline  ·  never runs anything without showing you first
```

---

## How it works

```
you speak  →  Whisper transcribes  →  LLM translates  →  you confirm  →  it runs
```

Every command is shown before it runs. Destructive commands (anything with `rm`, `sudo`, `chmod`) require typing `"yes"` in full — never a single keypress.

---

## Requirements

- macOS 12+ (Apple Silicon recommended)
- Python 3.11+
- [Ollama](https://ollama.com) — for fully offline use (recommended)
- A free [Gemini API key](https://aistudio.google.com) — optional cloud fallback

---

## Install

```bash
git clone https://github.com/yourusername/vocterm
cd vocterm

# install PortAudio (required by PyAudio)
brew install portaudio

# create a virtual environment
python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt
```

---

## Setup

### Option A — Fully offline with Ollama (recommended)

Privacy-first. Your commands never leave your machine.

```bash
# 1. Install Ollama from https://ollama.com
# 2. Pull the model
ollama pull llama3.2:3b

# 3. Copy the example env file
cp .env.example .env

# 4. Start Ollama (if not already running)
ollama serve
```

### Option B — Free cloud with Gemini

No Ollama needed. Uses Google's free API tier (1500 requests/day, no credit card).

```bash
# 1. Get a free key at https://aistudio.google.com
# 2. Add it to your .env
cp .env.example .env
# edit .env and set GEMINI_API_KEY=your_key_here
```

vocterm auto-detects which backend to use — Ollama if it's running, Gemini if a key is set, helpful error if neither.

---

## Mic permission

On first run, macOS will ask for microphone access. Grant it to Terminal (or whichever app you use).

If Terminal doesn't appear in System Settings → Privacy → Microphone, run `python main.py` once — it will trigger the permission prompt.

---

## Usage

Add the shell wrapper to your `.zshrc` so `cd` commands actually work in your shell:

```bash
# add to ~/.zshrc
vt() {
    python3 ~/vocterm/main.py "$@"
    local _vt_cd="/tmp/.vocterm_cd"
    if [[ -f "$_vt_cd" ]]; then
        local _vt_dir=$(cat "$_vt_cd")
        rm -f "$_vt_cd"
        [[ -n "$_vt_dir" && -d "$_vt_dir" ]] && cd "$_vt_dir"
    fi
}
```

Then reload your shell and use `vt` instead of `python main.py`:

```bash
source ~/.zshrc
vt                    # listen and run
vt --dry-run          # show what would run, execute nothing
vt --offline          # force Ollama
vt --cloud            # force Gemini
vt history            # last 20 commands
vt undo               # reverse last reversible command
vt alias list         # show saved shortcuts
vt alias save NAME    # save last command as a shortcut
vt alias delete NAME  # remove a shortcut
```

---

## Risk levels

vocterm classifies every command before showing it to you. The LLM's assessment is a suggestion — hardcoded rules always win.

| Risk | What it looks like | What happens |
|---|---|---|
| **low** | `ls -la`, `cat file.txt`, `git status` | Runs immediately, no prompt |
| **medium** | `git push`, `mkdir foo`, `npm install` | Shows command, asks Y/n |
| **high** | `rm`, `sudo`, `chmod`, `chown`, `-rf` | Full warning panel, must type `"yes"` |

High-risk commands are forced by vocterm regardless of what the LLM thinks. No amount of clever phrasing can convince vocterm to silently delete files.

---

## Plugins

Drop a `.py` file into `plugins/` to add instant shortcuts that bypass the LLM entirely:

```python
# plugins/deploy.py
TRIGGER = "deploy"
DESCRIPTION = "Deploy the app"

def run(context: dict) -> str:
    return "npm run build && netlify deploy --prod"
```

If your transcript contains the trigger word, the plugin command runs. Zero latency, zero API calls.

---

## Aliases

vocterm learns from repetition. Say the same thing 3+ times and it will offer to save it as a named alias:

```bash
vt alias list           # show all saved aliases
vt alias save clean     # save last command as "clean"
vt alias delete clean   # remove it
```

Aliases are stored in `data/aliases.json` — local to your machine, never committed.

---

## Environment variables

Set these in your `.env` file (copy `.env.example` to get started):

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_MODEL` | `llama3.2:3b` | Model to use with Ollama |
| `WHISPER_MODEL` | `base` | Whisper model size: `tiny` / `base` / `small` / `medium` |
| `GEMINI_API_KEY` | *(none)* | Free key from [aistudio.google.com](https://aistudio.google.com) |
| `VOCTERM_CONFIRM_TIMEOUT` | `30` | Seconds before medium-risk auto-cancels |
| `VOCTERM_EXEC_TIMEOUT` | `30` | Max seconds a command is allowed to run |

---

## Project structure

```
vocterm/
├── main.py          ← CLI entry point (Click)
├── audio.py         ← mic recording + VAD silence detection
├── transcribe.py    ← Whisper transcription
├── translate.py     ← Ollama / Gemini LLM translation
├── context.py       ← injects CWD, shell, OS into every LLM call
├── safety.py        ← hardcoded risk overrides + confirmation UI
├── executor.py      ← subprocess runner + cd interception
├── history.py       ← SQLite command log
├── undo.py          ← in-memory undo stack
├── aliases.py       ← named command shortcuts
├── ui.py            ← Rich terminal display + animations
├── prompts/
│   └── system.txt   ← LLM system prompt (edit to tune behaviour)
├── plugins/         ← drop .py files here for instant shortcuts
├── data/            ← history.db + aliases.json (gitignored)
└── requirements.txt
```

---

## Free, forever

| Layer | Tool | Cost |
|---|---|---|
| Transcription | faster-whisper (local) | Free |
| LLM (primary) | Ollama + llama3.2:3b (local) | Free |
| LLM (fallback) | Gemini 1.5 Flash | Free tier: 1500 req/day |
| Everything else | Python stdlib + open source | Free |

---

## Licence

MIT
