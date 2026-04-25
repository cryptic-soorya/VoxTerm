"""
transcribe.py — local speech-to-text via faster-whisper

Uses the CTranslate2-backed faster-whisper library, which runs the same
Whisper model weights as OpenAI's original but 2–4× faster on CPU.
On Apple Silicon (M1/M2/M3/M4) the base model transcribes a 5-second
clip in roughly 0.3–0.5 seconds.

The model is loaded once at import time. This takes ~1 second the first
run (it downloads the weights if missing), but each subsequent call is
fast because the model stays in memory.

Model size trade-offs:
  tiny  : ~39M params, ~0.1s/clip, lower accuracy
  base  : ~74M params, ~0.4s/clip, good accuracy for clear speech    ← default
  small : ~244M params, ~1.5s/clip, better with accents/noise
  medium: ~769M params, ~5s/clip,  near-human for most inputs

Set WHISPER_MODEL env var to override (see .env.example).
"""

import os
import sys
from faster_whisper import WhisperModel

WHISPER_MODEL_SIZE: str = os.getenv("WHISPER_MODEL", "base")

# Vocabulary hint fed to Whisper as an initial_prompt.
# Whisper biases transcription toward words it sees here, which dramatically
# reduces mishearing of developer/terminal vocabulary.
DEVELOPER_VOCAB_PROMPT = (
    "git commit push pull merge branch checkout rebase stash "
    "npm install run build start test node python pip brew "
    "mkdir rmdir chmod chown sudo grep find cat ls pwd cd mv cp rm "
    "ssh curl wget docker compose kubectl terraform ansible "
    "homebrew virtualenv conda jupyter pandas numpy "
    "localhost port server database postgres mongo redis "
    "API JSON config environment variable export source "
    "zsh bash shell terminal command flag argument stdin stdout stderr "
    "VoxTerm voxterm"
)

# compute_type="int8" uses 8-bit integer weights — 2× faster, ~half the RAM,
# negligible quality difference for short voice commands.
# device="cpu" is correct for Apple Silicon until CTranslate2 adds Metal support.
try:
    _model = WhisperModel(WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")
except Exception as exc:
    # Deferred error: let the import succeed so other modules can load,
    # but raise clearly on first use.
    _model = None
    _model_load_error = exc
else:
    _model_load_error = None


def transcribe(wav_path: str) -> str:
    """
    Transcribe a .wav file to text using the locally loaded Whisper model.

    Args:
        wav_path: absolute or relative path to a 16kHz mono PCM .wav file.
                  The file is deleted after transcription succeeds.

    Returns:
        Transcribed text, stripped of leading/trailing whitespace.
        Returns an empty string if the audio contained only silence/noise.

    Raises:
        RuntimeError: if the model failed to load at import time.
        FileNotFoundError: if wav_path does not exist.
    """
    if _model is None:
        raise RuntimeError(
            f"faster-whisper model failed to load: {_model_load_error}\n"
            "Run: pip install faster-whisper"
        ) from _model_load_error

    if not os.path.exists(wav_path):
        raise FileNotFoundError(f"WAV file not found: {wav_path}")

    try:
        # beam_size=5 gives the best accuracy/speed balance.
        # language="en" skips language detection (saves ~0.1s, fine for English).
        # vad_filter=True uses Silero VAD inside Whisper to skip silent segments
        #   — important for recordings that start/end with silence padding.
        # condition_on_previous_text=False prevents compounding errors across
        #   segments when multiple segments are returned.
        segments, _info = _model.transcribe(
            wav_path,
            beam_size=5,
            language="en",
            vad_filter=True,
            condition_on_previous_text=False,
            initial_prompt=DEVELOPER_VOCAB_PROMPT,
        )

        # segments is a lazy generator — consume it fully.
        parts = [segment.text.strip() for segment in segments]
        text = " ".join(p for p in parts if p)

        return text.strip()

    finally:
        # Always clean up the temp file, even if transcription raised.
        try:
            os.unlink(wav_path)
        except OSError:
            pass


def transcribe_and_keep(wav_path: str) -> str:
    """
    Same as transcribe() but does NOT delete the .wav file afterwards.
    Useful during debugging when you want to replay the audio.
    """
    if _model is None:
        raise RuntimeError(
            f"faster-whisper model failed to load: {_model_load_error}"
        ) from _model_load_error

    if not os.path.exists(wav_path):
        raise FileNotFoundError(f"WAV file not found: {wav_path}")

    segments, _info = _model.transcribe(
        wav_path,
        beam_size=5,
        language="en",
        vad_filter=True,
        condition_on_previous_text=False,
        initial_prompt=DEVELOPER_VOCAB_PROMPT,
    )
    parts = [segment.text.strip() for segment in segments]
    return " ".join(p for p in parts if p).strip()


def get_model_info() -> dict:
    """Return metadata about the loaded model. Useful for --version output."""
    return {
        "model_size": WHISPER_MODEL_SIZE,
        "device": "cpu",
        "compute_type": "int8",
        "loaded": _model is not None,
    }


# ---------------------------------------------------------------------------
# Quick smoke test: python transcribe.py path/to/file.wav
# Or: python transcribe.py   (records from mic first if audio.py is present)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) == 2:
        wav = sys.argv[1]
        print(f"Transcribing: {wav}")
        result = transcribe_and_keep(wav)
        print(f"Transcript: {result!r}")
    else:
        print("=== transcribe.py smoke test ===")
        print(f"Model: {WHISPER_MODEL_SIZE}  (set WHISPER_MODEL env var to change)")
        print()
        # Try to record from mic if audio.py is available
        try:
            from audio import record_until_silence
            print("Recording from mic (speak now)...")
            wav_path = record_until_silence()
            print("Transcribing...")
            text = transcribe(wav_path)  # deletes the wav
            if text:
                print(f"\nTranscript: {text!r}")
            else:
                print("\nNo speech detected in audio.")
        except ImportError:
            print("audio.py not found. Pass a .wav path as argument:")
            print("  python transcribe.py recording.wav")
            sys.exit(1)
        except RuntimeError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
