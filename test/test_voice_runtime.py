import collections
import json
from dataclasses import replace

import numpy as np

from robot_voice.runtime import (
    CHUNK,
    LiveBandpass,
    VoiceRuntime,
    capture_command,
    load_voice_runtime_config,
    make_live_filter,
    read_mono_chunk,
    wait_for_wake,
)


class FakeStream:
    def __init__(self, chunks):
        self.chunks = list(chunks)

    def read(self, _size):
        if not self.chunks:
            return b""
        return self.chunks.pop(0)


class FakeWakeModel:
    def __init__(self, scores):
        self.scores = list(scores)

    def predict(self, _chunk):
        score = self.scores.pop(0) if self.scores else 0.0
        return {"alexa": score}


class FakeRecognizer:
    def __init__(self, text):
        self.text = text
        self.calls = 0

    def SetWords(self, _enabled):
        pass

    def AcceptWaveform(self, _data):
        self.calls += 1
        return self.calls >= 2

    def Result(self):
        return json.dumps({"text": self.text})

    def FinalResult(self):
        return json.dumps({"text": self.text})


class FakeVosk:
    def __init__(self, text):
        self.text = text
        self.grammar = None

    def KaldiRecognizer(self, _model, _rate, grammar=None):
        self.grammar = grammar
        return FakeRecognizer(self.text)


def stereo_chunk(left, right=None, n=CHUNK):
    if right is None:
        right = left
    stereo = np.column_stack([
        np.full(n, left, dtype=np.int16),
        np.full(n, right, dtype=np.int16),
    ])
    return stereo.tobytes()


def test_runtime_module_has_no_ros_import():
    import robot_voice.runtime as runtime

    assert not hasattr(runtime, "rclpy")


def test_read_mono_chunk_removes_dc_offset():
    signal = np.arange(CHUNK, dtype=np.int16) % 100
    stereo = np.column_stack([signal + 1000, signal + 1000]).astype(np.int16)
    chunk = read_mono_chunk(FakeStream([stereo.tobytes()]))

    assert chunk.shape == (CHUNK,)
    assert abs(float(np.mean(chunk))) < 1.0


def test_make_live_filter_can_be_enabled_and_disabled():
    cfg = load_voice_runtime_config()

    assert isinstance(make_live_filter(cfg), LiveBandpass)
    assert make_live_filter(replace(cfg, live_filter=False)) is None


def test_wait_for_wake_honors_threshold_and_wake_hits():
    cfg = replace(load_voice_runtime_config(), threshold=0.3, wake_hits=2)
    stream = FakeStream([
        stereo_chunk(20),
        stereo_chunk(20),
        stereo_chunk(20),
    ])
    wake = wait_for_wake(
        stream,
        FakeWakeModel([0.2, 0.4, 0.5]),
        "alexa",
        cfg,
        time_fn=lambda: 0.0,
    )

    assert wake["wake_hit"] is True
    assert wake["chunks"] == 3
    assert wake["score"] == 0.5


def test_capture_command_returns_transcript_text():
    cfg = replace(
        load_voice_runtime_config(),
        min_command_secs=0.0,
        command_start_secs=1.0,
        max_command_secs=1.0,
        silence_dbfs=-80.0,
    )
    chunks = [stereo_chunk(0) for _ in range(4)] + [
        stereo_chunk(2000),
        stereo_chunk(2000),
    ]
    vosk = FakeVosk("alexa go forward")

    result = capture_command(
        FakeStream(chunks),
        vosk,
        object(),
        cfg,
        "alexa",
        grammar=list(cfg.grammar),
        noise_window=collections.deque([-50.0], maxlen=50),
        time_fn=lambda: 0.0,
    )

    assert result["text"] == "go forward"
    assert result["raw_text"] == "alexa go forward"
    assert result["empty"] is False
    assert "go forward" in vosk.grammar


def test_voice_runtime_next_turn_uses_fake_models():
    cfg = replace(
        load_voice_runtime_config(),
        threshold=0.3,
        wake_hits=1,
        min_command_secs=0.0,
        max_command_secs=1.0,
        silence_dbfs=-80.0,
    )
    chunks = [stereo_chunk(10)] + [stereo_chunk(0) for _ in range(4)] + [
        stereo_chunk(2000),
        stereo_chunk(2000),
    ]
    runtime = VoiceRuntime(
        cfg,
        stream=FakeStream(chunks),
        wake_model=FakeWakeModel([0.6]),
        wake_key="alexa",
        vosk_module=FakeVosk("alexa stop"),
        stt_model=object(),
        time_fn=lambda: 0.0,
    )
    wake_events = []

    turn = runtime.next_turn(on_wake=lambda wake: wake_events.append(wake))

    assert turn.text == "stop"
    assert turn.raw_text == "alexa stop"
    assert turn.empty is False
    assert turn.wake_score == 0.6
    assert len(wake_events) == 1
