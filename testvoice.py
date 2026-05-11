#!/usr/bin/env python3
"""Standalone voice test — no ROS. Listens for wake word, captures one command, prints debug."""

import sys
sys.path.insert(0, "/home/pitosalas/ros2_ws/src/robot_voice")

from robot_voice.runtime import (
    VoiceRuntime,
    load_voice_runtime_config,
    rms_dbfs,
    noise_floor,
    silence_cutoff,
    read_mono_chunk,
    CHUNK,
)


def main():
    config = load_voice_runtime_config()
    print(f"Config source: {config.source_path}")
    print(f"Wake word:     {config.wake_word!r}")
    print(f"Threshold:     {config.threshold}")
    print(f"Wake hits:     {config.wake_hits}")
    print(f"Grammar:       {list(config.grammar)}")
    print(f"Silence margin:{config.silence_margin} dB")
    print(f"Silence secs:  {config.silence_secs}")
    print(f"Min cmd secs:  {config.min_command_secs}")
    print(f"Cmd start secs:{config.command_start_secs}")
    print()

    runtime = VoiceRuntime(config)

    try:
        print(f"--- Listening for '{config.wake_word}' ---")
        print("(say 'alexa help' or any command)")
        print()

        def on_wake(wake):
            print(f"WAKE DETECTED  score={wake['score']}  elapsed={wake['elapsed_ms']}ms  max={wake['max_score']}")
            nf = noise_floor(wake["noise_window"])
            cut = silence_cutoff(nf, config.silence_dbfs, config.silence_margin)
            nf_str = f"{nf:.1f}" if nf is not None else "None"
            print(f"  noise_floor={nf_str} dBFS  silence_cutoff={cut:.1f} dBFS")
            print("  >>> speak your command now <<<")

        turn = runtime.next_turn(on_wake=on_wake)

        print()
        if not (turn.metadata or {}).get("wake", {}).get("wake_hit", False):
            print("No wake hit (timeout or stream error)")
            return

        cmd = (turn.metadata or {}).get("command", {})
        print(f"TURN RESULT")
        print(f"  text:            {turn.text!r}")
        print(f"  raw_text:        {turn.raw_text!r}")
        print(f"  empty:           {turn.empty}")
        print(f"  command_started: {cmd.get('command_started')}")
        print(f"  floor:           {cmd.get('floor')}")
        print(f"  cutoff:          {cmd.get('cutoff')}")
        print(f"  elapsed_ms:      {cmd.get('elapsed_ms')}")
        print()

        if turn.empty:
            print("DIAGNOSIS:")
            if not cmd.get("command_started"):
                print("  command_started=False — speech not detected above silence cutoff")
                print("  Try speaking louder or check cutoff vs floor values above")
            elif not turn.raw_text:
                print("  command_started=True but raw_text empty — Vosk got audio but no transcript")
                print("  Word may not be in grammar or audio too garbled")
            else:
                print(f"  raw_text={turn.raw_text!r} but text empty after clean_transcript")
        else:
            from robot_voice.intent_mapper import map_intent
            intent = map_intent(turn.text)
            print(f"INTENT: {intent}")
    finally:
        runtime.close()


if __name__ == "__main__":
    main()
