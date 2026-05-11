#!/usr/bin/env python3
from dome_voice.intent_mapper import IntentMapper, map_intent


def test_describe_scene():
    assert map_intent("describe")["name"] == "describe_scene"


def test_stop():
    assert map_intent("stop")["name"] == "stop"


def test_single_word_motion_phrases():
    assert map_intent("right")["name"] == "turn_right"
    assert map_intent("left")["name"] == "turn_left"


def test_explore():
    assert map_intent("explore")["name"] == "explore"


def test_status():
    assert map_intent("status")["name"] == "get_status"


def test_help():
    assert map_intent("help")["name"] == "get_help"


def test_return_home_words_are_not_voice_intents():
    assert map_intent("go home") is None
    assert map_intent("come back") is None
    assert map_intent("home") is None


def test_follow_words_are_not_voice_intents():
    assert map_intent("follow me") is None
    assert map_intent("follow") is None


def test_sleep_words_are_not_voice_intents():
    assert map_intent("go to sleep") is None
    assert map_intent("sleep") is None


def test_wake_words_are_not_voice_intents():
    assert map_intent("wake up") is None


def test_unknown_returns_none():
    assert map_intent("") is None
    assert map_intent("[unk]") is None
    assert map_intent("blah blah blah") is None


def test_source_is_voice():
    result = map_intent("stop")
    assert result["source"] == "voice"


def test_intent_mapper_class_api():
    mapper = IntentMapper()
    assert mapper.map_intent("stop")["name"] == "stop"
    assert mapper.map_intent("nonsense phrase") is None
