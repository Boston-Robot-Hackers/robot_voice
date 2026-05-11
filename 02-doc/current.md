# dome_voice — Current Session Handoff

## Snapshot

**Branch:** `main` (lives inside `ros2_ws/src/dome_voice/`, sibling to `control/`)

This package was extracted from `control/voice/` to be a standalone, ROS-free voice pipeline.
`control/` consumes it via `voice_input_node.py` (the only ROS adapter).

## What Is Built

- `runtime.py` — `VoiceRuntime`, `VoiceRuntimeConfig`, `load_voice_runtime_config`, full pipeline
- `intent_mapper.py` — `IntentMapper`: transcript → intent dict (7 commands)
- `audio_feedback.py` — `beep()` via aplay
- `__init__.py` — public API surface
- `test/` — 21 passing tests, 2 pre-existing failures in `test_voice_runtime.py`

## Known Issues

- 2 test failures in `test_voice_runtime.py` (`test_capture_command_returns_transcript_text`,
  `test_voice_runtime_next_turn_uses_fake_models`) — pre-existing before extraction, not regressions.
- Empty STT turns on hardware: debug fields (`floor`, `cutoff`, `command_started`, `raw_text`)
  are logged by `voice_input_node` in control. Next: observe on hardware.

## Likely Next Steps

1. Fix the 2 failing unit tests.
2. Create `02-doc/notes.md` with architecture decisions.
3. Set up git repo if separating from control workspace.

## Quick Commands

```bash
# Build
colcon build --packages-select dome_voice

# Test
python3 -m pytest test/

# Smoke test (hardware)
python3 -m dome_voice.runtime --trials 5
```
