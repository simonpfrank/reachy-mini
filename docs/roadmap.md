# Roadmap

One new thing per step. Status: ✅ done, 🟡 in progress, ❌ not started. Architecture: [architecture](architecture.md). Reference links: [ideas](ideas.md). Tool reference: [tools](tools.md).

**Status, 2026-10-16:** conversation and speaker mute work (confirmed by Simon); voice following is usable,
with accuracy refinement deferred. Phase 2 is redesigned as on-robot public tools; not built. Earlier patched-app results are historical.
Functional requirements live only here; phase documents describe implementation against the IDs below.

| # | Step | Done when | Data risk | Status |
|---|---|---|---|---|
| 0 | Robot alive from the Mac | Daemon healthy, SSH works, sound direction readable, robot wakes | None | ✅ (wake needs motors enabled first) |
| 0b | Find the silent-TTS cause | Deferred until the turn timeline exists. Then: reproduce in the far room with WiFi/router-ping/CPU logged on the robot (a 1 Hz on-robot logger worked; log on the robot, not over SSH) and match failure times | None | ⏸ |
| 1 | Stock conversation app, hosted voice | App talks and hears (transcripts, tool calls, replies seen on the dashboard 2026-10-13); starting the app wakes the robot (motors on) by itself. Not covered: waking by voice from sleep (stock app has no wake word; ours, later) | Audio goes to HF | ✅ (except wake word from sleep) |
| 3a | Voice tracking (turn to sound). Measurements: [motion evidence](architecture.md#motion-evidence) | Turns toward Simon speaking from left or right within about a second, using the daemon's direction reading. Does not chase the TV over a 5-minute test: only turn on detected speech, steady direction (~1 s), cooldown, ignore the TV's fixed direction. Front/back: DoA covers a half-circle only (0 left, 90° front or back, 180° right); fine in conversation (person in front); if needed, resolve by turning and re-listening. Dashboard first: held 'last voice heard from X°, n s ago' + recent range | None | ❌ |
| 3b | Face following (deferred 2026-10-15) | Live with voice-direction following for a while first; keep automatic camera head tracking disabled. Face/person detection during requested look-around scans is still in scope | None: faces stay on Mac/LAN | ⏸ |
| 4 | Our public tools | Today/location use ordinary external tools; stay_silent retired. Speaker mute and voice following restored. Search/weather/news and local look-around remain; phase assignments below | Public queries to providers; faces stay on Mac/LAN; service-side keys | 🟡 (control restored; phases 2–3 unbuilt) |
| 5 | Private brain | `ask_brain` (on the robot) calls agent-harness on the Mac; persona says "checking", timeout handled; serious mode: automatic for anything from `ask_brain` (plain, exact read-back, confirm changes) and on request ("serious mode" until "back to normal"); start as a rule in Marvin's profile, switch to a separate plain persona via `personalities.apply` only if the rule proves unreliable (links to step 7 modes); safe slice first: reminders and calendar (today's one thing, what's due, add reminder with approval) | Reminder titles reach HF until step 6. No email/messages | ❌ |
| 6 | Local backend on the Mac | speech-to-speech on Mac; median end-of-speech to first audio <= 1.5 s good, <= 2.5 s acceptable; Gemma vs Qwen3.5-4B. Gate for email and messages. | None leaves Mac/LAN | ❌ |
| 7 | Modes and brain-off | General/personal switch; sensible behaviour when the Mac is off | None | ❌ |
| 8 | Our voice | Parakeet STT and Marvin TTS plugged in as HTTP endpoints | None | ❌ |
| 9 | Voice ID gating, then face ID | Some tools only for Simon's voice; stops replying to the TV (seen 2026-10-13: Marvin answered the TV and joined in a game; profile rule is only a partial fix, wake word is the other route); known faces recognised locally | Faces stay local | ❌ |
| 10 | Later, as wanted | Siri capture, always-on node, AI Camera, Echo (write-only), TV/noise handling | | ❌ |

## Cross-cutting constraints

- Extend the official app through supported interfaces: no fork, installed-package edits, runtime monkey-patching,
  import-time workers, garbage-collector discovery or competing motor writers.
- Private email/messages/finances/faces stay on the Mac/LAN. The older step-5 reminder-title exposure note below
  records an unresolved privacy trade-off, not approval to send private data to a hosted backend.
- Only one app motion owner; no servo EEPROM/reflash changes for pose limits. Public-info credentials are scoped
  as specified in P2-5. Features surviving on disk after an update do not establish runtime compatibility.

## Phase assignments

| Phase | Requirement IDs | State | Implementation plan |
|---|---|---|---|
| 1: context and control | C1–C4 | Delivered; following accuracy accepted for now | Current implementation: [tools](tools.md) |
| 2: public information | P2-1–P2-6 | Planned 2026-10-16 (on-robot redesign); not built | [phase2.md](phase2.md) |
| Future phases | Backlog below | Not scheduled; select items before writing another phase plan | None |

## Delivered context and control

- **C1 — Today:** retain the date/time tool and use current dates for time-sensitive queries.
- **C2 — Location:** one editable, external record shared by weather/search/news: place, region, country,
  paired town-level coordinates, timezone, source and update time. Cobham, Surrey, UK is provisional;
  no guessed street address/GPS/IP location. Per-request place overrides do not change home location.
- **C3 — Speaker mute:** natural-language intent calls speech_control; no exact phrase list. Mute sets the speaker
  volume to 0 through the daemon volume API and remembers the level; unmute restores it. Any volume change
  (dashboard slider, volume tool) also restores sound. No relay or second mute control. Model replies, tool calls
  and telemetry continue while muted; do not acknowledge mute aloud. Voice following is independent.
- **C4 — Voice following:** one app-owned worker, automatic startup, explicit on/off and cleanup across reloads.
  Use the app's single motion owner; retain facing through breathing/gestures. Circular bearings, safe clamping,
  scaled smooth turns, saturation suppression and fresh sustained/dominant speech evidence; pause during robot
  output/motion. Accuracy tuning is deferred. Automatic face following remains off.

## Phase 2 requirements

Public tools only, run on the robot. Motto: robust but simple. No private data is in scope.

- **P2-1 — Search:** `web_search` calls Tavily directly from the robot. Return title, URL, publication date
  where given and snippet for each result; explicit provider failures. Use C1 so queries carry the right date.
- **P2-2 — Read:** `read_article` gets readable page text through Tavily Extract; the robot does not fetch
  article pages itself. Text is bounded, returned as untrusted page content (never instructions) and states
  when it is partial or unavailable.
- **P2-3 — Forecasts:** `weather` uses the UK Met Office model through Open-Meteo (no key) and C2; explicit place overrides, today/tomorrow,
  hourly, weekend and seven-day periods, units and provider update time; disambiguate places.
- **P2-4 — News:** `news` uses BBC RSS plus topic search. Headline numbering survives unrelated calls, tool
  reloads and reconnects; "the second one" refers to the presented list. Fetch the article (P2-2) before
  detailed answers; distinguish reporting from inference and state incomplete coverage.
- **P2-5 — Guardrails:** HTTPS to fixed provider endpoints only; timeouts and response-size caps; standard
  library only. Tavily key encrypted with `systemd-creds --user` and decrypted in memory per request, never
  in source, profiles, prompts or logs; accepted limit: anything running as `pollen` can decrypt it. Each
  search, read and failure is logged. Accepted risk: misuse while unattended.
- **P2-6 — Setup/replacement:** build and unit-test without a key; Simon adds the key with
  `scripts/keys.sh add tavily`. Keep the Pollen's built-in search/weather tools until replacements pass, then
  remove them from the tool selection.

## Backlog — not scheduled

Existing requests and ideas below remain in place. Additional detail consolidated from the removed plans:

### Scanning and positioning (future phase 3 candidates)

- **B-SCAN — Scan:** exclusive cancellable app-owned motion; pause following and restore its previous state.
  Overlapping safe body/head yaw poses and pitch bands; settle before each capture and retain actual pose/time.
  Detect objects, people and faces locally, anonymous until verified identity. Map detections to base-frame azimuth
  and elevation using calibration; merge overlap with uncertainty instead of double counting. Store labels, track
  IDs, angular extents, confidence, first/last seen and source observations. People expire faster than static objects.
  Reset/refresh on changed base placement, not ordinary head movement. Report unseen coverage; never invent objects
  or metric depth. Support scene questions and looking at referenced objects/people using age/confidence.
- **B-ALIGN — Manual positioning:** relative body-angle turns (including ninety degrees right) move the head with
  the body; explicit head yaw/pitch/centre commands have defined reference frames. Report requested versus achieved
  pose after clipping. Manual alignment pauses following and holds idle heading until explicit resume or another
  positioning request. A move is not a scan: observations require fresh settled frames.
- **B-PRESENCE — After scanning exists:** invalidate current presence immediately on wake and app/session startup;
  start a fresh observation generation. Keep long-term knowledge separate. Rebuild presence from new scans with
  timestamps/coverage; partial/failed scans leave uncertainty. Old transcripts, names or remembered visitors do
  not prove presence or speaker identity. Require a current introduction/verified evidence for names; ask if unsure.
  Update conversation context and discard results from pre-reset scans. Honour C3; no forced audible greeting.
  Acceptance: visitor A leaves during sleep; wake/restart must not assume A remains, including failed/partial scans.

### Further candidates

- **B-WEBGATE:** if public-tool misuse appears, or before private data shares a context with web content:
  links returned as IDs only, domain allowlist with redirect re-checks, approval tool whose grant is
  verified outside the model (relay transcript or hub button), and treatment of search queries as an
  outbound channel.

- **B-CONTROLS:** timers/alarms; consistent pause/resume/cancel/repeat/continue controls; capability/status help
  covering available tools, location, speaker/following state and service availability.
- **B-UX:** varied pre-recorded acknowledgement/wait/retry clips, one retry after unclear speech, first-run
  introduction and touch/knock reactions. Regenerate clips in the chosen final voice; check existing barge-in first:
  stop audio, cancel gesture and return to listening, including stop while already listening.
- **B-APPROVAL:** private-brain read-only actions need no confirmation; create/send/delete require spoken yes/no,
  read back outgoing messages and double-confirm deletion. Proactive greetings require face enrolment/verified
  identity; reactive wake and proactive interaction remain separate. Brain memory and scheduling stay brain-side.
- **B-AMBIENT:** optional meeting mode (no following/replies until ended), observer mode for two people, and explicit
  “that's the telly” direction marking. Candidate ambient map resets on base movement; no-face evidence alone is
  uncertain because TVs show faces. Later gating can use voice ID, wake-word direction or mic-array beam steering.
  Historical graded-glance/cooldown/unwind proposals need review; they are not the current follower specification.
- **B-WAKE:** wake word only for sleep, with one classifier thread, cooldown and microphone handoff to conversation;
  compare platform-specific models and gate background directions. Candidate offline reflex responses need no LLM.
- **B-BACKEND:** configurable brain endpoint/timeout and offline fallback; pluggable STT/LLM/TTS plus fallback chain.
  Validate end-of-turn detection and interrupted/streaming TTS service interfaces. Voice ID results need retesting
  with Reachy's microphone; end-to-end latency includes the LLM stage. Voice-swap relay is a candidate, not a plan.
- **B-DEPLOY:** reproducible backed-up installation with source/profile/settings rollback and health checks,
  independent companion dependencies, fixed tested revisions and a private source remote. The development lock is
  on 1.1.1 (2026-10-16); environment sync and the reviewed recovery commit remain.
- **B-HUB:** daemon loop rate/read-write timing/error counts, WiFi signal, CPU, temperature and throttling;
  optional A/V watch/listen panel; follower decisions/reasons, last-heard age/range, ambient direction map and
  lifted/moved detection with recorded DoA/head/body poses. Existing dashboard requests remain in Side tracks.
- **B-RESEARCH:** confirm hosted retention/model details, per-profile backend switching, Mac-side media routing,
  CM4 load/heat, raw microphone access, AI Camera compatibility/SDK support and alternative always-on hardware.

## Home and media tools to consider later

Requested 2026-10-15. Record for discussion only; no implementation or service connections now.

| Area | Requested capability |
|---|---|
| Philips Hue | Home lighting control |
| Harmony Hub | Audio/visual equipment control |
| Spotify | Music selection and playback |
| BBC Sounds | Radio, programmes and podcast playback |
| Other podcasts | Consider additional podcast sources |
| Audio output | Bluetooth playback to Simon's audio amplifier for the music/spoken-audio services |
| Favourites | Remember favourites; flesh this out gradually into a wider media tool over time |

## Side tracks (not blocking)
- **✅ Typed utterances in telemetry (2026-10-15).** Single-line input directly above the filter, same width, plus Send. Hub `/api/utterances` forwards to the app's `conversation.say`, which creates a user text turn and requests a model response. Send/Enter, pending-send protection and text retention on failure implemented. Delivery/errors and reactions use existing telemetry logs. Local server restarted; Chrome layout/submit checks passed; real robot reply "Text input works." observed in telemetry.
- **Web search is poor (seen 2026-10-13 via the hub).** Two faults: the AI searched "current movie list 2024" (doesn't know today's date) and Pollen's search Space returned "Electric current - Wikipedia"; it also sometimes returns "web search failed". Fix: Phase 2 replaces Pollen's search with `web_search` (P2-1).
- **Which models answer us? (parked 2026-10-13; Simon wants all the possibilities)**
  - Today (hosted): app names no model; Pollen's forwarder (`pollen-robotics-reachy-mini-realtime-url.hf.space`, supports A/B) sends sessions to a private HF Inference Endpoint (`hkbax8u9qwedr1uv.endpoints.huggingface.cloud`). Voice list = Qwen3-TTS CustomVoice presets, so very likely HF speech-to-speech (Silero VAD -> STT, likely Parakeet -> vision-capable LLM -> Qwen3-TTS). LLM unconfirmed. Hosted reply speed baseline: first audio ~1.45 s after transcript (app's own "Turn latency" log).
  - To confirm: run the app by hand on the robot with `--debug` (Pollen dev workflow) and read `session.created`.
  - Possibilities to compare: (a) Pollen hosted (free, unknown/changeable models, data to HF); (b) speech-to-speech on the Mac (choose each stage: STT Parakeet/Whisper; LLM Qwen3.5-4B in-process or Gemma via LM Studio; TTS Qwen3-TTS presets, Pocket TTS clone, OmniVoice clone, or our Marvin endpoint); (c) our own HF Inference Endpoint (paid, our choice of models, still off-Mac); (d) other realtime providers (OpenAI, Gemini) for general mode only, never personal data.
- **Vision: `look_around` (expanded 2026-10-15).** Replace the movement-only sweep with safe full body/head yaw coverage and pitch bands. Capture settled frames with actual poses, detect objects/people/faces locally and retain a timestamped angular scene model with lateral/vertical location. Account for unseen regions, moving people, uncertainty and changed base placement. Automatic face following stays deferred. Details: B-SCAN and B-ALIGN above.
- **Voice: choosing vs adding.** Hosted: 9 presets only (Aiden, Ryan, Dylan, Eric, Ono_Anna, Serena, Sohee, Uncle_Fu, Vivian), set via `voice =` in profile.md or the UI. Own voice needs our backend (step 6/8): Marvin endpoint (tts-chatterbox), Pocket TTS or OmniVoice clone.
- **Dashboard gap (seen 2026-10-14): when the app hears nothing there is no trace.** "Look up"/"look down" left no transcript, event or log line. Add: peak mic level over the last 10 s next to the sound bar, so a missed request shows whether the mic heard it. Firmware 2.1.4 adds +6 dB on the INPUT (changelog), which may help a quiet mic.
- **More dashboard additions:** `camera.image` event DONE 2026-10-13 (photo size, every picture sent to the AI); still to do: the picture itself (no daemon snapshot route: needs WebRTC from the Mac or a small robot-side helper), `latency` events from the app's "Turn latency" lines, move started/finished from the daemon (movement tools report "done" while still moving).
- **Idle behaviour (traced 2026-10-13).** After 180 s with no conversation (and again every 180 s while idle, only when the robot isn't moving) the app picks a random idle action, with no AI involved: stillness 60%, dance 16%, emotion 16%, move head 8% (`idle_policy.py`), only among tools the persona enables. An idle emotion is random from a curated pool of 47 that includes `dying1`, `rage1`, `scared1`, `sad1`. Timer is hard-coded (`IDLE_BEHAVIOR_THRESHOLD_S = 180.0`, `conversation_handler.py`); weights and pool are hard-coded too. Without forking, the only control is the persona's tool list (dropping `play_emotion` also stops the AI using emotions). Consider an upstream issue to make it configurable.
- **Dashboard fixes needed:** label idle actions (call id starts `idle-`) as "idle" in the event list; ignore IMU "taps" while the robot moves itself (emotions/dances/speech wobble triggered false taps at 2.0-3.2 m/s^2).
- **Weather tool is limited (2026-10-13 via the hub).** Pollen's tool answers "Cobham, GB" (drops the county) and only gives now + today's high/low: no hourly, no weekend. Temperature matched Open-Meteo within 0.5°C. Later: our own tool with home coordinates fixed and a real forecast (Open-Meteo, no key).
- **SOON: sound-card firmware 2.1.2 -> 2.1.4 (louder speaker).** Robot's "Reachy Mini Audio" (USB 38fb:1001) reports bcdDevice 0212 = 2.1.2. Pollen's 2.1.4 adds +6 dB (changelog says "audio input"; PR #1187 author measured louder playback) and fixes mic-after-USB-reset. File already on robot: `/venvs/mini_daemon/.../reachy_mini/assets/firmware/reachymini_ua_io16_lin_v2.1.4.bin` (standard 2-ch; the 6-ch file adds the 4 raw mics, revisit later). Flash: stop conversation app, `dfu-util -R -e -a 1 -D <file>` (may need sudo), restart daemon if needed. Measure before/after with the same test sound + dashboard robot sound bar. `REACHY_AUDIO_GAIN_DB` is from closed PR #1187, never released: setting it does nothing. ALSA speaker controls already at max (0 dB of -60..0).
- **Dashboard:** read `Domotick/reachy_web` (code and security) first; build only the gaps (sound level, direction, what the app is reacting to, WiFi/CPU log). Our own earlier work: `reachy-mini-aide/first_app` has a small control panel (state badge, wake/sleep, face on/off, speech-animation tests, debug toggle; ~130 lines of HTML/JS), built for the simulator. It is a control panel, not telemetry.
- **Mine from reachy-mini-aide (don't carry over wholesale):** `caldav_client.py` (calendar without macOS EventKit: the route to a brain on a Pi), pluggable sensor interface with simulator fakes (`sensors/interface.py`). Its `llm_tools/` (calendar, email, iMessage, reminders, memory) duplicate agent-harness: pick one brain, agent-harness.
- **Pose limits:** head knocks the body in some poses. Software clamp only, never servo EEPROM. Record the colliding poses first.
- **`reachy_web` reviewed (greps only, not a full audit):** covers daemon control, camera, 3D twin, moves, app store, log console, wifi/OTA, mic level meter. Does NOT show sound direction or "what is reacting". Can run on the Mac with `run.sh` (venv goes to `~/.venvs/reachy_web`, outside Documents), nothing installed on the robot, falls back to port 8043 if 8042 is taken. No shell=True/eval/exec found; no login (same as the daemon's own API, which is open on the LAN). Not yet run.
- **Turn timeline (needed, first custom dashboard panel):** one row per event with a turn id and timestamp: speech start/end, STT, LLM handoff and reply, tool call start/end (`ask_brain`), TTS first audio, interruption, head turn, wake/sleep. Merge sources instead of building a state machine: realtime backend events and its per-turn latency line, conversation-app log (daemon journal on the robot), agent-harness JSONL trace, daemon state (moves, direction, tracking). The aide only had a polled state badge (1 s) and a debug toggle; Reference links: [ideas](ideas.md).
- **Chrome and the robot:** it failed to open robot pages once, cause unknown. Note what changed if it recurs.

## Robot gotchas learned
- Motors start `disabled`: enable them, then wake (`/api/motors/set_mode/enabled`, then `/api/move/play/wake_up`).
- One robot app at a time: stop the testbench before starting the conversation app.
- Only matters once we run something on the Mac that listens (our dashboard, the `ask_brain` target): the Mac's 8000 and 8042 are already used by the brain, so pick other ports then. Robot ports don't clash with the Mac's.

# Unplanned futures
## Reachy led eyes
Domotick
- `Domotick/reachy_web` (`eyes.py`) already drives two community LED-eye hardware mods behind one `/eyes/*` API: **Reachy Eyes** (RP2350 on USB serial, brainwavecollective, no licence) and **reachy-mini-esp32-eyes** (ESP32 over WiFi at `rmeyes.local`, Apache-2.0). Colours, blink, startle effects. Needs the hardware; nothing in our stack yet.

# behviours ideas

Sound effects
https://www.trekcore.com/audio/ lots of sounds we should build a library to allow seelction of noise by category of event / actions

Gestures
simple nod, a side to side sway, or a head tilt roll. There is also a dizzy spin, a stumble and recover, headbanger combo, and interwoven spirals. I can do a sharp side tilt, side peekaboo, a yeah nod, an uh huh tilt, or a neck recoil. There is also a chin lead, groovy sway and roll, chicken peck, side glance flick, polyrhythm combo, grid snap, pendulum swing, and the jackson square.

 thinking, attentive, and uncertain would be the most useful. I also have a confused emotion if a tool returns no results

 Transition thinking and speaking

 ## IMU integration
 simple taps, tilting with more alarm have different taps as commands

 # Head banging
 Safe zones collision avoidance map.

 # PIR
 could work with Pi to wake

 ## Power management
 Pi to do that.

 # Custom low power mode

 # Weather sensor or darkness or
 so has knowledge

 ## Triggers and events and hooks
 look for them

 # loud noises
 trigger lok about

 # sensors
 TOF for distance
 tempaerature
 ultrasonic
 Millimtere wave radar
 ultrasoncis mulitple triangulate
 infrared

 https://huggingface.co/spaces/pollen-robotics/reachy-mini-chatbox

 Gesture recognition

 AI Camera - live object
