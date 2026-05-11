#!/usr/bin/env python3
# remote.launch.py — voice nodes for remote/dev machine
# Author: Pito Salas and Claude Code
# Open Source Under MIT license
from better_launch import BetterLaunch, launch_this


@launch_this(ui=True)
def remote_launch():
    bl = BetterLaunch()

    bl.node(
        "robot_voice",
        "voice_input",
    )
