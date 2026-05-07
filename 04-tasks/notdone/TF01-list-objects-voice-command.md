# TF01 — List Objects Voice Command

## T01 — Add intent mapping
**Status**: not done
**Description**: In `intent_mapper.py` add `(("objects",), "list_objects")` to `PHRASE_INTENTS`.
Write unit test: `map_intent("objects")["name"] == "list_objects"`.

## T02 — Add to grammar
**Status**: not done
**Description**: In `runtime.py` add `"objects"` to `DEFAULT_GRAMMAR` tuple and to
`TUNED_VOICE_PARAMETERS["stream_settings"]["grammar"]` list. Vosk will not
recognize the word otherwise.
