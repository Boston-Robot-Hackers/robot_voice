# dome_voice — Notes

## Extraction from control/

Extracted from `control/voice/` 2026-05-07. Dead files `stt.py` and `wake_word.py` were dropped
(legacy pyaudio-based classes, broken imports, unused by the production pipeline).

## arecord vs pyaudio

Pipeline uses `arecord` subprocess (stereo S16_LE) rather than pyaudio. Avoids ALSA/pyaudio
device index conflicts on Raspberry Pi. Stereo→mono average in `read_mono_chunk`.

## Grammar constraint

Vosk grammar must include every phrase in `PHRASE_INTENTS` plus `[unk]`. Adding a new voice
command requires updating both `intent_mapper.py` and `TUNED_VOICE_PARAMETERS["stream_settings"]["grammar"]`.

## Tuned parameters

`TUNED_VOICE_PARAMETERS` in `runtime.py` is the paste target for `~/tune` experiment results.
Shape mirrors tune's `active.yaml` so values can be copied mechanically.
