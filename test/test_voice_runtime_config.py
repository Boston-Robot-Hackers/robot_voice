from pathlib import Path

from dome_voice.runtime import (
    DEFAULT_GRAMMAR,
    config_from_tune_mapping,
    load_voice_runtime_config,
)


def test_config_from_tune_mapping_reads_stream_settings_and_sox_chain():
    cfg = config_from_tune_mapping(
        {
            "capture_card": 2,
            "playback_card": 3,
            "sox_chain": {"highpass": 120, "lowpass": 4000},
            "stream_settings": {
                "wake_word": "alexa",
                "threshold": 0.3,
                "wake_hits": 1,
                "live_filter": True,
                "vosk_model": "small",
                "grammar": [
                    "go forward",
                    "go backward",
                    "turn left",
                    "turn right",
                    "stop",
                ],
            },
        },
        source_path="/tmp/active.yaml",
    )

    assert cfg.source_path == "/tmp/active.yaml"
    assert cfg.capture_card == 2
    assert cfg.playback_card == 3
    assert cfg.wake_word == "alexa"
    assert cfg.threshold == 0.3
    assert cfg.wake_hits == 1
    assert cfg.live_filter is True
    assert cfg.highpass == 120
    assert cfg.lowpass == 4000
    assert cfg.vosk_model == "small"
    assert cfg.grammar == (
        "go forward",
        "go backward",
        "turn left",
        "turn right",
        "stop",
    )


def test_load_voice_runtime_config_uses_path_and_overrides(tmp_path: Path):
    path = tmp_path / "active.yaml"
    path.write_text(
        """
capture_card: 0
sox_chain:
  highpass: 80
  lowpass: 3000
stream_settings:
  wake_word: alexa
  threshold: 0.5
  wake_hits: 2
  grammar: go forward,stop
""",
        encoding="utf-8",
    )

    cfg = load_voice_runtime_config(
        path,
        overrides={"threshold": 0.25, "wake_hits": 1, "grammar": "turn left,stop"},
    )

    assert cfg.source_path == str(path)
    assert cfg.threshold == 0.25
    assert cfg.wake_hits == 1
    assert cfg.highpass == 80
    assert cfg.lowpass == 3000
    assert cfg.grammar == ("turn left", "stop")


def test_load_voice_runtime_config_env_path(monkeypatch, tmp_path: Path):
    path = tmp_path / "active.yaml"
    path.write_text(
        """
stream_settings:
  wake_word: hey robot
  threshold: 0.4
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("CONTROL_VOICE_TUNE_CONFIG", str(path))

    cfg = load_voice_runtime_config()

    assert cfg.source_path == str(path)
    assert cfg.wake_word == "hey robot"
    assert cfg.threshold == 0.4


def test_missing_tune_config_falls_back_to_tuned_defaults(tmp_path: Path):
    cfg = load_voice_runtime_config(tmp_path / "missing.yaml")

    assert cfg.wake_word == "alexa"
    assert cfg.threshold == 0.7
    assert cfg.wake_hits == 3
    assert cfg.grammar == DEFAULT_GRAMMAR
