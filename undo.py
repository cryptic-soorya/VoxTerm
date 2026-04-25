"""
undo.py — in-memory undo stack

Stores inverse commands after each successful execution.
Intentionally in-memory only — resets when VoxTerm exits.
Persisting undo to disk would allow stale destructive inverses
to be replayed much later, which is unsafe.

Usage:
    push(result.get("inverse_command"))   # after a successful run
    if can_undo():
        cmd = pop()                       # get + remove top of stack
"""

_stack: list[str | None] = []


def push(inverse_command: str | None):
    """
    Push an inverse command onto the stack after a successful run.
    Pass None for irreversible commands (rm, etc.) — undo will be
    disabled for those entries.
    """
    _stack.append(inverse_command)


def pop() -> str | None:
    """
    Remove and return the top inverse command.
    Returns None if the stack is empty.
    """
    return _stack.pop() if _stack else None


def can_undo() -> bool:
    """
    True only if there's an entry on the stack AND it's actually reversible.
    An entry of None means the last command was irreversible.
    """
    return bool(_stack) and _stack[-1] is not None


def peek() -> str | None:
    """See the top entry without removing it."""
    return _stack[-1] if _stack else None


def clear():
    """Empty the stack. Used in tests."""
    _stack.clear()


def depth() -> int:
    """Number of entries on the stack (includes None entries)."""
    return len(_stack)


# ---------------------------------------------------------------------------
# Quick smoke test: python undo.py
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    print("=== undo.py smoke test ===\n")
    all_pass = True

    def check(desc, condition):
        global all_pass
        status = "PASS" if condition else "FAIL"
        if not condition:
            all_pass = False
        print(f"  [{status}] {desc}")

    # Empty stack
    check("can_undo() False on empty stack", not can_undo())
    check("pop() returns None on empty stack", pop() is None)
    check("peek() returns None on empty stack", peek() is None)
    check("depth() is 0", depth() == 0)

    # Push a reversible command
    push("mv new_name.txt old_name.txt")
    check("can_undo() True after reversible push", can_undo())
    check("peek() shows command without removing", peek() == "mv new_name.txt old_name.txt")
    check("depth() is 1", depth() == 1)

    # Pop it
    cmd = pop()
    check("pop() returns the inverse command", cmd == "mv new_name.txt old_name.txt")
    check("can_undo() False after pop", not can_undo())
    check("depth() is 0 after pop", depth() == 0)

    # Push an irreversible command (None)
    push("mv a.txt b.txt")   # reversible
    push(None)               # irreversible (e.g. rm)
    check("can_undo() False when top is None", not can_undo())
    check("depth() is 2 (both entries present)", depth() == 2)

    # Pop the None, then the reversible one is accessible
    pop()  # removes the None
    check("can_undo() True after popping the None entry", can_undo())

    # clear()
    clear()
    check("clear() empties the stack", depth() == 0 and not can_undo())

    print()
    if all_pass:
        print("All undo tests: PASS")
    else:
        print("Some tests FAILED")
        sys.exit(1)
