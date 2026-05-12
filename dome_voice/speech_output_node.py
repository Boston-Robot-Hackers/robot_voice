#!/usr/bin/env python3
"""ROS2 node: subscribe to /announcement and speak via Piper + ALSA."""

import os
import struct
import subprocess
import tempfile
import wave

import rclpy
from rclpy.node import Node

from dome_control.announcement_contract import Announcement, AnnouncementMsg


def synthesize_to_wav(
    text: str,
    wav_path: str,
    piper_bin: str,
    model_path: str,
    length_scale: float = 1.0,
) -> None:
    """Synthesize text to wav_path using Piper."""
    if not model_path:
        raise RuntimeError("PIPER_MODEL_PATH is required for speech output")

    cmd = [
        piper_bin,
        "--model",
        model_path,
        "--output_file",
        wav_path,
        "--length_scale",
        str(length_scale),
        "--quiet",
    ]
    subprocess.run(
        cmd,
        input=text.encode("utf-8"),
        check=True,
        capture_output=True,
    )


def play_wav(wav_path: str, alsa_device: str = "") -> None:
    """Play wav_path using ALSA aplay."""
    cmd = ["aplay"]
    if alsa_device:
        cmd.extend(["-D", alsa_device])
    cmd.append(wav_path)
    subprocess.run(cmd, check=True, capture_output=True)


def _scale_pcm_frames(frames: bytes, sample_width: int, gain: float) -> bytes:
    if sample_width not in (1, 2, 4):
        raise ValueError(f"Unsupported WAV sample width: {sample_width}")

    max_value = (1 << (sample_width * 8 - 1)) - 1
    min_value = -(1 << (sample_width * 8 - 1))
    fmt_by_width = {1: "b", 2: "h", 4: "i"}
    fmt = "<" + fmt_by_width[sample_width]
    scaled = bytearray()

    for offset in range(0, len(frames), sample_width):
        sample = struct.unpack_from(fmt, frames, offset)[0]
        adjusted = int(sample * gain)
        adjusted = max(min(adjusted, max_value), min_value)
        scaled.extend(struct.pack(fmt, adjusted))

    return bytes(scaled)


def apply_wav_gain(input_path: str, output_path: str, gain: float) -> None:
    """Write a copy of input_path to output_path with sample amplitude scaled."""
    if gain <= 0:
        raise ValueError("SPEECH_GAIN must be greater than 0")

    with wave.open(input_path, "rb") as source:
        params = source.getparams()
        frames = source.readframes(source.getnframes())

    adjusted = _scale_pcm_frames(frames, params.sampwidth, gain)

    with wave.open(output_path, "wb") as target:
        target.setparams(params)
        target.writeframes(adjusted)


def parse_speech_gain(value: str) -> float:
    try:
        gain = float(value)
    except ValueError as exc:
        raise ValueError("SPEECH_GAIN must be a number") from exc

    if gain <= 0:
        raise ValueError("SPEECH_GAIN must be greater than 0")
    return gain


def parse_length_scale(value: str) -> float:
    try:
        length_scale = float(value)
    except ValueError as exc:
        raise ValueError("PIPER_LENGTH_SCALE must be a number") from exc

    if length_scale <= 0:
        raise ValueError("PIPER_LENGTH_SCALE must be greater than 0")
    return length_scale


class SpeechOutputNode(Node):
    def __init__(self):
        super().__init__("speech_output")
        self.announcement_sub = self.create_subscription(
            AnnouncementMsg, "/announcement", self.on_announcement, 10
        )
        self.piper_bin = os.environ.get("PIPER_BIN", "piper")
        self.piper_model_path = os.environ.get("PIPER_MODEL_PATH", "")
        self.alsa_device = os.environ.get("SPEECH_ALSA_DEVICE", "")
        self.tmp_dir = os.environ.get("SPEECH_TMP_DIR", tempfile.gettempdir())
        self.speech_gain = parse_speech_gain(os.environ.get("SPEECH_GAIN", "0.35"))
        self.length_scale = parse_length_scale(
            os.environ.get("PIPER_LENGTH_SCALE", "1.25")
        )

    def on_announcement(self, msg: AnnouncementMsg) -> None:
        announcement = Announcement.from_msg(msg)
        if not announcement.text:
            self.get_logger().debug("Ignoring empty announcement payload")
            return

        try:
            self.speak_text(announcement.text)
            self.get_logger().info(
                f"Spoken announcement ({announcement.priority}) from "
                f"{announcement.source}: {announcement.text}"
            )
        except Exception as exc:
            self.get_logger().error(f"Speech output failed: {exc}")

    def _make_wav_path(self) -> str:
        fd, path = tempfile.mkstemp(
            prefix="speech-output-",
            suffix=".wav",
            dir=self.tmp_dir,
        )
        os.close(fd)
        return path

    def speak_text(self, text: str) -> None:
        wav_path = self._make_wav_path()
        playback_path = wav_path
        gained_path = None
        try:
            synthesize_to_wav(
                text=text,
                wav_path=wav_path,
                piper_bin=self.piper_bin,
                model_path=self.piper_model_path,
                length_scale=self.length_scale,
            )
            if self.speech_gain != 1.0:
                gained_path = self._make_wav_path()
                apply_wav_gain(wav_path, gained_path, self.speech_gain)
                playback_path = gained_path
            play_wav(playback_path, alsa_device=self.alsa_device)
        finally:
            for path in (wav_path, gained_path):
                if path:
                    try:
                        os.remove(path)
                    except FileNotFoundError:
                        pass


def main():
    rclpy.init()
    node = SpeechOutputNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
