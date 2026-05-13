---
version: "1.0"
generated: "2026-05-12"
---

# audio_feedback.py — Beep Tones (Appendix)

## What This Module Does

`audio_feedback.py` provides a single function, `beep()`, that plays a short sine-wave tone through the system audio output. It is used by `voice_input_node.py` to give audible feedback at three moments: wake-word detection (high, short), command confirmed (mid, short), and command rejected (low, longer).

## Implementation

```python
def beep(frequency: int = 880, duration: float = 0.15, device_index: int = 0) -> None:
    alsa_device = os.environ.get("SPEECH_ALSA_DEVICE", "")
    sample_rate = 16000
    n = int(sample_rate * duration)
    samples = bytearray(n * 2)
    amplitude = 0.2
    for i in range(n):
        s = int(math.sin(2 * math.pi * frequency * i / sample_rate) * 32767 * amplitude)
        struct.pack_into("<h", samples, i * 2, max(-32768, min(32767, s)))

    cmd = ["aplay", "-q", "-f", "S16_LE", "-r", str(sample_rate), "-c", "1"]
    if alsa_device:
        cmd.extend(["-D", alsa_device])
    subprocess.run(cmd, input=bytes(samples), check=False, capture_output=True)
```

It generates raw PCM in memory (signed 16-bit LE, mono, 16 kHz), then pipes it directly to `aplay`. No temp file, no external dependency beyond `aplay` being on the system.

`SPEECH_ALSA_DEVICE` selects the output device — same env var pattern as the rest of the pipeline. If unset, `aplay` uses its default output.

`check=False` and `capture_output=True` on the subprocess call mean a missing or broken `aplay` silently fails — the pipeline continues without audio feedback rather than crashing.

## Observations

- **Per-sample Python loop** — the sine wave is computed sample-by-sample in a Python for-loop. For 0.15 s at 16 kHz that is 2400 iterations — negligible latency, but `numpy` vectorization or `array.array` with a list comprehension would be idiomatic.

- **`device_index` parameter is unused** — the signature accepts `device_index` but uses `SPEECH_ALSA_DEVICE` (a string) instead. The parameter is vestigial; removing it or wiring it to an ALSA device index would be cleaner.
