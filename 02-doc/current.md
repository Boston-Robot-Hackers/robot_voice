# dome_voice — Current Session Handoff

## Snapshot

**Branch:** `main` (lives inside `ros2_ws/src/dome_voice/`, sibling to `control/`)

This package was extracted from `control/voice/` to be a standalone, ROS-free voice pipeline.
`control/` consumes it via `voice_input_node.py` (the only ROS adapter).

## What Is Built

- `runtime.py` — `VoiceRuntime`, `VoiceRuntimeConfig`, `load_voice_runtime_config`, full pipeline
- `intent_mapper.py` — `IntentMapper`: transcript → intent dict (8 commands: stop, right, left, explore, describe, objects, status, help)
- `audio_feedback.py` — `beep()` via aplay
- `speech_output_node.py` — ROS2 node: subscribes `/announcement`, speaks via Piper TTS + ALSA
- `__init__.py` — public API surface
- `test/` — 42 passing tests (all green)
- `01-literate/` — literate docs: 00-overview, 01-runtime, 02-intent_mapper, 03-voice_input_node, 04-speech_output_node, X01-audio_feedback

## Known Issues

None. All 42 tests pass.

## Quick Commands

```bash
# Build
colcon build --packages-select dome_voice

# Test
python3 -m pytest test/

# Smoke test (hardware)
python3 -m dome_voice.runtime --trials 5
```
