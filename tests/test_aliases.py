"""Tests for voxterm.aliases: save/load/match/delete on-disk alias store.

Uses monkeypatch to redirect ALIASES_PATH to a tmp file so these never
touch the user's real ~/.voxterm/aliases.json.
"""

import pytest

from voxterm import aliases


@pytest.fixture(autouse=True)
def isolated_aliases_path(tmp_path, monkeypatch):
    monkeypatch.setattr(aliases, "ALIASES_PATH", tmp_path / "aliases.json")
    yield


def test_load_returns_empty_dict_when_no_file():
    assert aliases.load() == {}


def test_save_and_load_roundtrip():
    aliases.save("clean", "rm -rf node_modules && npm install")
    aliases.save("deploy", "npm run build && netlify deploy --prod")

    loaded = aliases.load()
    assert loaded["clean"] == "rm -rf node_modules && npm install"
    assert loaded["deploy"] == "npm run build && netlify deploy --prod"


def test_save_lowercases_and_strips_alias_name():
    aliases.save("  PUSH  ", "git push origin main")
    assert "push" in aliases.load()


def test_match_finds_alias_as_whole_word():
    aliases.save("clean", "rm -rf node_modules && npm install")
    assert aliases.match("run the clean script please") == "rm -rf node_modules && npm install"


def test_match_returns_none_when_no_alias_present():
    aliases.save("clean", "rm -rf node_modules && npm install")
    assert aliases.match("show me the git log") is None


def test_match_does_not_match_partial_word():
    aliases.save("push", "git push origin main")
    assert aliases.match("the pushover app notified me") is None


def test_delete_removes_existing_alias():
    aliases.save("clean", "rm -rf node_modules")
    assert aliases.delete("clean") is True
    assert "clean" not in aliases.load()


def test_delete_returns_false_for_missing_alias():
    assert aliases.delete("does-not-exist") is False
