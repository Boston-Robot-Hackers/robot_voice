#!/usr/bin/env python3
"""
runtime.py — ROS-free voice pipeline: wake detection, STT, and turn capture.

Author: Pito Salas and Claude Code
Open Source Under MIT license
"""

import argparse
import collections
import json
import math
import os
import subprocess
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Callable

import numpy as np

RATE = 16000
CHUNK = 1280
WAKE_SKIP_CHUNKS = 1
FLOOR_MAX_DBFS = -25.0

DEFAULT_GRAMMAR = (
    "stop",
    "right",
    "left",
    "explore",
    "describe",
    "objects",
    "status",
    "help",
)

# Paste the latest winning values from ~/tune here.
#
# This is the production voice configuration source of truth. Keep the shape
# close to tune's active.yaml so copying values from an experiment is mechanical:
# top-level capture/playback cards, stream_settings, and sox_chain.
TUNED_VOICE_PARAMETERS = {
    "capture_card": 0,
    "playback_card": 0,
    "stream_settings": {
        "wake_word": "alexa",          # openWakeWord model name to load
        "threshold": 0.7,              # min score per chunk to count as wake hit (0.0–1.0); raise if false triggers
        "wake_hits": 3,                # consecutive chunks above threshold required; raise to resist noise spikes
        "wake_cooldown_secs": 1.5,     # seconds to drain mic buffer after a turn before re-entering wake detection
        "live_filter": True,           # apply highpass/lowpass bandpass filter to mic input
        "vosk_model": "small",         # "small" or "large" — see VOSK_MODEL_PATHS
        "grammar": list(DEFAULT_GRAMMAR),  # constrained Vosk vocabulary; must include every phrase in intent_mapper
                                           # DEFAULT_GRAMMAR is source of truth — this line keeps them in sync
        "silence_dbfs": None,          # override silence floor (dBFS); None = auto from noise window
        "silence_margin": 5.0,         # dB above noise floor to classify as silence
        "silence_secs": 1.0,           # seconds of silence to end a command
        "min_command_secs": 0.4,       # minimum command duration before silence can end it
        "command_start_secs": 2.5,     # max seconds to wait for speech to start after wake
        "max_command_secs": 8.0,       # hard cap on total command capture time
    },
    "sox_chain": {
        "highpass": 120,
        "lowpass": 4000,
    },
}

TUNE_CONFIG_ENV_VARS = ("CONTROL_VOICE_TUNE_CONFIG", "VOICE_TUNE_CONFIG")

VOSK_MODEL_PATHS = {
    "small": "~/models/vosk-model-small-en-us-0.15",
    "large": "~/models/vosk-model-en-us-0.22",
}


@dataclass(frozen=True)
class VoiceRuntimeConfig:
    """Tuned voice parameters shared by the ROS node and non-ROS runtime."""

    source_path: str = ""
    capture_card: int = 0
    playback_card: int = 0
    wake_word: str = "alexa"
    threshold: float = 0.3
    wake_hits: int = 1
    wake_cooldown_secs: float = 1.5
    live_filter: bool = True
    highpass: float | None = 120.0
    lowpass: float | None = 4000.0
    vosk_model: str = "small"
    grammar: tuple[str, ...] = DEFAULT_GRAMMAR
    silence_dbfs: float | None = None
    silence_margin: float = 5.0
    silence_secs: float = 1.0
    min_command_secs: float = 0.4
    command_start_secs: float = 2.5
    max_command_secs: float = 8.0

    @property
    def vosk_model_path(self) -> str:
        model_path = VOSK_MODEL_PATHS.get(self.vosk_model, self.vosk_model)
        return os.path.expanduser(model_path)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["grammar"] = list(self.grammar)
        data["vosk_model_path"] = self.vosk_model_path
        return data


@dataclass(frozen=True)
class VoiceTurn:
    """One completed or timed-out voice interaction."""

    text: str = ""
    raw_text: str = ""
    wake_score: float = 0.0
    wake_elapsed_ms: int = 0
    command_elapsed_ms: int = 0
    empty: bool = True
    metadata: dict[str, Any] | None = None


class LiveBandpass:
    """Tiny streaming highpass/lowpass filter matching the tuned SoX cutoffs."""

    def __init__(self, highpass_hz: float | None, lowpass_hz: float | None):
        self.highpass_hz = highpass_hz if highpass_hz and highpass_hz > 0 else None
        self.lowpass_hz = lowpass_hz if lowpass_hz and lowpass_hz > 0 else None
        self.hp_x = 0.0
        self.hp_y = 0.0
        self.lp_y = 0.0

        dt = 1.0 / RATE
        self.hp_alpha = None
        self.lp_alpha = None
        if self.highpass_hz:
            rc = 1.0 / (2.0 * math.pi * self.highpass_hz)
            self.hp_alpha = rc / (rc + dt)
        if self.lowpass_hz:
            rc = 1.0 / (2.0 * math.pi * self.lowpass_hz)
            self.lp_alpha = dt / (rc + dt)

    def process(self, samples: np.ndarray) -> np.ndarray:
        x = samples.astype(np.float32)
        if self.hp_alpha is not None:
            y = np.empty_like(x)
            prev_x = self.hp_x
            prev_y = self.hp_y
            alpha = self.hp_alpha
            for i, sample in enumerate(x):
                prev_y = alpha * (prev_y + sample - prev_x)
                prev_x = float(sample)
                y[i] = prev_y
            self.hp_x = prev_x
            self.hp_y = prev_y
            x = y

        if self.lp_alpha is not None:
            y = np.empty_like(x)
            prev_y = self.lp_y
            alpha = self.lp_alpha
            for i, sample in enumerate(x):
                prev_y = prev_y + alpha * (float(sample) - prev_y)
                y[i] = prev_y
            self.lp_y = prev_y
            x = y

        return np.clip(x, -32768, 32767).astype(np.int16)


class VoiceRuntime:
    """Production voice loop with no ROS imports."""

    def __init__(
        self,
        config: VoiceRuntimeConfig | None = None,
        stream=None,
        wake_model=None,
        wake_key: str = "",
        vosk_module=None,
        stt_model=None,
        time_fn: Callable[[], float] = time.monotonic,
    ):
        self.config = config or load_voice_runtime_config()
        self.stream = stream
        self.wake_model = wake_model
        self.wake_key = wake_key
        self.vosk_module = vosk_module
        self.stt_model = stt_model
        self.time_fn = time_fn
        self.live_filter = make_live_filter(self.config)
        self._arecord_process = None

    def next_turn(
        self,
        ok_fn: Callable[[], bool] = lambda: True,
        wake_timeout_s: float | None = None,
        on_wake: Callable[[dict[str, Any]], None] | None = None,
    ) -> VoiceTurn:
        self._ensure_ready()
        wake = wait_for_wake(
            self.stream,
            self.wake_model,
            self.wake_key,
            self.config,
            live_filter=self.live_filter,
            ok_fn=ok_fn,
            timeout_s=wake_timeout_s,
            time_fn=self.time_fn,
            cooldown_s=self.config.wake_cooldown_secs,
        )
        if not wake["wake_hit"]:
            return VoiceTurn(
                wake_score=wake["score"],
                wake_elapsed_ms=wake["elapsed_ms"],
                metadata={"wake": wake},
            )
        if on_wake:
            on_wake(wake)

        command = capture_command(
            self.stream,
            self.vosk_module,
            self.stt_model,
            self.config,
            self.config.wake_word,
            grammar=list(self.config.grammar),
            live_filter=self.live_filter,
            noise_window=wake["noise_window"],
            time_fn=self.time_fn,
        )
        return VoiceTurn(
            text=command["text"],
            raw_text=command["raw_text"],
            wake_score=wake["score"],
            wake_elapsed_ms=wake["elapsed_ms"],
            command_elapsed_ms=command["elapsed_ms"],
            empty=command["empty"],
            metadata={"wake": wake, "command": command},
        )

    def close(self) -> None:
        if self._arecord_process is not None:
            _terminate_process(self._arecord_process)
            self._arecord_process = None
        self.stream = None

    def _ensure_ready(self) -> None:
        if self.stream is None:
            proc = open_arecord(self.config.capture_card)
            if proc.stdout is None:
                raise RuntimeError("arecord stdout unavailable")
            self.stream = proc.stdout
            self._arecord_process = proc
        if self.wake_model is None or not self.wake_key:
            self.wake_model, self.wake_key = load_wake_model(self.config.wake_word)
        if self.vosk_module is None or self.stt_model is None:
            self.vosk_module, self.stt_model = load_stt_model(self.config.vosk_model)


def load_voice_runtime_config(
    path: str | os.PathLike[str] | None = None,
    overrides: dict[str, Any] | None = None,
) -> VoiceRuntimeConfig:
    """Load tuned voice settings.

    By default this uses ``TUNED_VOICE_PARAMETERS`` above, which is the simple
    cut-and-paste handoff point from ``~/tune`` experiments. For comparison
    tests, set ``CONTROL_VOICE_TUNE_CONFIG`` or ``VOICE_TUNE_CONFIG`` to point at
    a tune YAML file, or pass ``path`` directly.
    """

    config_path = _resolve_config_path(path)
    if config_path is not None and config_path.exists():
        data = _load_yaml(config_path)
        source_path = str(config_path)
    else:
        data = TUNED_VOICE_PARAMETERS
        source_path = "dome_voice.runtime:TUNED_VOICE_PARAMETERS"
    config = config_from_tune_mapping(data, source_path=source_path)
    if overrides:
        config = apply_config_overrides(config, overrides)
    return config


def config_from_tune_mapping(
    data: dict[str, Any],
    source_path: str = "",
) -> VoiceRuntimeConfig:
    stream = _as_dict(data.get("stream_settings"))
    sox_chain = _as_dict(data.get("sox_chain"))

    return VoiceRuntimeConfig(
        source_path=source_path,
        capture_card=_as_int(data.get("capture_card"), 0),
        playback_card=_as_int(data.get("playback_card"), 0),
        wake_word=str(stream.get("wake_word", "alexa")),
        threshold=_as_float(stream.get("threshold"), 0.3),
        wake_hits=_as_int(stream.get("wake_hits"), 1),
        wake_cooldown_secs=_as_float(stream.get("wake_cooldown_secs"), 1.5),
        live_filter=_as_bool(stream.get("live_filter"), True),
        highpass=_optional_float(stream.get("highpass", sox_chain.get("highpass", 120))),
        lowpass=_optional_float(stream.get("lowpass", sox_chain.get("lowpass", 4000))),
        vosk_model=str(stream.get("vosk_model", "small")),
        grammar=_parse_grammar(stream.get("grammar", DEFAULT_GRAMMAR)),
        silence_dbfs=_optional_float(stream.get("silence_dbfs")),
        silence_margin=_as_float(stream.get("silence_margin"), 5.0),
        silence_secs=_as_float(stream.get("silence_secs"), 1.0),
        min_command_secs=_as_float(stream.get("min_command_secs"), 0.4),
        command_start_secs=_as_float(stream.get("command_start_secs"), 2.5),
        max_command_secs=_as_float(stream.get("max_command_secs"), 8.0),
    )


def apply_config_overrides(
    config: VoiceRuntimeConfig,
    overrides: dict[str, Any],
) -> VoiceRuntimeConfig:
    values: dict[str, Any] = {}
    for key, value in overrides.items():
        if value is None or not hasattr(config, key):
            continue
        if key == "grammar":
            value = _parse_grammar(value)
        values[key] = value
    return replace(config, **values)


def _resolve_config_path(path: str | os.PathLike[str] | None) -> Path | None:
    if path:
        return Path(path).expanduser()
    for name in TUNE_CONFIG_ENV_VARS:
        value = os.environ.get(name)
        if value:
            return Path(value).expanduser()
    return None


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("PyYAML is required to read tune voice config") from exc
    with path.open() as fh:
        return yaml.safe_load(fh) or {}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_int(value: Any, default: int) -> int:
    if value is None:
        return default
    return int(value)


def _as_float(value: Any, default: float) -> float:
    if value is None:
        return default
    return float(value)


def _optional_float(value: Any) -> float | None:
    if value in (None, "", "none", "None"):
        return None
    return float(value)


def _as_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _parse_grammar(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        items = value.split(",")
    else:
        items = value or []
    grammar = tuple(str(item).strip() for item in items if str(item).strip())
    return grammar or DEFAULT_GRAMMAR


def make_live_filter(config: VoiceRuntimeConfig) -> LiveBandpass | None:
    if not config.live_filter:
        return None
    return LiveBandpass(config.highpass, config.lowpass)


def read_mono_chunk(
    stream,
    n_samples: int = CHUNK,
    live_filter: LiveBandpass | None = None,
) -> np.ndarray | None:
    raw = stream.read(n_samples * 4)
    if len(raw) < n_samples * 4:
        return None
    stereo = np.frombuffer(raw, dtype=np.int16).reshape(-1, 2)
    mono = stereo.mean(axis=1).astype(np.float32)
    mono -= float(np.mean(mono))
    chunk = np.clip(mono, -32768, 32767).astype(np.int16)
    if live_filter:
        chunk = live_filter.process(chunk)
    return chunk


def rms_dbfs(samples: np.ndarray) -> float:
    rms = np.sqrt(np.mean(samples.astype(np.float32) ** 2))
    return 20 * math.log10(rms / 32768) if rms > 0 else -96.0


def noise_floor(samples: collections.deque[float] | list[float]) -> float | None:
    quiet = [value for value in samples if value <= FLOOR_MAX_DBFS]
    values = quiet or list(samples)
    if not values:
        return None
    return float(np.percentile(values, 20))


def silence_cutoff(
    noise_floor_value: float | None,
    override: float | None,
    margin: float,
) -> float:
    if override is not None:
        return override
    if noise_floor_value is None:
        return -38.0
    return min(noise_floor_value + margin, -22.0)


def clean_transcript(text: str, wake_word: str) -> str:
    words = text.split()
    wake_words = wake_word.replace("_", " ").split()
    if words[:len(wake_words)] == wake_words:
        return " ".join(words[len(wake_words):]).strip()
    return text


def open_arecord(card: int) -> subprocess.Popen:
    return subprocess.Popen(
        [
            "arecord",
            "-q",
            "-D",
            f"hw:{card},0",
            "-f",
            "S16_LE",
            "-r",
            str(RATE),
            "-c",
            "2",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        bufsize=CHUNK * 4,
    )


def wait_for_wake(
    stream,
    wake_model,
    wake_key: str,
    config: VoiceRuntimeConfig,
    live_filter: LiveBandpass | None = None,
    ok_fn: Callable[[], bool] = lambda: True,
    timeout_s: float | None = None,
    time_fn: Callable[[], float] = time.monotonic,
    cooldown_s: float = 0.0,
) -> dict[str, Any]:
    # Flush pipe AND model sliding window before scoring — prevents both stale
    # buffered audio and residual OWW activations from the previous "alexa" from
    # immediately re-triggering after a turn completes.
    if cooldown_s > 0:
        drain_end = time_fn() + cooldown_s
        while ok_fn() and time_fn() < drain_end:
            chunk = read_mono_chunk(stream, CHUNK, live_filter)
            if chunk is None:
                break
            wake_model.predict(chunk)

    noise_window: collections.deque[float] = collections.deque(maxlen=50)
    scores: list[float] = []
    wake_hits = 0
    chunks = 0
    start = time_fn()

    while ok_fn():
        if timeout_s is not None and time_fn() - start >= timeout_s:
            break
        chunk = read_mono_chunk(stream, CHUNK, live_filter)
        if chunk is None:
            break
        chunks += 1
        chunk_dbfs = rms_dbfs(chunk)
        score = float(wake_model.predict(chunk).get(wake_key, 0.0))
        scores.append(score)

        if score < config.threshold:
            noise_window.append(chunk_dbfs)
            wake_hits = 0
            continue

        wake_hits += 1
        if wake_hits < config.wake_hits:
            continue

        return {
            "wake_hit": True,
            "score": round(score, 6),
            "chunks": chunks,
            "elapsed_ms": round((time_fn() - start) * 1000),
            "max_score": round(max(scores), 6) if scores else 0.0,
            "noise_window": noise_window,
        }

    return {
        "wake_hit": False,
        "score": 0.0,
        "chunks": chunks,
        "elapsed_ms": round((time_fn() - start) * 1000),
        "max_score": round(max(scores), 6) if scores else 0.0,
        "noise_window": noise_window,
    }


def capture_command(
    stream,
    vosk_module,
    stt_model,
    config: VoiceRuntimeConfig,
    wake_word: str,
    grammar: list[str] | None = None,
    live_filter: LiveBandpass | None = None,
    noise_window: collections.deque[float] | None = None,
    time_fn: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    floor = noise_floor(noise_window or [])
    cutoff = silence_cutoff(floor, config.silence_dbfs, config.silence_margin)
    for _ in range(WAKE_SKIP_CHUNKS):
        read_mono_chunk(stream, CHUNK, live_filter)

    grammar_json = json.dumps((grammar or []) + ["[unk]"]) if grammar else None
    if grammar_json:
        rec = vosk_module.KaldiRecognizer(stt_model, RATE, grammar_json)
    else:
        rec = vosk_module.KaldiRecognizer(stt_model, RATE)
    rec.SetWords(True)

    silence_limit_chunks = max(1, math.ceil(config.silence_secs * RATE / CHUNK))
    min_cmd_chunks = max(1, math.ceil(config.min_command_secs * RATE / CHUNK))
    start_limit_chunks = max(1, math.ceil(config.command_start_secs * RATE / CHUNK))
    max_cmd_chunks = max(1, math.ceil(config.max_command_secs * RATE / CHUNK))

    silence_chunks = 0
    speech_chunks = 0
    command_started = False
    final_text = ""
    start = time_fn()

    for chunk_idx in range(max_cmd_chunks):
        cmd_chunk = read_mono_chunk(stream, CHUNK, live_filter)
        if cmd_chunk is None:
            break

        chunk_is_speech = rms_dbfs(cmd_chunk) > cutoff
        if chunk_is_speech:
            speech_chunks += 1
            silence_chunks = 0
            if speech_chunks >= 2:
                command_started = True
        else:
            speech_chunks = 0
            silence_chunks += 1

        endpoint = rec.AcceptWaveform(cmd_chunk.tobytes())
        if endpoint:
            result = json.loads(rec.Result())
            final_text = result.get("text", "").strip()
            if command_started and final_text and chunk_idx >= min_cmd_chunks:
                break

        if not command_started and chunk_idx >= start_limit_chunks:
            break
        if (
            command_started
            and chunk_idx >= min_cmd_chunks
            and silence_chunks >= silence_limit_chunks
        ):
            break

    if not final_text:
        final_text = json.loads(rec.FinalResult()).get("text", "").strip()

    text = clean_transcript(final_text, wake_word)
    return {
        "text": text,
        "raw_text": final_text,
        "empty": not bool(text),
        "command_started": command_started,
        "floor": floor,
        "cutoff": cutoff,
        "elapsed_ms": round((time_fn() - start) * 1000),
    }


def load_wake_model(model_name: str):
    import warnings

    saved = _suppress_fd2()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from openwakeword.model import Model as OWWModel
        oww = OWWModel(wakeword_model_paths=[_resolve_oww_model(model_name)])
    finally:
        _restore_fd2(saved)

    model_key = next(
        key for key in oww.models
        if key not in {"embedding_model", "melspectrogram", "silero_vad"}
    )
    return oww, model_key


def load_stt_model(model_key: str):
    import vosk

    vosk.SetLogLevel(-1)
    model_path = VOSK_MODEL_PATHS.get(model_key, model_key)
    model_path = os.path.expanduser(model_path)
    if not os.path.isdir(model_path):
        raise RuntimeError(f"Vosk model not found: {model_path}")
    return vosk, vosk.Model(model_path)


def _resolve_oww_model(name: str) -> str:
    if os.path.isabs(name) and os.path.exists(name):
        return name

    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        import openwakeword
    models_dir = os.path.join(os.path.dirname(openwakeword.__file__), "resources", "models")
    utility_models = {"embedding_model", "melspectrogram", "silero_vad"}
    candidates = [
        fname for fname in os.listdir(models_dir)
        if fname.endswith(".onnx") and os.path.splitext(fname)[0] not in utility_models
    ]
    for fname in candidates:
        stem = os.path.splitext(fname)[0]
        if stem == name or stem.startswith(name + "_"):
            return os.path.join(models_dir, fname)
    names = [os.path.splitext(fname)[0] for fname in candidates]
    raise RuntimeError(
        f"Wake word model '{name}' not found. Available: {', '.join(sorted(names))}"
    )


def _suppress_fd2() -> int:
    saved = os.dup(2)
    devnull = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull, 2)
    os.close(devnull)
    return saved


def _restore_fd2(saved: int) -> None:
    os.dup2(saved, 2)
    os.close(saved)


def _terminate_process(proc) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=1)
    except subprocess.TimeoutExpired:
        proc.kill()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run tuned voice runtime smoke test")
    parser.add_argument("--config", help="Path to tune active.yaml or preset YAML")
    parser.add_argument("--threshold", type=float)
    parser.add_argument("--wake-hits", type=int)
    parser.add_argument("--wake-word")
    parser.add_argument("--grammar", help="Comma-separated Vosk grammar override")
    parser.add_argument("--trials", type=int, default=0, help="Run this many voice turns")
    args = parser.parse_args()

    config = load_voice_runtime_config(
        args.config,
        overrides={
            "threshold": args.threshold,
            "wake_hits": args.wake_hits,
            "wake_word": args.wake_word,
            "grammar": args.grammar,
        },
    )
    if args.trials <= 0:
        print(json.dumps(config.to_dict(), indent=2, sort_keys=True))
        return

    runtime = VoiceRuntime(config)
    try:
        hits = 0
        empties = 0
        latencies: list[int] = []
        for trial in range(args.trials):
            print(f"Trial {trial + 1}/{args.trials}: listening for {config.wake_word!r}")
            turn = runtime.next_turn()
            hits += int(turn.wake_score >= config.threshold)
            empties += int(turn.empty)
            latencies.append(turn.command_elapsed_ms)
            print(
                json.dumps(
                    {
                        "text": turn.text,
                        "raw_text": turn.raw_text,
                        "wake_score": turn.wake_score,
                        "empty": turn.empty,
                        "command_elapsed_ms": turn.command_elapsed_ms,
                    },
                    sort_keys=True,
                )
            )
        median_latency = int(np.median(latencies)) if latencies else 0
        print(
            json.dumps(
                {
                    "trials": args.trials,
                    "wake_hits": hits,
                    "empty_count": empties,
                    "median_latency_ms": median_latency,
                },
                sort_keys=True,
            )
        )
    finally:
        runtime.close()


if __name__ == "__main__":
    main()
