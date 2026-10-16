## Latest baseline recovery (2026-10-15)
Disabled broken voice_look/speech_control in default and Marvin through supported profile_tools RPC, preserving
all other selections and backing up first. Backend connected; typed test final transcript "Conversation is working."
No installed app code edits. Audible playback not verified. Quiet/following remain unavailable, now disabled.

## Current focus: update-compatibility audit (2026-10-15)
**Status:** Local audit/retirement complete and verified. Runtime repair remains outstanding.
**Completed:** Local refusal of app-patch installation/deployment, corrected current-status docs and 113 focused
local tests; Ruff and strict mypy passed. No robot changes or new live acceptance.
**Confirmed:** Installed app is now 1.1.0. All 52 installed Python sources match distribution RECORD hashes.
The update removed our unsupported app patches, breaking quiet control and voice following despite enabled tools.
**Next step:** Restore affected features through supported interfaces and verify live; no compliant implementation
exists yet. Both local installer write modes now refuse before filesystem access, and the local deployer always
exits without side effects. Old robot-staged copies remain untouched and must not run. No app edits/restarts or
repair deployment during this continuation. Audit evidence and missing interfaces: `docs/update-compatibility.md`.
**Phase 2:** Authorised, but only its plan exists; service/tool implementation and key setup are not built yet.

## Earlier focus (2026-10-15)
**Status:** Phase 1 implementation in progress; Simon explicitly requested building now.
**Working on:** `docs/public-tools.md` and roadmap revision. Defer automatic face following while voice direction is used in daily life. Keep today, retire stay_silent, add location and stop/resume speech, improve useful head/body voice reach, implement requested scene scans locally, reuse harness search/extraction, add location-aware weather and news story follow-up.
**Next step:** Phase 1: context/control and head/body following fixes. Use provisional editable Cobham, Surrey, UK from existing context. Quiet behavior is confirmed: “shut up” stops audio and stays quiet until explicitly told it can speak again; keep listening for resume. Phase 2: search/weather/news and credentials. Phase 3: local look-around/scene memory. Batch verification and live checks by phase, with no routine per-tool or per-phase approval loop.
**Delivered this session:** Voice-follow singleton/lifecycle repair deployed; camera head tracking disabled. Telemetry typed input/Send is live, tested through a real robot reply. Full unit suite: 124 passed, same 6 pre-existing experimental tracker failures. Home/media integrations remain recorded for later.

## Earlier Session (2026-10-13)
**Status:** In Progress (good stopping point; committed)
**Working on:** Telemetry hub/dashboard (`python -m reachy_hub`, http://localhost:8710), Marvin persona (`profiles/marvin/profile.md`), on-device tools (`robot_tools/`: `today`, `stay_silent`, live on the robot).
**Next step:** Pick one: (a) dashboard held voice-direction reading, start of roadmap 3a; (b) our web search + weather (roadmap step 4, private HF Space per `docs/tools.md`); (c) finish step 2: Marvin's tool list and camera decision (camera off until step 6?). Dashboard fix list in roadmap side tracks (idle labels, no false taps during self-motion, move finished, latency events, quiet the runner's INFO-as-WARNING lines).
**Notes:**
- Env done (`.venv` -> `~/.venvs/reachy_mini_env`, reachy-mini installed). Skills in `.claude/skills/`. Old unused `~/venvs/reachy_mini_env` awaiting deletion by user.
- Robot (Wireless, 192.168.0.15) up, daemon healthy (49 Hz, 0 errors). SSH works with `~/.ssh/reachy_ed25519`. Conversation app already installed on robot.
- Testbench (`reachy_mini_testbench`) installed on robot (not running). Conversation app is the running app; one robot app at a time.
- RESOLVED (cause unknown): Chrome on the Mac could not open `http://192.168.0.15:8042` (robot saw no connection; curl from Mac worked); user says it now works. Checked before it cleared: no proxy/VPN, no Chrome policies, logs showed nothing. Unproven theory: macOS Local Network permission for Chrome. SSH tunnel was tried and removed. If it recurs, note what changed.
- Found via the hub (2026-10-13): Pollen's hosted search tool (`pollen-robotics/reachy-mini-search-tool`) returns "web search failed" inside a `status: ok` result; the robot then says it failed. Not our bug. Also an app install of `reachy_mini_greetings` failed at 11:40.
- Persona (roadmap step 2) in progress: master copy `profiles/marvin/profile.md`, live on the robot (pushed 2026-10-13 evening): voice Uncle_Fu, Marvin as seasoning with an off-switch for serious moments, speaking rules. Deploy = copy to robot `user_personalities/Marvin/profile.md` + `personalities.apply` (persist, force). Speech language already English: robot runs conversation app 1.0.1, default `en` (no `language.*` RPC in this version).
- Robot tools live (2026-10-13): `today`, `stay_silent` in `/home/pollen/reachy_tools/`, enabled by `/venvs/.env` (one line). Undo: delete both. How to deploy: `docs/tools.md`.
- Voice tracker v0 built (2026-10-14), roadmap 3a: `reachy_hub/tracker.py` (pure logic) + `python -m reachy_hub.track` (dry run by default; `--live` moves the head, head-only, capped at 35 deg, refuses while an app runs). First live turn also tests head-relative vs base-relative. Design: `docs/voice-tracking.md`. Not yet run on the robot.
- Back burner, soon: sound-card firmware 2.1.2 -> 2.1.4 for louder speaker (details in roadmap side tracks).
- A process on the Mac holds 127.0.0.1:8042 and :8000 (user says it is the brain). Pick a different port range for our brain.

| Component | Unit Tests | Code | Integration Tests | Unit Results | Integration Results |
|---|---|---|---|---|---|
| Architecture doc | ⏭️ N/A | 🟡 In Progress | ⏭️ N/A | ⏭️ N/A | ⏭️ N/A |
| Telemetry design (`docs/telemetry-and-hooks.md`) | ⏭️ N/A | ✅ Done | ⏭️ N/A | ⏭️ N/A | ⏭️ N/A |
| reachy_hub/events.py | ✅ Done | ✅ Done | ❌ Not Done | ✅ Pass (7) | ⏭️ N/A |
| reachy_hub/sources.py (WebSocket reader: app /rpc, daemon state) | ✅ Done | ✅ Done | ✅ Done | ✅ Pass (4) | ✅ Pass (2, real robot) |
| reachy_hub/logs.py (daemon log feed: tool calls/starts/cancels, session, warnings/errors) | ✅ Done | ✅ Done | ✅ Done | ✅ Pass (7) | ✅ Pass (log feed connects) |
| reachy_hub daemon status (loop rate/errors), SSH stats (WiFi/CPU/temp) | ❌ Not Done | ❌ Not Done | ❌ Not Done | ❌ Not Done | ❌ Not Done |
| reachy_hub/store.py | ✅ Done | ✅ Done | ✅ Done | ✅ Pass (9) | ✅ Pass (via server test) |
| reachy_hub/imu.py (tap detector, fast IMU feed) | ✅ Done | ✅ Done | ✅ Done | ✅ Pass (4, incl. real recording) | ✅ Pass (IMU feed connects) |
| reachy_hub/server.py + static/index.html + `python -m reachy_hub` | ✅ Done | ✅ Done | ✅ Done | ✅ Pass (3) | ✅ Pass (1, real robot) |
| Latency spike (roadmap step 6) | ❌ Not Done | ❌ Not Done | ❌ Not Done | ❌ Not Done | ❌ Not Done |
| ask_brain tool | ❌ Not Done | ❌ Not Done | ❌ Not Done | ❌ Not Done | ❌ Not Done |
