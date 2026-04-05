"""
audio.py — microphone capture with WebRTC VAD silence detection

Records from the default mic at 16kHz mono 16-bit PCM (Whisper's native format).
Uses WebRTCVAD to detect when you stop talking, then returns a temp .wav path.

Key design choices:
- Pre-speech ring buffer: captures ~0.5s before speech starts so we never
  miss the first syllable of an utterance.
- 1.5 second silence threshold: long enough to handle natural pauses in speech,
  short enough to feel responsive.
- Max duration cap: prevents infinite recording if VAD misses silence.
- exception_on_overflow=False: drops frames rather than crashing on buffer
  overrun (can happen when the system is briefly busy).
"""

import pyaudio
import webrtcvad
import wave
import tempfile
import os
import collections
import sys

SAMPLE_RATE = 16_000          # Hz — Whisper was trained on 16kHz
FRAME_DURATION_MS = 30        # ms per VAD frame (10, 20, or 30 are valid)
CHUNK = int(SAMPLE_RATE * FRAME_DURATION_MS / 1000)  # 480 samples per frame

SILENCE_THRESHOLD_SECONDS = 1.5
SILENCE_FRAMES_NEEDED = int(SILENCE_THRESHOLD_SECONDS * 1000 / FRAME_DURATION_MS)  # 50

# Ring buffer to keep ~0.5s of audio before speech starts, so we don't
# clip the beginning of what you said.
PRE_SPEECH_BUFFER_SECONDS = 0.5
PRE_SPEECH_FRAMES = int(PRE_SPEECH_BUFFER_SECONDS * 1000 / FRAME_DURATION_MS)  # 16

MAX_RECORDING_SECONDS = 30    # safety cap — stops after 30s regardless
MAX_FRAMES = int(MAX_RECORDING_SECONDS * 1000 / FRAME_DURATION_MS)


def record_until_silence(status_callback=None) -> str:
    """
    Open the default microphone, wait for speech, record until silence.

    Args:
        status_callback: optional callable(str) for status messages.
                         Defaults to printing to stdout.

    Returns:
        Path to a temporary .wav file. Caller is responsible for deleting it
        if transcribe.py doesn't (it does, but just in case).

    Raises:
        RuntimeError: if PyAudio can't open the microphone.
        RuntimeError: if no speech is detected within MAX_RECORDING_SECONDS.
    """
    def _status(msg: str):
        if status_callback:
            status_callback(msg)
        else:
            print(msg, flush=True)

    vad = webrtcvad.Vad(3)  # aggressiveness 0–3; 3 = most aggressive (classifies more as silence)

    pa = pyaudio.PyAudio()
    try:
        stream = pa.open(
            rate=SAMPLE_RATE,
            channels=1,
            format=pyaudio.paInt16,
            input=True,
            frames_per_buffer=CHUNK,
        )
    except OSError as exc:
        pa.terminate()
        raise RuntimeError(
            f"Could not open microphone: {exc}\n"
            "Check that a microphone is connected and that this app has mic permissions."
        ) from exc

    _status("listening...")

    # Ring buffer holds pre-speech audio so we capture the utterance start.
    pre_buffer: collections.deque[bytes] = collections.deque(maxlen=PRE_SPEECH_FRAMES)
    frames: list[bytes] = []
    silent_frame_count = 0
    speech_detected = False
    total_frames = 0

    try:
        while True:
            raw_frame = stream.read(CHUNK, exception_on_overflow=False)
            total_frames += 1

            try:
                is_speech = vad.is_speech(raw_frame, SAMPLE_RATE)
            except Exception:
                # VAD can fail on rare malformed frames — treat as silence.
                is_speech = False

            if not speech_detected:
                if is_speech:
                    # Speech just started — flush the pre-buffer first
                    speech_detected = True
                    silent_frame_count = 0
                    frames.extend(pre_buffer)
                    frames.append(raw_frame)
                else:
                    pre_buffer.append(raw_frame)
                    # Enforce max duration even before speech (e.g. always-noisy env)
                    if total_frames >= MAX_FRAMES:
                        raise RuntimeError(
                            f"No speech detected in {MAX_RECORDING_SECONDS}s. "
                            "Is your microphone working?"
                        )
            else:
                frames.append(raw_frame)
                if is_speech:
                    silent_frame_count = 0
                else:
                    silent_frame_count += 1
                    if silent_frame_count >= SILENCE_FRAMES_NEEDED:
                        break  # clean end-of-utterance silence detected

                if total_frames >= MAX_FRAMES:
                    # Hit the cap mid-speech — still process what we have.
                    _status("max recording length reached")
                    break
    finally:
        stream.stop_stream()
        stream.close()
        pa.terminate()

    if not frames:
        raise RuntimeError("Recorded zero frames — nothing to transcribe.")

    # Write to a temp .wav file that faster-whisper can read.
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp_path = tmp.name
    tmp.close()

    with wave.open(tmp_path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)          # 16-bit = 2 bytes per sample
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(b"".join(frames))

    return tmp_path


def list_input_devices() -> list[dict]:
    """
    Return available audio input devices. Useful for debugging mic issues.
    Not called in normal operation.
    """
    pa = pyaudio.PyAudio()
    devices = []
    try:
        for i in range(pa.get_device_count()):
            info = pa.get_device_info_by_index(i)
            if info.get("maxInputChannels", 0) > 0:
                devices.append({
                    "index": i,
                    "name": info["name"],
                    "sample_rate": int(info["defaultSampleRate"]),
                })
    finally:
        pa.terminate()
    return devices


# ---------------------------------------------------------------------------
# Quick smoke test: python audio.py
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=== audio.py smoke test ===")
    print("Available input devices:")
    for d in list_input_devices():
        print(f"  [{d['index']}] {d['name']}  ({d['sample_rate']} Hz)")

    print()
    try:
        path = record_until_silence()
        size_kb = os.path.getsize(path) / 1024
        print(f"\nRecorded to: {path}  ({size_kb:.1f} KB)")
        print("Cleaning up temp file...")
        os.unlink(path)
        print("Done. Phase 1 audio capture working correctly.")
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
