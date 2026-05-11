#!/usr/bin/env python3
"""ROS2 node: openWakeWord + Vosk STT + intent mapper → /intent."""

import json
import os

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from dome_voice import IntentMapper, VoiceRuntime, VoiceTurn, beep, load_voice_runtime_config

VOICE_STATES = ("IDLE", "LISTENING", "PROCESSING", "SPEAKING")


class VoiceInputNode(Node):
    def __init__(self):
        super().__init__("voice_input")
        self.intent_pub = self.create_publisher(String, "/intent", 10)
        self.state_pub = self.create_publisher(String, "/voice/state", 10)
        self.intent_mapper = IntentMapper()

    def publish_intent(self, intent: dict) -> None:
        msg = String()
        msg.data = json.dumps(intent)
        self.intent_pub.publish(msg)
        self.get_logger().info(f"Intent published: {msg.data}")

    def publish_state(self, state: str) -> None:
        msg = String()
        msg.data = state
        self.state_pub.publish(msg)
        self.get_logger().info(f"Voice state: {state}")

    def process_transcript(self, text: str, device_index: int = 0) -> None:
        self.get_logger().info(f"Transcribed: '{text}'")
        self.publish_state("PROCESSING")

        intent = self.intent_mapper.map_intent(text)
        if intent:
            self.publish_intent(intent)
            self.publish_state("SPEAKING")
            beep(frequency=330, duration=0.02, device_index=device_index)
        else:
            self.publish_state("SPEAKING")
            beep(frequency=220, duration=0.15, device_index=device_index)

    def process_turn(self, turn: VoiceTurn, device_index: int = 0) -> None:
        if turn.empty:
            cmd = (turn.metadata or {}).get("command", {})
            floor = cmd.get("floor")
            cutoff = cmd.get("cutoff")
            self.get_logger().info(
                f"Empty turn: floor={floor:.1f} cutoff={cutoff:.1f} "
                f"started={cmd.get('command_started')} raw={cmd.get('raw_text')!r}"
                if floor is not None and cutoff is not None
                else "Empty turn: no command metadata"
            )
            self.publish_state("SPEAKING")
            beep(frequency=220, duration=0.15, device_index=device_index)
            return
        self.process_transcript(turn.text, device_index=device_index)


def main():
    voice_config = load_voice_runtime_config()
    device_index = int(os.environ.get("VOICE_DEVICE_INDEX", voice_config.capture_card))

    rclpy.init()
    node = VoiceInputNode()
    runtime = VoiceRuntime(voice_config)

    try:
        node.get_logger().info(
            f"Voice input ready — listening for '{voice_config.wake_word}' "
            f"from {voice_config.source_path or 'built-in defaults'}"
        )
        node.publish_state("IDLE")

        while rclpy.ok():
            def on_wake(_wake):
                node.get_logger().info("Wake word detected — speak your command")
                node.publish_state("LISTENING")
                beep(frequency=880, duration=0.02, device_index=device_index)

            turn = runtime.next_turn(ok_fn=rclpy.ok, on_wake=on_wake)
            if turn.metadata and not turn.metadata.get("wake", {}).get("wake_hit", False):
                break
            node.process_turn(turn, device_index=device_index)
            node.publish_state("IDLE")

    finally:
        runtime.close()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
