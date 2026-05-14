#!/usr/bin/env python3
# robot.launch.py — voice nodes for the physical robot (Seeed board assumed present)
# Author: Pito Salas and Claude Code
# Open Source Under MIT license
import os

from better_launch import BetterLaunch, launch_this


@launch_this(ui=True)
def robot_launch(
    piper_bin: str = os.environ.get("DOME_PIPER_BIN", "piper"),
    piper_model_path: str = os.environ.get("DOME_PIPER_MODEL_PATH", ""),
    piper_length_scale: str = os.environ.get("PIPER_LENGTH_SCALE", "1.0"),
    speech_gain: str = os.environ.get("SPEECH_GAIN", "0.25"),
    speech_alsa_device: str = os.environ.get("SPEECH_ALSA_DEVICE", "plughw:0,0"),
):
    bl = BetterLaunch()

    bl.node(
        "dome_voice",
        "voice_input",
        name="voice_input",
    )

    bl.node(
        "dome_voice",
        "speech_output",
        "speech_output",
        env={
            "DOME_PIPER_BIN": piper_bin,
            "DOME_PIPER_MODEL_PATH": piper_model_path,
            "PIPER_LENGTH_SCALE": piper_length_scale,
            "SPEECH_GAIN": speech_gain,
            "SPEECH_ALSA_DEVICE": speech_alsa_device,
        },
    )
