# dome_voice — Spec

## Purpose

Standalone Python package providing a complete voice pipeline for robot control. No ROS imports. Designed to be consumed by a ROS2 adapter node (e.g. `dome_voice/voice_input_node.py`).

## Pipeline

```
mic (arecord) → stereo→mono → bandpass filter
    → wake word detection (openWakeWord)
    → STT (Vosk, grammar-constrained)
    → intent mapping (transcript → intent dict)
    → audio feedback (beep via aplay)
```

## Public API

```python
from dome_voice import (
    VoiceRuntime,        # main loop: next_turn() → VoiceTurn
    VoiceTurn,           # dataclass: text, raw_text, wake_score, empty, metadata
    VoiceRuntimeConfig,  # frozen dataclass of all tuned parameters
    load_voice_runtime_config,  # loads from TUNED_VOICE_PARAMETERS or YAML file
    IntentMapper,        # maps transcript text → intent dict
    beep,                # short audio tone via aplay
)
```

## Configuration

All tuned hardware parameters live in `dome_voice/runtime.py:TUNED_VOICE_PARAMETERS`. Override via:
- env var `CONTROL_VOICE_TUNE_CONFIG` or `VOICE_TUNE_CONFIG` pointing to a tune YAML
- `load_voice_runtime_config(path=...)` directly

## Dependencies

- `openwakeword` — wake word detection
- `vosk` — offline STT
- `numpy` — audio math
- `arecord` / `aplay` — ALSA audio I/O (system)

## Constraints

- Zero ROS imports anywhere in this package
- No assumptions about robot hardware beyond ALSA audio device index
- Grammar vocabulary must include every phrase in `intent_mapper.py`
