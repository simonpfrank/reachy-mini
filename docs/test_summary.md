# Test Summary

Run: `.venv/bin/python -m pytest` (78 tests: 75 unit, 3 integration on the real robot)

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

### robot_tools/stay_silent.py (`tests/unit/test_stay_silent_tool.py`; stand-in Tool base)
- The tool is named `stay_silent` and has `needs_response = False`, so the app does not prompt a spoken reply.
- It returns status "silent" with the given reason, defaulting to "not addressed".

## Integration tests (real robot, no mocks; skip if unreachable; `REACHY_HOST` overrides 192.168.0.15)

### `tests/integration/test_server_robot.py`
- The real hub connects to the real robot within 8 s (state, fast IMU and log feeds), serves its motor mode, and connects to the app when it is running.

### `tests/integration/test_sources_robot.py`
- Daemon state stream (`/api/state/ws/full`) gives 3 robot states with a valid motor mode.
- Conversation app `/rpc` stream gives `conversation.*` events (needs the app running).
