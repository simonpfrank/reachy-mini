# Tool and runtime reference

Current implementation, 2026-10-16. Behaviour requirements and future tools: [roadmap](roadmap.md).
Paths and launch configuration: [setup](development_setup.md).

| Adapter | Parameters / result |
|---|---|
| `today` | No arguments; spoken date/time plus structured fields |
| `location` | Configured place, region, country, timezone, optional paired coordinates and provisional flag |
| `speech_control` | Optional boolean `enabled`; omitted reads state, false mutes speaker, true unmutes |
| `voice_look` | `enabled`; runs under the stock app's background-tool manager |

`stay_silent` is retired. Stock search/weather, camera, sweep and move tools remain upstream;
`sweep_look` queues motion only, `camera` captures one image, and `move_head` has fixed presets.
These do not implement the roadmap's scan or precise-alignment backlog.

## Companion runtime

`conversation_runtime.py` is a supervised service, not a model-callable tool. It forwards conversation
traffic and supplies the loopback controls used by the adapters:

| Route | Method | Purpose |
|---|---|---|
| `/state`, `/health` | GET | Mute/follower state, mode and operational counters |
| `/speech` | POST `{"enabled": bool}` | ALSA `Audio` card, `PCM,0` playback mute/unmute |
| `/voice` | POST `{"enabled": bool}` | Follower preference |
| `/heartbeat` | POST | Worker identity/running heartbeat |

Mute changes the playback switch, not numeric volume, capture or response generation. It persists
in external `speech.json` and is reapplied when the service starts. No phrase matching is performed
in the live relay; `speech_control` is invoked by the model. Errors reach the caller.

## Settings and source layout

`REACHY_TOOLS_STATE_DIR` defaults to `~/.config/reachy_tools/`. `location.json` stores place,
region, country, country_code, timezone, latitude/longitude and provisional status. `speech.json`
stores the speaker preference. Neither belongs in Git. Control port is selected by
`REACHY_TOOLS_CONTROL_PORT` (default 8767).

`robot_tools/` contains adapters, runtime source and package marker. The patch helpers were moved to
`archive/retired_patches/`; installation/deployment write paths remain disabled. The old Mac-specific
`deploy_runtime.py` was deleted. The unused historical `SpeechState` code remains in speech_control.py
for regression tests; it is not the live mute implementation.

Old staged scripts under `/home/pollen/reachy_tools_deploy/` were not changed and must not be run.
Installed package files are not deployment targets. The current service still uses the dashboard
app interpreter; independent dependency management remains roadmap maintenance work.
