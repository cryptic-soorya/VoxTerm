"""
aliases.py — saved command shortcuts + repeat detection

Two jobs:
  1. match()           — check if a transcript contains a saved alias name,
                         return the stored command (skips the LLM entirely)
  2. check_for_repeat() — scan recent history for similar requests; returns
                         True when the same intent has appeared 3+ times,
                         triggering an offer to save it as an alias

Aliases are stored in ~/.voxterm/aliases.json — local to the user.
"""

import json
from pathlib import Path

ALIASES_PATH = Path.home() / ".voxterm" / "aliases.json"


def load() -> dict[str, str]:
    """Return all saved aliases as {name: command}. Empty dict if none saved."""
    if ALIASES_PATH.exists():
        try:
            return json.loads(ALIASES_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save(name: str, command: str):
    """Add or overwrite an alias. Creates ~/.voxterm/ if it doesn't exist."""
    aliases = load()
    aliases[name.strip().lower()] = command
    ALIASES_PATH.parent.mkdir(exist_ok=True)
    ALIASES_PATH.write_text(json.dumps(aliases, indent=2), encoding="utf-8")


def delete(name: str) -> bool:
    """Remove an alias by name. Returns True if it existed, False if not."""
    aliases = load()
    key = name.strip().lower()
    if key not in aliases:
        return False
    del aliases[key]
    ALIASES_PATH.write_text(json.dumps(aliases, indent=2), encoding="utf-8")
    return True


def match(transcript: str) -> str | None:
    """
    Check if the transcript contains a saved alias name.
    Returns the stored command string if matched, None otherwise.

    Matching is case-insensitive and checks for whole-word presence.
    e.g. alias "clean" matches "clean the project" but not "cleaning".
    """
    transcript_lower = transcript.lower()
    for name, command in load().items():
        # Whole-word match: alias name must appear as a standalone word
        import re
        if re.search(rf'\b{re.escape(name)}\b', transcript_lower):
            return command
    return None


def check_for_repeat(transcript: str) -> bool:
    """
    Return True if a very similar request has been made 3+ times in
    the last 50 commands — signal to offer saving it as an alias.

    Matches on the first 25 characters of the transcript (enough to
    identify the intent without being too strict about exact wording).
    """
    try:
        from .history import recent
        rows = recent(50)
    except Exception:
        return False

    prefix = transcript[:25].lower().strip()
    if not prefix:
        return False

    count = sum(
        1 for _, hist_transcript, *_ in rows
        if hist_transcript and prefix in hist_transcript.lower()
    )
    return count >= 3


# ---------------------------------------------------------------------------
# Quick smoke test: python aliases.py
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    import tempfile
    import os

    print("=== aliases.py smoke test ===\n")
    all_pass = True

    # Redirect to a temp file so tests don't touch real aliases
    orig_path = ALIASES_PATH
    import voxterm.aliases as _self
    tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
    tmp.close()
    _self.ALIASES_PATH = Path(tmp.name)
    # Start fresh
    Path(tmp.name).write_text("{}", encoding="utf-8")

    def check(desc, condition):
        global all_pass
        status = "PASS" if condition else "FAIL"
        if not condition:
            all_pass = False
        print(f"  [{status}] {desc}")

    # load empty
    check("load() returns {} when file is empty", load() == {})

    # save + load roundtrip
    save("clean", "rm -rf node_modules && npm install")
    save("deploy", "npm run build && netlify deploy --prod")
    aliases = load()
    check("save() + load() roundtrip", len(aliases) == 2)
    check("saved command is correct", aliases["clean"] == "rm -rf node_modules && npm install")

    # case normalisation on save
    save("PUSH", "git push origin main")
    check("alias name lowercased on save", "push" in load())

    # match — hit
    cmd = match("run the clean script please")
    check("match() finds alias in transcript", cmd == "rm -rf node_modules && npm install")

    # match — miss
    cmd = match("show me the git log")
    check("match() returns None when no alias matches", cmd is None)

    # match — no partial word match (alias 'push' should not match 'pushover')
    cmd = match("pushover notification test")
    check("match() does not partial-match mid-word", cmd is None)

    # delete — existing
    result = delete("push")
    check("delete() returns True for existing alias", result is True)
    check("alias is gone after delete()", "push" not in load())

    # delete — missing
    result = delete("nonexistent")
    check("delete() returns False for missing alias", result is False)

    # check_for_repeat — needs history module; just verify it doesn't crash
    try:
        result = check_for_repeat("list my files")
        check("check_for_repeat() runs without error", isinstance(result, bool))
    except Exception as e:
        check(f"check_for_repeat() did not crash ({e})", False)

    # cleanup
    _self.ALIASES_PATH = orig_path
    os.unlink(tmp.name)

    print()
    if all_pass:
        print("All aliases tests: PASS")
    else:
        print("Some tests FAILED")
        sys.exit(1)
