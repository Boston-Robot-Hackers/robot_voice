#!/usr/bin/env python3
"""
audio_feedback.py — simple audio feedback tones for voice state transitions.

Author: Pito Salas and Claude Code
Open Source Under MIT license
"""

import math
import os
import struct
import subprocess


def beep(frequency: int = 880, duration: float = 0.15, device_index: int = 0, volume: float = 1.0) -> None:
    """Play a short sine-wave tone via aplay on the configured ALSA output device."""
    alsa_device = os.environ.get("SPEECH_ALSA_DEVICE", "")
    sample_rate = 16000
    n = int(sample_rate * duration)
    amplitude = 0.07 * max(0.0, min(1.0, volume))
    buf = bytearray(n * 4)  # stereo: 2 channels * 2 bytes
    for i in range(n):
        t = i / sample_rate
        # fundamental decays slowly, inharmonic partial decays fast — bell character
        fund = math.sin(2 * math.pi * frequency * t) * math.exp(-4.0 * t)
        partial = math.sin(2 * math.pi * frequency * 2.76 * t) * math.exp(-12.0 * t) * 0.4
        s = int((fund + partial) * 32767 * amplitude)
        s = max(-32768, min(32767, s))
        struct.pack_into("<hh", buf, i * 4, s, s)  # L + R

    cmd = ["aplay", "-q", "-f", "S16_LE", "-r", str(sample_rate), "-c", "2"]
    if alsa_device:
        cmd.extend(["-D", alsa_device])
    try:
        subprocess.run(cmd, input=bytes(buf), check=False, capture_output=True)
    except Exception as exc:
        import sys
        print(f"beep: aplay failed: {exc}", file=sys.stderr)
