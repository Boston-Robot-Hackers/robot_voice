#!/usr/bin/env python3
import json
import wave
from unittest.mock import MagicMock, patch

from dome_control.announcement_contract import (
    Announcement,
    PRIORITY_CHITCHAT,
    PRIORITY_QUERY_REPLY,
    make_announcement_msg,
)
from dome_voice.speech_output_node import (
    apply_wav_gain,
    parse_length_scale,
    parse_speech_gain,
    play_wav,
    synthesize_to_wav,
)


def _make_node():
    with patch("rclpy.node.Node.__init__", return_value=None):
        from dome_voice.speech_output_node import SpeechOutputNode

        node = SpeechOutputNode.__new__(SpeechOutputNode)
        node.get_logger = MagicMock(return_value=MagicMock())
        node.piper_bin = "piper"
        node.piper_model_path = "/tmp/model.onnx"
        node.alsa_device = "hw:1,0"
        node.speech_gain = 0.35
        node.length_scale = 1.25
        node.speak_text = MagicMock()
        return SpeechOutputNode, node


def test_parse_announcement_payload_json():
    payload = json.dumps(
        {
            "text": "I see a can",
            "priority": PRIORITY_QUERY_REPLY,
            "source": "behavior_manager",
        }
    )
    parsed = Announcement.from_payload(payload)
    assert parsed == Announcement(
        text="I see a can",
        priority=PRIORITY_QUERY_REPLY,
        source="behavior_manager",
    )


def test_parse_announcement_payload_plain_text():
    parsed = Announcement.from_payload("hello robot")
    assert parsed == Announcement(
        text="hello robot",
        priority=PRIORITY_CHITCHAT,
        source="unknown",
    )


def test_parse_announcement_payload_empty_text():
    parsed = Announcement.from_payload("   ")
    assert parsed.text == ""


def test_on_announcement_calls_speak_text():
    SpeechOutputNode, node = _make_node()
    msg = make_announcement_msg(
        "hello there",
        priority=PRIORITY_QUERY_REPLY,
        source="test",
    )
    SpeechOutputNode.on_announcement(node, msg)
    node.speak_text.assert_called_once_with("hello there")


def test_on_announcement_ignores_empty():
    SpeechOutputNode, node = _make_node()
    msg = make_announcement_msg("   ")
    SpeechOutputNode.on_announcement(node, msg)
    node.speak_text.assert_not_called()


@patch("dome_voice.speech_output_node.subprocess.run")
def test_synthesize_to_wav_invokes_piper(mock_run):
    synthesize_to_wav(
        text="test speech",
        wav_path="/tmp/out.wav",
        piper_bin="piper",
        model_path="/tmp/model.onnx",
        length_scale=1.4,
    )
    mock_run.assert_called_once()
    cmd = mock_run.call_args.args[0]
    assert cmd[:2] == ["piper", "--model"]
    assert "/tmp/model.onnx" in cmd
    assert "--output_file" in cmd
    assert "/tmp/out.wav" in cmd
    assert "--length_scale" in cmd
    assert "1.4" in cmd
    assert "--quiet" in cmd


@patch("dome_voice.speech_output_node.subprocess.run")
def test_play_wav_invokes_aplay(mock_run):
    play_wav("/tmp/out.wav", alsa_device="hw:1,0")
    mock_run.assert_called_once_with(
        ["aplay", "-D", "hw:1,0", "/tmp/out.wav"],
        check=True,
        capture_output=True,
    )


def test_parse_speech_gain():
    assert parse_speech_gain("0.35") == 0.35
    assert parse_speech_gain("1") == 1.0


def test_parse_speech_gain_rejects_bad_values():
    for value in ("0", "-1", "loud"):
        try:
            parse_speech_gain(value)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Expected ValueError for {value}")


def test_parse_length_scale():
    assert parse_length_scale("1.25") == 1.25
    assert parse_length_scale("0.75") == 0.75


def test_parse_length_scale_rejects_bad_values():
    for value in ("0", "-1", "fast"):
        try:
            parse_length_scale(value)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Expected ValueError for {value}")


def _write_test_wav(path):
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes((10000).to_bytes(2, byteorder="little", signed=True))


def _read_test_sample(path):
    with wave.open(str(path), "rb") as wav:
        frame = wav.readframes(1)
    return int.from_bytes(frame, byteorder="little", signed=True)


def test_apply_wav_gain_reduces_sample_amplitude(tmp_path):
    raw_path = tmp_path / "raw.wav"
    quiet_path = tmp_path / "quiet.wav"
    _write_test_wav(raw_path)

    apply_wav_gain(str(raw_path), str(quiet_path), 0.35)

    assert _read_test_sample(quiet_path) == 3500


@patch("dome_voice.speech_output_node.play_wav")
@patch("dome_voice.speech_output_node.apply_wav_gain")
@patch("dome_voice.speech_output_node.synthesize_to_wav")
def test_speak_text_applies_gain_when_configured(mock_synth, mock_gain, mock_play):
    from dome_voice.speech_output_node import SpeechOutputNode

    node = SpeechOutputNode.__new__(SpeechOutputNode)
    node.piper_bin = "piper"
    node.piper_model_path = "/tmp/model.onnx"
    node.alsa_device = "hw:1,0"
    node.speech_gain = 0.35
    node.length_scale = 1.25
    node.make_wav_path = MagicMock(
        side_effect=["/tmp/raw.wav", "/tmp/quiet.wav"]
    )

    SpeechOutputNode.speak_text(node, "hello")

    mock_synth.assert_called_once()
    assert mock_synth.call_args.kwargs["length_scale"] == 1.25
    mock_gain.assert_called_once_with("/tmp/raw.wav", "/tmp/quiet.wav", 0.35)
    mock_play.assert_called_once_with("/tmp/quiet.wav", alsa_device="hw:1,0")
