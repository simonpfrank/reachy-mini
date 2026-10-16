# Test Summary

Current correction (2026-10-15): the earlier Phase 1 live checks below tested patched app 1.0.1. Update to 1.1.0
removed those unsupported hooks and broke persistent quiet and voice following. Prototype tests do not prove
stock-app compatibility or current runtime behavior. Patch deployment is retired locally; see
[update-compatibility.md](update-compatibility.md). No robot changes or new live acceptance checks in this audit.

Historical baseline run: `.venv/bin/python -m pytest` (95 tests: 92 unit, 3 integration on the real robot).
Later batches below supersede this count; it is not the current full-suite result.

## Update-compatibility audit verification (2026-10-15)

- 113 focused local tests passed: retired installer/deployer entry points, historical voice/quiet logic,
  ordinary today/location tools, typed input and hub regressions. No robot connection or motor writes.
- Refusal tests exercise imported APIs and standalone scripts, including absent app paths, existing backups,
  already-patched source, a meaningless force flag and unchanged files. Read-only checks explicitly report
  retirement and denied deployment; installer writes reject before source reads or backup creation.
- Ruff passed for the changed Python implementation/tests; strict mypy passed for the five changed tool/installer/
  deployer source files. One existing Starlette/AnyIO deprecation warning appeared in pytest.
- The known experimental tracker failures were not rerun; they are outside this audit. No new live acceptance
  was performed. These results establish local deployment retirement, not repaired quiet or voice following.
- Earlier staged robot installers remain unchanged. Local safeguards do not disable those copies.

## Unit tests

### reachy_hub/events.py (`tests/unit/test_events.py`)
- An app JSON-RPC notification becomes an `Event` with source "app", kind = method, data = params.
- A JSON-RPC reply (has `id`, no `method`) is not an event.
- A notification without params gets empty data.
- A non-dict message is ignored.
- A real daemon `/api/state/full` sample (`tests/data/state_full.json`) gives motor mode, head pitch in degrees, speech flag and IMU temperature.
- The IMU sample gives acceleration magnitude, tilt from upright and rotation speed (°/s).
- Tilt direction is where the head leans, in sensor axes (lean toward +y reads 90°).
- A level, still head reads tilt 0, rotation 0, acceleration 9.81.
- Sound direction converts to degrees from straight ahead: left 90, front 0, right -90.
- Missing head pose, sound direction and IMU give None.

### reachy_hub/sources.py (`tests/unit/test_sources.py`, fake connection)
- Decoded JSON messages are delivered in order; status goes "connected" then "disconnected: closed".
- A non-JSON message is skipped.
- A refused connection is reported as "disconnected: ConnectionRefusedError" and retried.
- Text mode delivers lines and skips empty keep-alives.
- Returns at once, without connecting, when already stopped.

### reachy_hub/logs.py (`tests/unit/test_logs.py`, real log lines in `tests/data/daemon_log_sample.txt`)
- "Tool call received" gives `tool.call` with tool name, parsed args and the app's millisecond timestamp.
- A background tool start gives `tool.start` once (the duplicate line from another module is ignored).
- A daemon ERROR line gives `log.error` with logger and message.
- An app error uses the app's own level, not the runner wrapper's WARNING.
- A session start gives `app.session` with profile and voice.
- Routine relay and access lines, and non-journal text, are ignored.
- A cancelled tool gives `tool.cancelled`.
- "executed successfully" gives `tool.done` with tool name and call id.
- A tool result (`role=assistant content={...}`) gives `tool.result` with status, a 300-char preview, and the error hidden inside the text (real case: search "status ok" but "web search failed").
- "failed with error" gives `tool.failed` with tool, id and error.
- A plain chat line is not a tool result.
- "Added camera image to conversation jpeg_bytes=N" gives `camera.image` with bytes and KB (a photo sent to the AI).
- A long tool result the app cut short (~700 chars, ends with "…") still gives `tool.result`: tool, status, `truncated`, and a preview starting at the content.

### reachy_hub/store.py (`tests/unit/test_store.py`)
- Sound-level events update the live you/robot levels and do not enter the event list.
- Other app events go to the event list.
- A JSON-RPC reply is ignored.
- Robot state is replaced by the latest payload.
- A feed's link status is logged only when it changes.
- The event list is capped (oldest dropped).
- An IMU tap becomes a "robot" `imu.tap` event with strength and direction.
- The latest IMU reading is kept live; the last tap is kept with time, strength and direction.
- A message without IMU data is ignored.
- Log lines older than the store's start (the log replays on connect) are ignored.
- Log events are kept and duplicate lines skipped.
- `tool.done` gets `seconds` from its matching `tool.call` (by call id): real search took 9.23 s.
- `tool.done` with no known call has no duration.
- `tool_result_ready` (app event) adds no extra events.
- Streaming chunks (`*_delta` activity) become one `stream.started` and one `stream.ended` with chunks and seconds.
- Partial transcripts collapse the same way; `stream.ended` keeps the last partial text; the final transcript is kept as is.
- A different stream ends the previous one.
- User speech start to stop gives `speech.heard` with seconds spoken and the mic's peak level (what was fed to speech-to-text).
- Speech stopped without a start gives no summary.
- The snapshot is JSON-ready with robot, levels, links, IMU and numbered events.

### reachy_hub/imu.py (`tests/unit/test_imu.py`)
- A real 30 s recording with 3 hard taps (`tests/data/imu_three_taps.json`) gives exactly 3 taps, at ~7, 15 and 21 s.
- A still head with small noise gives no taps.
- Spikes within half a second count as one tap.
- No detection until enough readings define "normal".
- Tap direction is the sideways push in sensor axes (+x = 0°, +y = 90°), so sideways pushes are detected.

### reachy_hub/server.py (`tests/unit/test_server.py`, FastAPI test client, no feeds)
- `/api/snapshot` returns the store's contents.
- `/` serves the dashboard page.
- With no robot host, no feeds are started.

### robot_tools/today.py (`tests/unit/test_today_tool.py`; stand-in for the app's Tool base, which only exists on the robot)
- Spoken British time for 10 cases: "twenty past seven in the evening", "seven o'clock in the morning", "midday", "midnight", "quarter to four in the afternoon", "seven minutes past nine in the morning", "twenty-five to eleven at night", "half past eleven in the morning", "ten to midnight", "two minutes to midday".
- Spoken date with ordinals: "Tuesday the thirteenth of October, twenty twenty-six" (also first, twenty-second, thirty-first).
- Payload: spoken sentence plus date, weekday, 24-hour time and time zone.
- The tool is named `today` and returns that payload.

### Retired `stay_silent`
- Removed with its obsolete tests in Phase 1. Persistent quiet/resume is covered below.

### reachy_hub/tracker.py (`tests/unit/test_tracker.py`; synthetic cases plus the real recording `motion_doa_frame.json`)
- Silence gives no decision; a 0.2 s burst (clap) is ignored; a source already in front (within 8 deg) gives none; wandering angles are not a steady source.
- A steady talker at 145 deg gives a right turn, capped at 35 deg (head-only reach), flagged clamped.
- A flickering source (speech flagged about a third of the time) at 77 deg still counts and gives a 13 deg left turn.
- The turn is relative to where the head already points.
- Cooldown: no second decision for 3 s, then allowed.
- A strict threshold (0.5) ignores the flickering background talker but still answers a steady voice.
- Real recording, loose rule: decisions toward both the video (about 77 deg) and the shouting (141-151 deg), all within the cap, 3 s apart. Strict rule (0.6): only the shouting.

### reachy_hub/track.py (`tests/unit/test_track.py`)
- A real daemon state sample becomes a sound sample (angle in degrees, speech flag) and the head's turn relative to the body.
- A state without a sound reading gives no angle.
- The move request turns the head relative to the body (heading = body + turn) and keeps the body still.
- Frame verdict: reading moving toward front after a turn = head-relative; unchanged = base-relative; source already near front = inconclusive.

## Integration tests (real robot, no mocks; skip if unreachable; `REACHY_HOST` overrides 192.168.0.15)

### `tests/integration/test_server_robot.py`
- The real hub connects to the real robot within 8 s (state, fast IMU and log feeds), serves its motor mode, and connects to the app when it is running.

### `tests/integration/test_sources_robot.py`
- Daemon state stream (`/api/state/ws/full`) gives 3 robot states with a valid motor mode.
- Conversation app `/rpc` stream gives `conversation.*` events (needs the app running).

## Voice-follow lifecycle repair (2026-10-15)

- 14 new tests pass: app-owned worker startup, concurrent enable, on/off after tool reload, disabled-state retention,
  stop during an in-flight microphone poll, shutdown after reload, refusal to overlap a stuck worker, and safe installer behavior.
- Full unit suite: 110 passed; the same 6 pre-existing failures remain in `test_tracker.py` (experimental tracker).
- Robot-side checks passed using the installed app's real movement manager and file loader with no motor writes.
- Deployed app logs show one worker surviving a registry reload, clean shutdown, and one worker on the next app launch.
- Camera face tracking is off; live Marvin tools include `voice_look` and exclude `head_tracking`.
- These checks establish lifecycle correctness. Accurate physical speaker-facing and behavior after gestures still need live testing.

## Telemetry typed utterances (2026-10-15)

- 14 new tests pass for forwarding, matching RPC acknowledgements amid notifications, rejection, timeout without
  retry, unavailable app, malformed replies, request validation, and delivery/error events in telemetry.
- 43 focused hub tests pass; lint and source type checks pass. Full unit suite: 124 passed, same 6 existing
  experimental tracker failures.
- Chrome checks passed for equal-width input above filter, pending-send protection, error text retention and
  successful clearing. Tested desktop and phone-emulation layout.
- Live test: user text accepted via the hub; `utterance.sent` logged; robot replied "Text input works." and its
  final transcript appeared in telemetry. Local hub restarted and left running on port 8710.

## Public tools Phase 1 (2026-10-15)

- Combined relevant batch: 103 passed across phase1 tools, voice lifetime/planning/evidence, installers,
  today and typed-input/hub regressions. No full rerun of the known six experimental tracker failures.
- Covers explicit quiet/resume recognition, ordinary-input suppression, persistent and unreadable state,
  failed persistence remaining quiet, blocked old audio after resume, preserved transcription/response cleanup,
  suppressed function calls, shared location defaults/overrides and invalid coordinates.
- Voice checks cover circular bearings, useful head/body targets, scaled duration, saturation suppression,
  sustained evidence, evidence discarded during gestures, and pauses during robot speech/recent playback.
- Lint passes for all new/changed Phase 1 Python files. Strict type checks pass for the five implementation files
  (location, speech control, voice following and the two patch installers).
- Robot-side runtime batch loads the real patched app classes without hardware: 804 head/body samples within
  limits, held heading after a finite gesture, speaking state with face tracking off, actual final playback gate,
  pending response suppression, tool gating, restart persistence, resume and normal text injection.
- Combined live check: all requested tools available; mic unmuted; quiet requests and normal text produce zero
  assistant audio events; quiet survives tool save/reload and a full app restart; explicit resume succeeds.
  The subsequent instruction called both location and today, producing the spoken Cobham/current-date answer
  with seven observed assistant audio events.
- Live harness retries temporary HTTP 403 while `/rpc` mounts during app startup. Initial run stopped at that
  readiness error; no app code change was needed. Corrected combined live check passed.
- Logs show one current follower and real head/body turns; physical speaker-facing accuracy still needs a real
  speaking session. TV rejection and automatic face following are deferred.
