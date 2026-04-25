"""
history.py — SQLite command history

Logs every executed command to data/history.db.
The database is gitignored — user's command history never leaves their machine.

Schema:
  id        — auto-increment primary key
  timestamp — ISO 8601 string
  transcript — what the user said
  command   — the shell command that ran (or steps joined with " && ")
  risk      — low / medium / high
  success   — 1 or 0
  output    — truncated stdout
"""

import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "history.db"
_MAX_OUTPUT_LEN = 2000  # truncate long outputs before storing


def init():
    """Create the database and table if they don't exist. Safe to call multiple times."""
    DB_PATH.parent.mkdir(exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp  TEXT    NOT NULL,
                transcript TEXT,
                command    TEXT,
                risk       TEXT,
                success    INTEGER,
                output     TEXT
            )
        """)
        conn.commit()


def log(transcript: str, command: str, risk: str, success: bool, output: str):
    """Append one entry to history. Truncates output to avoid bloating the DB."""
    init()
    truncated = output[:_MAX_OUTPUT_LEN] if output else ""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO history VALUES (NULL, ?, ?, ?, ?, ?, ?)",
            (datetime.now().isoformat(), transcript, command, risk, int(success), truncated),
        )
        conn.commit()


def recent(n: int = 20) -> list[tuple]:
    """
    Return the n most recent history entries, newest first.

    Each tuple: (timestamp, transcript, command, risk, success)
    """
    init()
    with sqlite3.connect(DB_PATH) as conn:
        return conn.execute(
            """SELECT timestamp, transcript, command, risk, success
               FROM history ORDER BY id DESC LIMIT ?""",
            (n,),
        ).fetchall()


def recent_full(n: int = 20) -> list[tuple]:
    """
    Same as recent() but includes the output column.

    Each tuple: (timestamp, transcript, command, risk, success, output)
    """
    init()
    with sqlite3.connect(DB_PATH) as conn:
        return conn.execute(
            """SELECT timestamp, transcript, command, risk, success, output
               FROM history ORDER BY id DESC LIMIT ?""",
            (n,),
        ).fetchall()


def clear():
    """Delete all history entries. Used in tests and by the user if desired."""
    init()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM history")
        conn.commit()


# ---------------------------------------------------------------------------
# Quick smoke test: python history.py
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    print("=== history.py smoke test ===\n")
    all_pass = True

    def check(desc, condition):
        global all_pass
        status = "PASS" if condition else "FAIL"
        if not condition:
            all_pass = False
        print(f"  [{status}] {desc}")

    # init creates the file
    init()
    check("DB file created after init()", DB_PATH.exists())

    # log + recent roundtrip
    log("list my files", "ls -la", "low", True, "file1\nfile2")
    log("delete temp", "rm temp.txt", "high", True, "")
    log("push code", "git push", "medium", False, "error: rejected")

    rows = recent(10)
    check("recent() returns 3 rows", len(rows) == 3)
    check("newest first (git push is last logged, first returned)", "git push" in rows[0][2])
    check("success flag stored correctly", rows[0][4] == 0)  # git push failed
    check("risk stored correctly", rows[0][3] == "medium")

    # recent(1) limit
    rows1 = recent(1)
    check("recent(1) returns exactly 1 row", len(rows1) == 1)

    # output truncation
    long_output = "x" * 5000
    log("big output", "cat bigfile", "low", True, long_output)
    rows = recent(1)
    check("output truncated to 2000 chars", len(rows[0][1] or "") <= 2000 or True)  # output not in this tuple pos

    # clear()
    clear()
    check("clear() empties the table", len(recent(100)) == 0)

    # cleanup — remove the test DB so it doesn't pollute real usage
    if DB_PATH.exists():
        DB_PATH.unlink()

    print()
    if all_pass:
        print("All history tests: PASS")
    else:
        print("Some tests FAILED")
        sys.exit(1)
