---
version: "1.0"
generated: "2026-05-13"
---

# Chapter 4 — speech_output_node.py

## Purpose

`speech_output_node.py` is the ROS2 speech output adapter. It subscribes to `/announcement`, synthesizes the text payload to a WAV file using Piper TTS, optionally scales the sample amplitude, and plays it via ALSA `aplay`. Like `voice_input_node.py`, it is a thin ROS shell — all the non-trivial logic is in pure functions that can be tested without a running ROS graph.

## Module Structure

```
speech_output_node.py
├── synthesize_to_wav()   # invoke Piper binary via subprocess
├── play_wav()            # invoke aplay via subprocess
├── scale_pcm_frames()    # PCM sample amplitude scaling (pure, no I/O)
├── apply_wav_gain()      # read WAV → scale → write new WAV
├── parse_speech_gain()   # validate SPEECH_GAIN env var
├── parse_length_scale()  # validate PIPER_LENGTH_SCALE env var
├── SpeechOutputNode      # ROS2 Node subclass
│   ├── __init__          # subscribe, read env vars
│   ├── on_announcement() # callback: parse msg, call speak_text
│   ├── make_wav_path()   # create a temp file, return path
│   └── speak_text()      # orchestrate synth → gain → play → cleanup
└── main()                # rclpy init/spin/shutdown
```

## Configuration via Environment Variables

All configuration comes from environment variables, validated at startup by `parse_speech_gain` and `parse_length_scale`. This avoids ROS parameter boilerplate for a node that runs as a system service.

| Variable | Default | Meaning |
|---|---|---|
| `DOME_PIPER_BIN` | `"piper"` | Path to Piper binary |
| `DOME_PIPER_MODEL_PATH` | `""` | Path to `.onnx` voice model (required for speech) |
| `PIPER_LENGTH_SCALE` | `"1.25"` | TTS speed (>1 = slower) |
| `SPEECH_ALSA_DEVICE` | `""` | ALSA device string, e.g. `hw:1,0`; empty = default |
| `SPEECH_GAIN` | `"0.35"` | PCM amplitude multiplier applied after synthesis |
| `SPEECH_TMP_DIR` | system tmp | Directory for temporary WAV files |

`SPEECH_GAIN` defaults to 0.35 (35%) because Piper's default output level clips the amplifier on the robot's speaker. The gain is applied in software rather than at the ALSA mixer to keep the pipeline hardware-agnostic.

## speak_text() Flow

```
speak_text(text)
  │
  ├─ make_wav_path()         → raw.wav  (temp file)
  ├─ synthesize_to_wav()     → writes PCM to raw.wav via Piper subprocess
  │
  ├─ if speech_gain != 1.0:
  │    make_wav_path()       → gained.wav  (second temp file)
  │    apply_wav_gain()      → copies raw.wav with scaled samples
  │    playback_path = gained.wav
  │  else:
  │    playback_path = raw.wav
  │
  ├─ play_wav(playback_path) → aplay subprocess
  │
  └─ finally: os.remove() both temp files (best-effort)
```

The `finally` block cleans up regardless of subprocess errors. `FileNotFoundError` is silently swallowed in cleanup because synthesis may have failed before the file was written.

## scale_pcm_frames() — PCM Arithmetic

WAV PCM samples are little-endian signed integers. The function unpacks each sample, multiplies by `gain`, clamps to the representable range for the sample width, and repacks. Supported widths: 1-byte (`b`), 2-byte (`h`), 4-byte (`i`).

The clamp prevents wrap-around distortion when gain > 1.0 (though the default gain of 0.35 never triggers it).

## Testing Strategy

All pure functions (`synthesize_to_wav`, `play_wav`, `scale_pcm_frames`, `apply_wav_gain`, `parse_speech_gain`, `parse_length_scale`) are tested without ROS or hardware. The node callback (`on_announcement`) is tested by constructing a bare `SpeechOutputNode` subclass that skips `rclpy.Node.__init__`, then calling the method directly with a mock message.

`speak_text` is tested by patching `synthesize_to_wav`, `apply_wav_gain`, `play_wav`, and `make_wav_path` — verifying the orchestration logic (gain branch, cleanup) without touching disk or spawning subprocesses.
