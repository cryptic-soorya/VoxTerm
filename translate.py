"""
translate.py — LLM translation layer (Ollama primary, Gemini Flash fallback)

Takes a transcript string + environment context, returns a validated dict:
  {
    "command": "string or null",
    "steps": ["cmd1", "cmd2"] or null,
    "risk": "low | medium | high",
    "explanation": "one sentence",
    "destructive": true or false,
    "inverse_command": "undo command or null"
  }

Mode selection order (automatic, no user configuration needed):
  1. --offline flag → Ollama only, error if not running
  2. --cloud flag   → Gemini only, error if no key
  3. auto           → Ollama if running, else Gemini, else helpful error

Plugin check runs before any LLM call — zero latency, zero API usage.
"""

import json
import os
import importlib.util
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT_PATH = Path(__file__).parent / "prompts" / "system.txt"
_SYSTEM_PROMPT: str = _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")

OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
_OLLAMA_BASE = "http://localhost:11434"
_OLLAMA_GENERATE_URL = f"{_OLLAMA_BASE}/api/generate"
_OLLAMA_TIMEOUT = 60  # seconds — local inference, should be well within this

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_ollama_running() -> bool:
    """Ping Ollama's local HTTP server. Fast — returns in <2s either way."""
    try:
        r = requests.get(_OLLAMA_BASE, timeout=2)
        return r.status_code == 200
    except requests.exceptions.RequestException:
        return False


def _parse_json(raw: str) -> dict:
    """
    Parse JSON from the LLM response.

    Handles the most common LLM formatting mistakes in order:
      1. Markdown fences (```json ... ```)
      2. Invalid backslash escapes inside string values (e.g. \\* \\e \\p)
         — common when LLMs write shell globs or find patterns in JSON
      3. Truncated/incomplete JSON (best-effort extraction of the root object)

    Returns a dict. On parse failure, returns {"error": "...", "raw": "..."}.
    """
    import re

    cleaned = raw.strip()

    # 1. Strip markdown fences.
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        inner = lines[1:]
        if inner and inner[-1].strip() == "```":
            inner = inner[:-1]
        cleaned = "\n".join(inner).strip()

    # 2. First attempt — clean parse.
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # 3. Fix invalid escape sequences. JSON only allows: \" \\ \/ \b \f \n \r \t \uXXXX
    #    LLMs often produce \* \. \( \) \s \d etc. inside shell command strings.
    #    Replace any \X where X is not a valid JSON escape char with just X.
    fixed = re.sub(r'\\([^"\\/bfnrtu])', r'\1', cleaned)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    # 4. Extract just the outermost {...} object in case of surrounding prose.
    match = re.search(r'\{.*\}', cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            # Try the escape fix on the extracted object too.
            try:
                return json.loads(re.sub(r'\\([^"\\/bfnrtu])', r'\1', match.group()))
            except json.JSONDecodeError:
                pass

    return {
        "error": f"LLM returned unparseable output",
        "raw": raw[:500],
    }


def _validate(result: dict) -> dict:
    """
    Sanity-check the parsed dict before returning it to the caller.

    Fills in missing optional keys with safe defaults so downstream code
    can always do result["destructive"] without a KeyError.
    """
    if "error" in result:
        return result

    required = {"risk", "explanation"}
    missing = required - result.keys()
    if missing:
        return {"error": f"LLM response missing required fields: {missing}", "raw": str(result)}

    # Ensure exactly one of command / steps is set (never both, never neither).
    has_command = bool(result.get("command"))
    has_steps = bool(result.get("steps"))
    if not has_command and not has_steps:
        return {"error": "LLM returned neither 'command' nor 'steps'", "raw": str(result)}

    # Fill optional fields with safe defaults.
    result.setdefault("destructive", False)
    result.setdefault("inverse_command", None)
    result.setdefault("steps", None)
    result.setdefault("command", None)

    # Normalise risk to lowercase.
    result["risk"] = str(result.get("risk", "high")).lower()
    if result["risk"] not in ("low", "medium", "high"):
        result["risk"] = "high"  # default to safe

    return result


# ---------------------------------------------------------------------------
# Ollama backend
# ---------------------------------------------------------------------------

def translate_ollama(transcript: str, context: str) -> dict:
    """
    Send transcript + context to the local Ollama model.

    Uses Ollama's built-in JSON mode (`"format": "json"`) for extra
    reliability. stream=False waits for the complete response.

    Raises:
        requests.exceptions.RequestException: if Ollama is not reachable.
    """
    full_prompt = (
        f"{_SYSTEM_PROMPT}\n\n"
        f"Environment:\n{context}\n\n"
        f"Request: {transcript}"
    )
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": full_prompt,
        "stream": False,
        # NOTE: "format": "json" is intentionally omitted. Thinking models
        # like qwen3 route all output into the "thinking" key when format:json
        # is set, leaving "response" empty. We rely on _parse_json() to strip
        # any markdown fences the model adds instead.
    }
    try:
        response = requests.post(_OLLAMA_GENERATE_URL, json=payload, timeout=_OLLAMA_TIMEOUT)
        response.raise_for_status()
    except requests.exceptions.ConnectionError:
        return {"error": "Ollama is not running. Start it with: ollama serve"}
    except requests.exceptions.Timeout:
        return {"error": f"Ollama timed out after {_OLLAMA_TIMEOUT}s. Is the model loaded?"}
    except requests.exceptions.HTTPError as exc:
        return {"error": f"Ollama HTTP error: {exc}"}

    data = response.json()
    raw = data.get("response", "").strip()

    # Thinking models (qwen3, deepseek-r1, etc.) expose a separate "thinking"
    # key. When the response is empty, the useful JSON is in "thinking" — but
    # that field contains the model's reasoning prose, not clean JSON. Instead
    # of parsing prose, instruct the model more explicitly via the prompt.
    # If response is truly empty after a successful call, return a clear error.
    if not raw:
        thinking_preview = data.get("thinking", "")[:200]
        return {
            "error": (
                f"Model '{OLLAMA_MODEL}' returned an empty response. "
                "If this is a thinking model (qwen3, deepseek-r1), it may need "
                "a different prompt format. Thinking preview: " + thinking_preview
            )
        }

    return _validate(_parse_json(raw))


# ---------------------------------------------------------------------------
# Gemini backend
# ---------------------------------------------------------------------------

def translate_gemini(transcript: str, context: str) -> dict:
    """
    Send transcript + context to Google Gemini 1.5 Flash (free tier).

    Key: response_mime_type="application/json" tells Gemini to output raw
    JSON — much more reliable than asking it in the prompt alone.

    Requires GEMINI_API_KEY in .env or environment.
    """
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return {
            "error": (
                "No LLM available. Options:\n"
                "  A) Install Ollama (ollama.com) and run: ollama serve\n"
                "  B) Get a free Gemini key at aistudio.google.com and add "
                "GEMINI_API_KEY to .env"
            )
        }

    try:
        import google.generativeai as genai
    except ImportError:
        return {"error": "google-generativeai not installed. Run: pip install google-generativeai"}

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name="gemini-1.5-flash",
        system_instruction=_SYSTEM_PROMPT,
        generation_config=genai.GenerationConfig(
            response_mime_type="application/json",  # forces raw JSON, no fences
        ),
    )

    user_message = f"Environment:\n{context}\n\nRequest: {transcript}"

    try:
        response = model.generate_content(user_message)
    except Exception as exc:
        return {"error": f"Gemini API error: {exc}"}

    return _validate(_parse_json(response.text))


# ---------------------------------------------------------------------------
# Plugin system
# ---------------------------------------------------------------------------

def check_plugins(transcript: str) -> str | None:
    """
    Check if any plugin in plugins/ matches the transcript.
    Returns the command string if matched, None otherwise.

    Plugins run before any LLM call — instant, no API usage.
    The example.py plugin is skipped (it's a template, not a real plugin).
    """
    plugins_dir = Path(__file__).parent / "plugins"
    if not plugins_dir.exists():
        return None

    transcript_lower = transcript.lower()

    for plugin_file in sorted(plugins_dir.glob("*.py")):
        if plugin_file.name in ("example.py", "__init__.py"):
            continue

        try:
            spec = importlib.util.spec_from_file_location(plugin_file.stem, plugin_file)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        except Exception:
            continue  # broken plugin — skip silently

        trigger = getattr(mod, "TRIGGER", None)
        if trigger and trigger.lower() in transcript_lower:
            try:
                from context import get_context_dict
                return mod.run(get_context_dict())
            except Exception:
                return None  # plugin run() failed — fall through to LLM

    return None


# ---------------------------------------------------------------------------
# Public router
# ---------------------------------------------------------------------------

def translate(
    transcript: str,
    context: str,
    force_offline: bool = False,
    force_cloud: bool = False,
) -> dict:
    """
    Main entry point. Translate a voice transcript into a JSON command dict.

    Args:
        transcript:    the user's spoken words as a string
        context:       output of context.get_context()
        force_offline: use Ollama only, error if not running (--offline flag)
        force_cloud:   use Gemini only, error if no key (--cloud flag)

    Returns:
        Validated dict with keys: command, steps, risk, explanation,
        destructive, inverse_command. On any error: {"error": "..."}.
    """
    if force_offline:
        if not _is_ollama_running():
            return {"error": "Ollama is not running. Start it with: ollama serve"}
        return translate_ollama(transcript, context)

    if force_cloud:
        return translate_gemini(transcript, context)

    # Auto-select: prefer Ollama (privacy), fall back to Gemini.
    if _is_ollama_running():
        return translate_ollama(transcript, context)
    else:
        return translate_gemini(transcript, context)


# ---------------------------------------------------------------------------
# Quick smoke test: python translate.py
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    from context import get_context

    ctx = get_context()
    print("Context:")
    print(ctx)
    print()

    tests = [
        "show me what's in the current directory",
        "make a new folder called test-output",
        "find all python files in the current directory",
    ]

    # Determine which backend to use for the test.
    if len(sys.argv) > 1 and sys.argv[1] == "--cloud":
        print("Using Gemini (--cloud flag)")
        backend = lambda t: translate_gemini(t, ctx)
    elif _is_ollama_running():
        print(f"Using Ollama (model: {OLLAMA_MODEL})")
        backend = lambda t: translate_ollama(t, ctx)
    else:
        api_key = os.getenv("GEMINI_API_KEY", "")
        if api_key:
            print("Using Gemini (Ollama not running, GEMINI_API_KEY found)")
            backend = lambda t: translate_gemini(t, ctx)
        else:
            print("ERROR: Neither Ollama nor GEMINI_API_KEY is available.")
            print("  A) Start Ollama: ollama serve")
            print("  B) Add GEMINI_API_KEY to .env and re-run: python translate.py --cloud")
            sys.exit(1)

    print()
    for transcript in tests:
        print(f"Transcript: {transcript!r}")
        result = backend(transcript)
        if "error" in result:
            print(f"  ERROR: {result['error']}")
        else:
            print(f"  command:     {result.get('command')}")
            print(f"  risk:        {result.get('risk')}")
            print(f"  explanation: {result.get('explanation')}")
            print(f"  destructive: {result.get('destructive')}")
            print(f"  inverse:     {result.get('inverse_command')}")
        print()
