# robot_voice

ROS-free voice pipeline: wake word detection, speech-to-text, intent mapping, and audio feedback for robot control.

## Installation

```bash
# Within a ROS2 workspace:
colcon build --packages-select robot_voice
source install/setup.bash
```

## Usage

```bash
# Smoke test (hardware required):
python3 -m robot_voice.runtime --trials 5
# or via entry point:
ros2 run robot_voice voice_smoke_test --trials 5
```

## Development

```bash
python3 -m pytest test/
```

## License

MIT — see [LICENSE](LICENSE)
