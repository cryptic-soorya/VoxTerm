"""
context.py — system context injected into every LLM call

Without this, "delete the build folder" might generate `rm -rf /build`
instead of `rm -rf /Users/soorya/projects/myapp/build`.
Prepending CWD + shell + OS makes every command precise.
"""

import os
import platform
import datetime


def get_context() -> str:
    """
    Return a compact multi-line context string for the LLM prompt.

    Example output:
        CWD: /Users/soorya/projects/myapp
        USER: soorya
        SHELL: /bin/zsh
        OS: macOS 15.4.0 (Apple Silicon)
        TIME: 2026-04-04 14:32
    """
    mac_ver = platform.mac_ver()[0] or platform.version()
    return (
        f"CWD: {os.getcwd()}\n"
        f"USER: {os.getenv('USER', 'unknown')}\n"
        f"SHELL: {os.getenv('SHELL', '/bin/zsh')}\n"
        f"OS: macOS {mac_ver} (Apple Silicon)\n"
        f"TIME: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )


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
