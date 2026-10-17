# Tool and runtime reference

Current implementation, 2026-10-16. Behaviour requirements and future tools: [roadmap](roadmap.md).
Paths and launch configuration: [setup](development_setup.md).

| Adapter | Parameters / result |
|---|---|
| `today` | No arguments; spoken date/time plus structured fields |
| `location` | Configured place, region, country, timezone, optional paired coordinates and provisional flag |
| `speech_control` | Optional boolean `enabled`; false sets daemon speaker volume 0 (level remembered in `speaker_restore.json`), true restores it, omitted reads |
| `voice_look` | `enabled`; runs under the stock app's background-tool manager |
| `weather` | Optional `place`, `period` (now/today/tomorrow/hourly/weekend/week), `units`; UK Met Office model via Open-Meteo for UK places; ambiguous names return candidates |
| `news` | Optional `topic`: BBC section (top, world, uk, politics, business, technology, science, health, entertainment) or any subject via Tavily news search; numbered, saved for follow-up |
| `web_search` | `query`, optional `recent` (day/week/month/year); Tavily; numbered results saved for follow-up |
| `read_article` | `number` from the last search/news list, or `url`; text via Tavily Extract, max 8000 characters |

`stay_silent` is retired. Stock search/weather, camera, sweep and move tools remain upstream;
`sweep_look` queues motion only, `camera` captures one image, and `move_head` has fixed presets.
These do not implement the roadmap's scan or precise-alignment backlog.

## No relay

The former relay (`conversation_runtime.py`) was retired on 2026-10-16 and is kept under `archive/relay/`.
The app connects directly to Pollen's backend ("deployed" mode). Mute uses the daemon volume API.
`voice_look` runs standalone; the Standard profile greeting asks the model to start it.

## Settings and source layout

`REACHY_TOOLS_STATE_DIR` defaults to `~/.config/reachy_tools/`. `location.json` stores place,
region, country, country_code, timezone, latitude/longitude and provisional status. `speaker_restore.json`
stores the level unmute restores. `last_results.json` holds the last numbered search/news list.
None of these belong in Git.

## API keys

Keys live in `~/.config/reachy_tools/keys/<name>.cred` (`REACHY_TOOLS_KEYS_DIR` overrides it, for
tests), shared by the development and live tools. Each is encrypted with `systemd-creds --user`: the
file is unreadable off the robot or by another user, and nothing is decrypted to disk. Tools run
`/usr/bin/systemd-creds --user --name=<name> decrypt` for each request and keep the key in memory only.
Accepted limit: anything running as `pollen` can decrypt it. `.claude/settings.json` denies Claude
reading the files or running the decrypt. Only the Tavily key (`tavily`) is used so far.

Manage keys on the robot, in the project folder; no sudo needed:

| Task | Command |
|---|---|
| Add or replace a key (paste it at the hidden prompt) | `scripts/keys.sh add tavily` |
| Check a key is stored and decrypts (never shown) | `scripts/keys.sh check tavily` |
| List stored key names | `scripts/keys.sh list` |
| Delete a key | `scripts/keys.sh remove tavily` |

`robot_tools/` contains the tool files and package marker. The patch helpers were moved to
`archive/retired_patches/`; installation/deployment write paths remain disabled. The old Mac-specific
`deploy_runtime.py` was deleted. The unused historical `SpeechState` code remains in speech_control.py
for regression tests; it is not the live mute implementation.

Old staged scripts under `/home/pollen/reachy_tools_deploy/` were not changed and must not be run.
Installed package files are not deployment targets. Tools run in the dashboard app interpreter, so they
use the standard library only.
