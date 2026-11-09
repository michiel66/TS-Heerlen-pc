"""Original locally audible three-tone roger beep. No claim of TS3 audio injection."""
from __future__ import annotations

from io import BytesIO
import math
import struct
import threading
import wave


def generate_three_tone_wav(sample_rate: int = 24000) -> bytes:
    """Return a 16-bit mono WAV with three short smooth tones."""
    frequencies = (740.0, 980.0, 1240.0)
    length = 0.125
    samples = []
    per_tone = int(sample_rate * length)
    ramp = max(1, int(sample_rate * 0.012))
    for frequency in frequencies:
        for i in range(per_tone):
            envelope = min(1.0, i / ramp, (per_tone - 1 - i) / ramp)
            value = int(10500 * max(0.0, envelope) *
                        math.sin(2 * math.pi * frequency * i / sample_rate))
            samples.append(value)
    raw = struct.pack(f"<{len(samples)}h", *samples)
    memory = BytesIO()
    with wave.open(memory, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframes(raw)
    return memory.getvalue()


_ROGER_WAV = generate_three_tone_wav()


def play_roger_async() -> None:
    """Play on default Windows output asynchronously, without freezing the UI."""
    def _worker():
        try:
            import winsound
            winsound.PlaySound(_ROGER_WAV, winsound.SND_MEMORY)
        except (ImportError, RuntimeError, OSError):
            pass
    threading.Thread(target=_worker, name="HeerlenRogerPiep", daemon=True).start()
