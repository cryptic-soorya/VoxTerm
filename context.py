"""
context.py — system context injected into every LLM call

Without this, "delete the build folder" might generate `rm -rf /build`
instead of `rm -rf /Users/soorya/projects/myapp/build`.
Prepending CWD + shell + OS makes every command precise.
"""

import os
import platform
import datetime


def get_filesystem_context(max_items: int = 20) -> str:
    """
    Return a compact listing of the current directory so the LLM knows what's
    actually here before generating commands.

    Skips hidden files (dotfiles) to reduce noise. Shows size in MB only for
    files larger than 1 MB. Caps at max_items entries.
    """
    try:
        items = []
        for entry in sorted(os.scandir("."), key=lambda e: e.name):
            # Skip hidden files but keep hidden directories (e.g. .venv, .git) —
            # they're important for the LLM to know about when generating commands.
            if entry.name.startswith(".") and not entry.is_dir():
                continue
            if entry.is_dir():
                items.append(f"  {entry.name}/")
            else:
                size = entry.stat().st_size
                if size > 1_000_000:
                    items.append(f"  {entry.name} ({size / 1_000_000:.1f} MB)")
                else:
                    items.append(f"  {entry.name}")
            if len(items) >= max_items:
                items.append("  ... and more")
                break
        if not items:
            return "Current directory contents: (empty)"
        return "Current directory contents:\n" + "\n".join(items)
    except PermissionError:
        return "Current directory contents: (permission denied)"


def get_context() -> str:
    """
    Return a compact multi-line context string for the LLM prompt.

    Example output:
        CWD: /Users/soorya/projects/myapp
        USER: soorya
        SHELL: /bin/zsh
        OS: macOS 15.4.0 (Apple Silicon)
        TIME: 2026-04-04 14:32

        Current directory contents:
          dist/
          node_modules/
          package.json
          README.md (2.1 MB)
    """
    mac_ver = platform.mac_ver()[0] or platform.version()
    base = (
        f"CWD: {os.getcwd()}\n"
        f"USER: {os.getenv('USER', 'unknown')}\n"
        f"SHELL: {os.getenv('SHELL', '/bin/zsh')}\n"
        f"OS: macOS {mac_ver} (Apple Silicon)\n"
        f"TIME: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )
    return f"{base}\n\n{get_filesystem_context()}"


def get_context_dict() -> dict:
    """
    Same info as get_context() but as a dict — used by the plugin system.
    """
    mac_ver = platform.mac_ver()[0] or platform.version()
    return {
        "cwd": os.getcwd(),
        "user": os.getenv("USER", "unknown"),
        "shell": os.getenv("SHELL", "/bin/zsh"),
        "os": f"macOS {mac_ver} (Apple Silicon)",
        "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


# ---------------------------------------------------------------------------
# Quick smoke test: python context.py
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print(get_context())
