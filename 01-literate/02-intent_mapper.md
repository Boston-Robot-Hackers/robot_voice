---
version: "1.0"
generated: "2026-05-12"
---

# intent_mapper.py — Transcript to Intent

## What This Module Does

`intent_mapper.py` converts a raw Vosk transcript string into a structured intent dict. It sits between the STT layer (`runtime.py`) and any downstream consumer (ROS node, test harness, CLI). Its job is narrow: accept a string, return either `None` (unrecognized) or a dict like `{"name": "turn_right", "source": "voice", "slots": {}}`.

The module is deliberately ignorant of audio, ROS, or configuration. It is a pure function wrapped in a thin class.

## The Phrase Table

All recognized commands live in a single tuple-of-tuples constant:

```python
PHRASE_INTENTS = (
    (("stop",),     "stop"),
    (("right",),    "turn_right"),
    (("left",),     "turn_left"),
    (("explore",),  "explore"),
    (("describe",), "describe_scene"),
    (("objects",),  "list_objects"),
    (("status",),   "get_status"),
    (("help",),     "get_help"),
)
```

Each row is `(phrases_tuple, intent_name)`. The phrases tuple is a set of synonyms for a single intent — currently each intent has exactly one phrase, but the structure allows multi-word synonyms without any code change. The intent name is a normalized verb-noun string that consumers dispatch on.

This table is also the source of truth for the grammar fed to Vosk's `KaldiRecognizer` in `runtime.py`. They must stay in sync; currently this is enforced by convention. See the observations section.

## Matching Logic

```python
def contains_phrase(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in text for phrase in phrases)
```

`contains_phrase` uses substring matching, not word-boundary matching. This is intentional: Vosk returns clean single-word transcripts for constrained grammars, and the implementation favors simplicity over precision. For multi-word synonyms (e.g. `"turn right"`), substring matching is the natural fit.

`IntentMapper.map_intent` normalizes to lowercase, rejects empty strings and the Vosk OOV token `[unk]`, then scans `PHRASE_INTENTS` in order:

```python
def map_intent(self, text: str) -> dict | None:
    normalized_text = text.lower().strip()
    if not normalized_text or normalized_text == "[unk]":
        return None

    for phrases, name in PHRASE_INTENTS:
        if contains_phrase(normalized_text, phrases):
            return {"name": name, "source": self.SOURCE, "slots": {}}

    return None
```

First match wins. Order in `PHRASE_INTENTS` is the priority order if synonyms ever overlap.

## Data Flow

```mermaid
flowchart LR
    TEXT[transcript string] --> NORM[normalize: lowercase + strip]
    NORM --> REJECT{empty or\n'[unk]'?}
    REJECT -- yes --> NONE[None]
    REJECT -- no --> SCAN[scan PHRASE_INTENTS]
    SCAN -- match --> DICT["{'name': ..., 'source': 'voice', 'slots': {}}"]
    SCAN -- no match --> NONE2[None]
```

## Module-Level Singleton

```python
DEFAULT_MAPPER = IntentMapper()

def map_intent(text: str) -> dict | None:
    """Compatibility wrapper for existing call sites and tests."""
    return DEFAULT_MAPPER.map_intent(text)
```

The module exports both the class and a module-level function. The function exists purely for call-site ergonomics and backward compatibility — callers that don't need a custom mapper don't need to instantiate one. Both paths are tested.

## Observations and Improvement Opportunities

- **Grammar coupling** — `DEFAULT_GRAMMAR` in `runtime.py` must enumerate exactly the same words as `PHRASE_INTENTS` keys. A drift would cause Vosk to accept phrases the mapper can't handle (returning `None`) or reject valid commands. The fix is to export the word list from `intent_mapper.py` and import it into `runtime.py`:

  ```python
  # intent_mapper.py
  GRAMMAR_WORDS = tuple(phrase for phrases, _ in PHRASE_INTENTS for phrase in phrases)
  ```

- **`slots` is always `{}`** — the dict schema implies future slot filling (e.g. `{"direction": "left"}`), but nothing fills it today. Fine for now; it signals the intended extension point.

- **`contains_phrase` is substring, not token** — `"righteous"` would match `"right"`. In practice this can't happen because Vosk's constrained grammar only returns exact grammar words. But if the grammar ever opens up, `re.search(r'\bright\b', text)` would be safer.
