# voxterm.spec — PyInstaller configuration for VoxTerm.app
#
# Usage:
#   pyinstaller voxterm.spec
#
# Output: dist/VoxTerm.app
#
# This spec bundles app_gui.py (the rumps menu bar entry point) along with
# all backend modules, data files, and macOS-specific plist keys needed for
# mic access, menu-bar-only mode, and optional Accessibility (global hotkey).

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH)   # directory containing this .spec file

# Collect all numpy and ctranslate2 files — PyInstaller misses C-extensions
# in numpy 2.x and ctranslate2 without this.
numpy_datas, numpy_binaries, numpy_hiddenimports = collect_all('numpy')
ct2_datas, ct2_binaries, ct2_hiddenimports = collect_all('ctranslate2')
# faster_whisper ships silero_vad_v6.onnx in its assets/ dir — must be collected
# explicitly or the bundled app throws ONNXRuntimeError: NO_SUCH_FILE at startup.
fw_datas, fw_binaries, fw_hiddenimports = collect_all('faster_whisper')

# ---------------------------------------------------------------------------
# Version — bump this before each release
# ---------------------------------------------------------------------------
VERSION = "1.0.0"
BUNDLE_ID = "com.voxterm.app"

# ---------------------------------------------------------------------------
# Analysis — collect all source files and data
# ---------------------------------------------------------------------------
a = Analysis(
    scripts=[str(ROOT / "app_gui.py")],

    # Add any extra source search paths here if needed.
    pathex=[str(ROOT)],

    binaries=[] + numpy_binaries + ct2_binaries + fw_binaries,

    # Non-Python files that must be present inside the .app bundle.
    # Each tuple is (source_path_or_glob, destination_folder_inside_bundle).
    datas=[
        # LLM system prompt — editable without recompiling.
        # Destination mirrors the package layout because translate.py resolves
        # these via Path(__file__).parent, i.e. <bundle>/voxterm/prompts.
        (str(ROOT / "voxterm" / "prompts" / "system.txt"), "voxterm/prompts"),

        # Plugin directory (Python files loaded at runtime via importlib)
        (str(ROOT / "voxterm" / "plugins"),   "voxterm/plugins"),

        # App icon (used by the macOS Dock / Finder if LSUIElement is removed)
        (str(ROOT / "assets" / "icon.icns"),  "assets"),
    ] + numpy_datas + ct2_datas + fw_datas,

    # Modules that PyInstaller's static analyser misses (dynamic imports,
    # optional backends, rumps internals, etc.).
    hiddenimports=[
        # faster-whisper / CTranslate2 backends
        "ctranslate2",
        "ctranslate2.specs",
        "faster_whisper",
    ] + numpy_hiddenimports + ct2_hiddenimports + fw_hiddenimports + [

        # google-genai (new SDK, replaces deprecated google-generativeai)
        "google.genai",
        "google.genai.types",
        "google.genai.client",

        # pynput platform backend picked at runtime
        "pynput.keyboard._darwin",
        "pynput.mouse._darwin",

        # rumps internals
        "rumps",

        # Standard-library modules referenced dynamically in plugins
        "importlib.util",
        "sqlite3",

        # dotenv
        "dotenv",

        # voxterm.main is only imported conditionally (--cli dispatch in
        # app_gui.py), which PyInstaller's static analysis can miss.
        "click",
        "voxterm.main",
    ],

    hookspath=["hooks"],   # custom hooks override contrib (e.g. webrtcvad-wheels fix)
    hooksconfig={},
    runtime_hooks=[],

    # Packages to exclude to keep the bundle lean.
    excludes=[
        "tkinter",
        "matplotlib",
        "PIL",
        "IPython",
        "jupyter",
    ],

    noarchive=False,
    optimize=0,
)

# ---------------------------------------------------------------------------
# PYZ — compressed Python bytecode archive
# ---------------------------------------------------------------------------
pyz = PYZ(a.pure)

# ---------------------------------------------------------------------------
# EXE — the raw UNIX executable (embedded inside the .app)
# ---------------------------------------------------------------------------
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,  # binaries handled by COLLECT below
    name="voxterm",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # no Terminal window — menu bar app
    disable_windowed_traceback=False,
    argv_emulation=False,   # rumps handles the macOS event loop itself
    target_arch=None,       # None → match the current machine's arch (arm64 on M-series)
    codesign_identity=None, # set to your Apple Developer identity to sign
    entitlements_file=None,
    icon=str(ROOT / "assets" / "icon.icns"),
)

# ---------------------------------------------------------------------------
# COLLECT — gather all binaries, data files, and dylibs into one folder
# ---------------------------------------------------------------------------
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="voxterm",
)

# ---------------------------------------------------------------------------
# BUNDLE — wrap everything into VoxTerm.app
# ---------------------------------------------------------------------------
app = BUNDLE(
    coll,
    name="VoxTerm.app",
    icon=str(ROOT / "assets" / "icon.icns"),
    bundle_identifier=BUNDLE_ID,
    version=VERSION,
    info_plist={
        # ── Appearance ────────────────────────────────────────────────────
        "CFBundleName":               "VoxTerm",
        "CFBundleDisplayName":        "VoxTerm",
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion":            VERSION,
        "CFBundleIdentifier":         BUNDLE_ID,

        # ── Menu bar app — no Dock icon ───────────────────────────────────
        # LSUIElement = True hides the app from the Dock and the ⌘-Tab
        # switcher; the only UI surface is the menu bar icon.
        "LSUIElement": True,

        # ── Minimum macOS — Apple Silicon ships 11+ ───────────────────────
        "LSMinimumSystemVersion": "11.0",

        # ── Privacy usage descriptions (required since macOS 10.14) ───────
        # The system will refuse mic access and show a crash if this key is
        # absent when the app first tries to open the audio input stream.
        "NSMicrophoneUsageDescription": (
            "VoxTerm records your voice locally to transcribe commands. "
            "No audio is ever sent to the internet."
        ),

        # Required for pynput global hotkey via the Accessibility API.
        "NSAppleEventsUsageDescription": (
            "VoxTerm uses Accessibility to detect the global hotkey "
            "(⌘⇧Space) so you can trigger it from any app."
        ),

        # macOS 14+ (Sonoma) requires this key for input monitoring permission.
        # Without it, the OS silently denies pynput's CGEventTap request and
        # the global hotkey never fires.
        "NSInputMonitoringUsageDescription": (
            "VoxTerm monitors the ⌘⇧Space hotkey so you can trigger a "
            "voice command from any app without switching windows."
        ),

        # ── Supported document types (none) ──────────────────────────────
        "CFBundleDocumentTypes": [],

        # ── High-DPI / Retina support ─────────────────────────────────────
        "NSHighResolutionCapable": True,
    },
)
