# Copilot instructions for Viernes

## Build
- Standalone binary (PyInstaller): `./scripts/build_app.sh`

## Tests
- Full suite: `pytest`
- Single test: `pytest tests/test_intent_parser.py::TestIntentParser::test_parse_success`

## High-level architecture
- **Entry points:** `main.py` (console/orchestrator) and `gui.py` (CustomTkinter UI + tray) both instantiate `ViernesAssistant`.
- **Voice pipeline:** `core.audio_listener.AudioListener` handles wake word (Vosk) and command capture (Whisper). Parsed text goes to `core.intent_parser.IntentParser`, which can short-circuit locally (templates/macros) or call Ollama and returns a **list** of intent objects.
- **Dispatch layer:** `core.dispatcher.Dispatcher` maps intents to action classes in `actions/` using `config.json:intent_mapping` and executes them.
- **Remote control:** `core.web_server` (FastAPI + WebSockets) is started by `ViernesAssistant` and serves `static/` plus remote mic/volume/media controls. `core.tts` can route speech back to connected mobile clients.

## Key conventions
- **`config.json` is the source of truth** for `intents`, `intent_mapping`, `whitelist_apps`, `keyboard_macros`, `games`, and `phonetics`. Actions should read config, not hardcode values.
- **Actions are class-based modules** under `actions/` and are referenced by class name in `config.json:intent_mapping`. Keep new actions compatible with `ActionModule` from `actions/base_action.py`.
- **Packaged builds need explicit imports:** if you add a new action, include it in the frozen-mode imports in `core/dispatcher.py` and add a `--hidden-import=actions.<module>` entry in `scripts/build_app.sh`.
- **Intent entities include `_raw_text`** (added by `IntentParser`) and some actions rely on it; preserve it if you transform intents.
