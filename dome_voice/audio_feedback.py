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


def beep(frequency: int = 880, duration: float = 0.15, device_index: int = 0) -> None:
    """Play a short sine-wave tone via aplay on the configured ALSA output device."""
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
    try:
        subprocess.run(cmd, input=bytes(samples), check=False, capture_output=True)
    except Exception as exc:
        import sys
        print(f"beep: aplay failed: {exc}", file=sys.stderr)
