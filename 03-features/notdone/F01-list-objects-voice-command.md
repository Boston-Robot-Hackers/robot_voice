# F01 — List Objects Voice Command

**Priority**: Medium
**Done:** no
**Tasks File Created:** yes
**Tests Written:** no
**Test Passing:** no
**Description**: Add "objects" as a recognized voice word mapping to the `list_objects` intent.
Companion to dome_control/F16. dome_voice owns the grammar and intent mapping.

## How to Demo
**Setup**: voice pipeline running, say "alexa objects"

**Steps**:
1. Say "alexa objects"
2. `IntentMapper.map_intent("objects")` returns `{"name": "list_objects", ...}`

**Expected output**: intent dict with `name: list_objects` published to `/intent`
