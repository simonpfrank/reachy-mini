# Verification record

Dated results, not a feature specification. Requirements/status: [roadmap](roadmap.md).
No new robot tests were run during documentation consolidation.

## Latest recorded recovery — 2026-10-16

- 165 maintained unit tests passed after speaker mute replaced response blocking; experimental tracker excluded.
- Changed-file Ruff and `git diff --check` passed for that batch.
- Model invoked speech_control for mute/unmute and today while muted; telemetry continued receiving events.
  ALSA numeric level stayed at 100%, with playback switch off/on. Suppression counters stayed zero.
- Voice following reconnected after the relay/app restart. Simon confirmed speech and mute work.
- Initial setup's earlier 170-test result predates the change in tested policy; it is not the current suite count.
- After the archive relocation and 1.1.1 lock: 165 maintained unit tests passed (2026-10-16).

## Commands

```bash
# Whole suite: unit and integration. Nothing is excluded or skipped.
.venv/bin/python -m pytest -q
```

`tests/integration/` runs for real against the robot daemon (8000) and conversation app (7860), with no mocks.
If either is down, those tests fail and say what to start.

## Coverage map

| Area | Evidence location |
|---|---|
| RPC/state parsing, feeds, logs, store, IMU, server, typed input | `tests/unit/test_events.py`, `test_sources.py`, `test_logs.py`, `test_store.py`, `test_imu.py`, `test_server.py`, `test_utterances.py` |
| Context/control adapters | `tests/unit/test_today_tool.py`, `test_phase1_tools.py` |
| Voice following | `tests/unit/test_voice_look_tool.py` |
| Public tools (weather, news, web search, read_article, keys) | `tests/unit/test_weather_tool.py`, `test_public_tools.py`, `test_read_article.py` |
| Site approval (user's yes from the transcript; model cannot approve alone) | `tests/unit/test_approve_site.py`, `tests/integration/test_approval_robot.py` |
| Private photo (pose, owner-only, latest only; no levelling) | `tests/unit/test_photo_tool.py`; no integration test yet: the camera is held by the running app |
| Room scan: planner and settings, one-move timeline, runner, tool (unit only; not yet run in the app or on the robot) | `tests/unit/test_room_scan_plan.py`, `test_room_scan_run.py` |
| Shared tool library: pose capture, smooth moves, private storage | `tests/unit/test_reachy_lib_motion.py`, `test_reachy_lib_storage.py` |
| Hub settings (`.env`) | `tests/unit/test_main.py` |
| Sleep and wake watcher | `tests/unit/test_sleep_tool.py`, `test_wake_watcher.py`, `tests/integration/test_wake_robot.py` |
| Retired patch refusal/source transforms | `tests/unit/test_patch_retirement.py`, `test_voice_look_install.py`; helpers now under `archive/retired_patches/` |
| Real robot daemon, app and hub | `tests/integration/test_sources_robot.py`, `test_server_robot.py`, `test_approval_robot.py` |
| Recorded robot samples | `tests/data/` |

The experimental voice tracker and its tests were retired to `archive/tracker/` on 2026-10-17.

## Historical results

| Date | Result | Limitation |
|---|---|---|
| 2026-10-13 | Baseline 95 tests (92 unit, 3 robot integration) | Older source and app |
| 2026-10-15 | Lifecycle: 110 unit passed; typed input: 124 passed; 14 new typed-input tests | Six pre-existing experimental tracker failures; lifecycle used patched app 1.0.1 |
| 2026-10-15 | Typed UI desktop/mobile checks and real reply “Text input works.” | Dated delivery evidence |
| 2026-10-15 | Phase 1: 103 focused passed; 804 sampled yaw paths; quiet/reload/restart live check | Patched app 1.0.1; response/tool blocking is no longer the intended behaviour |
| 2026-10-15 | Retirement audit: 113 focused passed, Ruff and strict mypy | Established refusal/integrity, not runtime repair |
| 2026-10-16 | Setup: 170 maintained passed, real-app tool loading, isolated 8787 relay health | Before speaker-mute correction |

The 1.1.0 update removed unsupported hooks; those historical patched-app results did not prove update survival.
The subsequent separate relay repair is the latest recovery evidence above.
