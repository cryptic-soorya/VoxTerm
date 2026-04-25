#!/bin/zsh
# voxterm.sh — shell wrapper that enables directory-change support.
#
# cd is a shell built-in: running `cd` inside a subprocess can't affect your
# terminal's working directory. This wrapper reads the signal file that
# executor.py writes and performs the cd in your actual shell session.
#
# SETUP — add ONE of these lines to your ~/.zshrc, then restart your terminal:
#
#   source /Users/soorya/terminaltalker/voxterm.sh
#
# After sourcing, use `vt` or `voxterm` instead of `python main.py`.

_VOXTERM_DIR="$(cd "$(dirname "${(%):-%x}")" && pwd)"
# Must match executor.py: use $TMPDIR (user-private) not /tmp (world-writable).
# Python's executor.py falls back to /tmp when TMPDIR is unset; mirror that here
# so a launchd-style empty TMPDIR doesn't break the cd handoff.
_VOXTERM_CD_FILE="${${TMPDIR:-/tmp}%/}/.voxterm_cd"

voxterm() {
    # Use $VOXTERM_PYTHON if set (the menu bar app exports it when it spawns a
    # linked terminal so we run inside its venv with all deps available).
    local _vt_py="${VOXTERM_PYTHON:-python}"
    VOXTERM_SHELL_WRAPPER=1 "$_vt_py" "$_VOXTERM_DIR/main.py" "$@"
    if [[ -f "$_VOXTERM_CD_FILE" ]]; then
        local _target
        _target="$(<"$_VOXTERM_CD_FILE")"
        rm -f "$_VOXTERM_CD_FILE"
        # Validate: must be an absolute path to an existing directory.
        # Rejects any crafted content that contains shell metacharacters or
        # relative path components.
        if [[ "$_target" == /* && -d "$_target" && "$_target" != *..* ]]; then
            cd "$_target"
        fi
    fi
}

# Short alias
vt() { voxterm "$@"; }
