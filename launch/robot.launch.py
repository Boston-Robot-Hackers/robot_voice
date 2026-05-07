#!/usr/bin/env python3
# robot.launch.py — voice nodes for the physical robot (Seeed board assumed present)
# Author: Pito Salas and Claude Code
# Open Source Under MIT license
from better_launch import BetterLaunch, launch_this


@launch_this(ui=False)
def robot_launch():
    bl = BetterLaunch()

    bl.node(
        "robot_voice",
        "voice_input",
        "voice_input",
    )
