# Tool and runtime reference

Current implementation, 2026-10-16. Behaviour requirements and future tools: [roadmap](roadmap.md).
Paths and launch configuration: [setup](development_setup.md).

| Adapter | Parameters / result |
|---|---|
| `today` | No arguments; spoken date/time plus structured fields |
| `location` | Configured place, region, country, timezone, optional paired coordinates and provisional flag |
| `speech_control` | Optional boolean `enabled`; false sets daemon speaker volume 0 (level remembered in `speaker_restore.json`), true restores it, omitted reads |
| `voice_look` | Optional `enabled` (default on); turns toward whoever is talking; starts a task inside the app and replies at once |
| `weather` | Optional `place`, `period` (now/today/tomorrow/hourly/weekend/week), `units`; UK Met Office model via Open-Meteo for UK places; ambiguous names return candidates |
| `news` | Optional `topic`: BBC section (top, world, uk, politics, business, technology, science, health, entertainment) or any subject via Tavily news search; numbered, saved for follow-up |
| `web_search` | `query`, optional `recent` (day/week/month/year); Tavily; numbered results saved for follow-up |
| `photo` | No arguments; takes one frame without moving the head and records the measured pose (no levelling); saves `photo.jpg` + `photo.json` (pose, time, resolution) owner-only in `~/.local/share/reachy-tools/camera/`, replacing the last. Nothing goes to the model |
| `room_scan` | No arguments; starts a background scan and replies at once. One queued move through 7 stops (default settings, about 40 s) and back to the starting pose, a photo at each stop; saves `scan_NN.jpg` + `scan.json` (reason, settings, planned and measured poses, complete flag) owner-only in `~/.local/share/reachy-tools/scan/` (`REACHY_TOOLS_SCAN_DIR`), replacing the last scan. Not analysed yet. Settings `REACHY_SCAN_*`: `OVERLAP` 0.25, `HFOV_DEG` 87, `BODY_YAW_MIN_DEG`/`MAX_DEG` −125/140, `HEAD_YAW_MIN_DEG`/`MAX_DEG` −35/35, `PITCH_DEG` 0, `SETTLE_S` 0.5, `CROP` 1.0, `CONFIDENCE` 0.35, `NMS_IOU` 0.5, `ANALYSIS_THREADS` 1, `STALE_AFTER_S` 900, `MERGE_TOLERANCE_DEG` 3, `MERGE_OVERLAP` 0.5. Also read from `scan.json` (below). Each photo is analysed as it is taken (pass `now`, YOLOX-Nano) and again over all photos when the robot is back (pass `after`, YOLOX-S); results go in `analysis.json` beside the photos: per photo a label, score, box and tier, and per pass whether it ran or was skipped and why. A missing model file or engine skips a pass and never stops the scan. The Mac pass `remote` is recorded as not built. The robot's picture of the room is saved as `world.json` and updated as each result arrives: objects merged across overlapping photos and passes, each with a direction (from the photo's measured pose and the box), a score, and whether the strongest pass that ran confirmed it, plus coverage and status (`scanning`, `complete`, `partial`). The previous picture is kept as stale until the new scan completes. Defaults to be recalibrated on the robot |
| `room_view` | No arguments; read-only. Describes `world.json` in plain anonymous words: objects, rough direction relative to the robot's front, how sure, how old the information is (stale after `STALE_AFTER_S`) and how much of the room was covered. Says so when there is no scan, the scan is unfinished or the picture is old, and offers to scan again. No names, no photos. Tick it in the personality with `room_scan` |
| `sleep` | No arguments; starts the wake watcher, then Pollen's sleep (pose, app stops, motors off); stays awake if the watcher cannot start. Replaces `go_to_sleep` |
| `approve_site` | `site`; adds the exact refused site to `approved_sites.txt` only if the transcript shows the robot named it and the user said or typed yes; permanent |
| `read_article` | `number` from the last search/news list, `link` from the last page read, or `url`; fetches the page directly, text via BeautifulSoup (max 8000 characters) plus its links in page order; local and private addresses refused with a reason |

`stay_silent` is retired. Stock search/weather, camera, sweep and move tools remain upstream;
`sweep_look` queues motion only, `camera` captures one image, and `move_head` has fixed presets.
These do not implement the roadmap's scan or precise-alignment backlog.

## No relay

The former relay (`conversation_runtime.py`) was retired on 2026-10-16 and is kept under `archive/relay/`.
The app connects directly to Pollen's backend ("deployed" mode). Mute uses the daemon volume API.
`voice_look` runs standalone. Its own description asks the model to turn it on at the start of every
conversation, whatever the personality, if the tool is ticked for that personality.

## Settings and source layout

`REACHY_TOOLS_STATE_DIR` defaults to `~/.config/reachy_tools/`. `location.json` stores place,
region, country, country_code, timezone, latitude/longitude and provisional status. `speaker_restore.json`
stores the level unmute restores. `last_results.json` holds the last numbered search/news list; `last_page_links.json` the links of the last page read. `approved_sites.txt` lists the sites `read_article`
may read, one per line (seeded with bbc.co.uk, bbc.com, theguardian.com, reuters.com, apnews.com,
metoffice.gov.uk); delete a line to remove a site.
None of these belong in Git.

### Where scan and analysis configuration lives (agreed 2026-10-22; being built)

| What | Where |
|---|---|
| Rules: the tool-reply allow-list, the private-address check for a vision LLM, no network in analysis code | In code (`robot_tools/reachy_lib/`), under tests. Not a settings file, so it cannot be changed by accident |
| Defaults (`ScanSettings`, the default model table) | In code, so a scan works with nothing configured |
| Values to tune (overlap, crop, cut-offs, which model runs in which tier, threads) and the model table | `~/.config/reachy_tools/scan.json`, read fresh at every scan (no restart); `REACHY_SCAN_*` environment variables override it |
| Model files | `REACHY_TOOLS_MODELS_DIR`, outside the repo |
| What a scan actually used | That scan's own `scan.json` and `analysis.json` |

Order of precedence: code default, then `scan.json`, then an environment variable if set.

`scan.json` keys (the `REACHY_SCAN_*` names without the prefix, lower case): `overlap`, `hfov_deg`,
`body_yaw_min_deg`, `body_yaw_max_deg`, `head_yaw_min_deg`, `head_yaw_max_deg`, `pitch_deg`, `settle_s`, `crop`,
`confidence`, `nms_iou`, `analysis_threads`, `stale_after_s`, `merge_tolerance_deg`, `merge_overlap`; and two tables,
`models` and `tiers`. The settings code is `reachy_lib/scan_settings.py`, shared by `room_scan` and `room_view`. An unknown key, bad JSON or a bad value is refused with a message naming it.
`crop` is the central fraction of each photo's width kept (default 1, the whole photo); the overlap applies to the
trimmed field, so crop 0.8 gives 8 stops, 0.7 gives 9, 0.6 gives 10 (instead of 7).

`models` adds a model or changes fields of a known one (`file`, `size`, `family`, `pad`); the defaults are
`yolox_nano` (416), `yolox_s` (640), `yolox_m` (640) and `nanodet` (416). `tiers` says which model runs in `now`
(during the scan), `after` (on the robot after it) and `remote` (on the Mac); `null` switches a pass off.
Model files live in `REACHY_TOOLS_MODELS_DIR` (default `~/.local/share/reachy-tools/models`), and a file name may not
contain a path, so a setting cannot point the scan at an arbitrary file. A mistake in the `models` or `tiers` tables
is recorded in `analysis.json` and does not stop the scan. Analysis needs ONNX Runtime and OpenCV in the app's
environment (both are in the sim's; the robot's is not yet checked) and the model files in that folder.

### Tool replies are checked (built 2026-10-22)

Every tool's `__call__` carries `@checked` (`reachy_lib/replies.py`), so its reply is vetted before the LLM sees it:
plain data only (text, numbers, true/false, nothing, lists and dictionaries with text keys); text that looks like
encoded image data or names a private folder (photos, scans, keys) is refused; so is a key containing `b64`, and
any reply over 100,000 characters. A refusal names the rule, never the data. A new tool without `@checked` fails
`tests/unit/test_every_tool_checks_its_reply.py`. If a legitimate reply is refused, fix the tool, not the check.

## API keys

Tools get a key with `reachy_lib.keys.get_key(name)`, the same call on the robot and the Mac. It tries, in order:

| Source | Where |
|---|---|
| Environment variable `<NAME>_API_KEY` | e.g. `TAVILY_API_KEY` in `~/.env` for the sim; also used by tests. Plain text, so keep the file `chmod 600` |
| Robot (Linux): `systemd-creds` | `~/.config/reachy_tools/keys/<name>.cred` (`REACHY_TOOLS_KEYS_DIR` overrides it, for tests), shared by the development and live tools. Encrypted with `systemd-creds --user`: unreadable off the robot or by another user, nothing decrypted to disk |
| Mac: login Keychain | Service `reachy-tools`, account = key name (`REACHY_TOOLS_KEYCHAIN_SERVICE` overrides it, for tests). The first read may ask once to allow access |
| Windows: Credential Manager | Generic credential `reachy-tools/<name>` (same override for the prefix), through `ctypes`. **Not yet tested on Windows** |

Keys are read for each request and kept in memory only. Accepted limit on the robot: anything running as `pollen` can
decrypt it. `.claude/settings.json` denies Claude reading the files or running the decrypt. Only the Tavily key
(`tavily`) is used so far.

Manage keys with `scripts/keys.sh` from the project folder, on the robot or the Mac, or `scripts\keys.bat` on
Windows; no sudo needed. Both just run `robot_tools/reachy_lib/keys.py` with the project `.venv`, where the logic
lives once:

| Task | Command |
|---|---|
| Add or replace a key (paste it at the hidden prompt) | `scripts/keys.sh add tavily` |
| Check a key is stored and readable (never shown) | `scripts/keys.sh check tavily` |
| List stored key names (robot only: the Keychain cannot be listed this way) | `scripts/keys.sh list` |
| Delete a key | `scripts/keys.sh remove tavily` |

On a Mac a key may only use letters, digits and `. _ ~ + / = : -`; anything else is refused, not stored.

`robot_tools/` contains the tool files and package marker, plus `reachy_lib/`: shared code for the tools (smooth
moves, pose capture), not a tool. The app loads only top-level `*.py` files as tools, so a subfolder is ignored;
a tool imports it after adding its own folder to `sys.path` (see `reachy_lib/__init__.py`). The patch helpers were moved to
`archive/retired_patches/`; installation/deployment write paths remain disabled. The old Mac-specific
`deploy_runtime.py` was deleted. The unused historical `SpeechState` code remains in speech_control.py
for regression tests; it is not the live mute implementation.

Old staged scripts under `/home/pollen/reachy_tools_deploy/` were not changed and must not be run.
Installed package files are not deployment targets. Tools run in the dashboard app interpreter, so they
use the standard library only.
