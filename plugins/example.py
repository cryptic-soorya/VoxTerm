"""
Example plugin for vocterm.

Plugins are checked before calling any LLM — zero latency, zero API usage.
Copy this file, rename it, and edit TRIGGER + run() to create your own.

The plugin matches if TRIGGER appears anywhere in the transcript (case-insensitive).
"""

TRIGGER = "deploy"
DESCRIPTION = "Run the project deploy pipeline"


def run(context: dict) -> str:
    """
    Return the shell command string to execute.

    Args:
        context: dict with keys: cwd, user, shell, os, time
                 Use context["cwd"] to make paths precise.

    Returns:
        A shell command string. vocterm will run this through the normal
        safety gate (medium risk by default for plugin commands).
    """
    return "npm run build && netlify deploy --prod"
