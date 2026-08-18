"""Tests for the in-memory undo stack in voxterm.undo."""

import pytest

from voxterm import undo


@pytest.fixture(autouse=True)
def clean_stack():
    undo.clear()
    yield
    undo.clear()


def test_empty_stack_state():
    assert not undo.can_undo()
    assert undo.pop() is None
    assert undo.peek() is None
    assert undo.depth() == 0


def test_push_and_pop_reversible_command():
    undo.push("mv new_name.txt old_name.txt")
    assert undo.can_undo()
    assert undo.peek() == "mv new_name.txt old_name.txt"
    assert undo.depth() == 1

    assert undo.pop() == "mv new_name.txt old_name.txt"
    assert not undo.can_undo()
    assert undo.depth() == 0


def test_irreversible_command_disables_undo_without_losing_history():
    undo.push("mv a.txt b.txt")
    undo.push(None)  # e.g. after `rm`

    assert not undo.can_undo()
    assert undo.depth() == 2

    undo.pop()  # remove the None marker
    assert undo.can_undo()
    assert undo.peek() == "mv a.txt b.txt"


def test_clear_empties_the_stack():
    undo.push("echo restore")
    undo.clear()
    assert undo.depth() == 0
    assert not undo.can_undo()
