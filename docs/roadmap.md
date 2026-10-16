# Roadmap

One new thing per step. Status: ✅ done, 🟡 in progress, ❌ not started. Architecture: `docs/architecture.md`. Links and finds to investigate: `docs/ideas.md`. Where tools live: `docs/tools.md`.

**Current correction (2026-10-15):** the app is now 1.1.0. Updating removed our unsupported app hooks, breaking
voice following and persistent quiet/resume even though the external tools remain enabled. Their earlier
delivery claims describe the patched 1.0.1 app. Local patch deployment is now retired; the robot features are
**not repaired**. See [the compatibility audit](update-compatibility.md). No robot edits/restarts during this audit.

| # | Step | Done when | Data risk | Status |
|---|---|---|---|---|
| 0 | Robot alive from the Mac | Daemon healthy, SSH works, sound direction readable, robot wakes | None | ✅ (wake needs motors enabled first) |
| 0b | Find the silent-TTS cause | Deferred until the turn timeline exists. Then: reproduce in the far room with WiFi/router-ping/CPU logged on the robot (a 1 Hz on-robot logger worked; log on the robot, not over SSH) and match failure times | None | ⏸ |
| 1 | Stock conversation app, hosted voice | App talks and hears (transcripts, tool calls, replies seen on the dashboard 2026-10-13); starting the app wakes the robot (motors on) by itself. Not covered: waking by voice from sleep (stock app has no wake word; ours, later) | Audio goes to HF | ✅ (except wake word from sleep) |
| 2 | Our persona | Custom profile loads from an external folder, no fork; works on the robot. No stage directions: default persona's "[sigh]" is read aloud as "sigh" by the hosted TTS (seen 2026-10-13) | Same as 1 | ❌ |
| 3a | Voice tracking (turn to sound). Design and experiments: `docs/voice-tracking.md` | Turns toward Simon speaking from left or right within about a second, using the daemon's direction reading. Does not chase the TV over a 5-minute test: only turn on detected speech, steady direction (~1 s), cooldown, ignore the TV's fixed direction. Front/back: DoA covers a half-circle only (0 left, 90° front or back, 180° right); fine in conversation (person in front); if needed, resolve by turning and re-listening. Dashboard first: held 'last voice heard from X°, n s ago' + recent range | None | ❌ |
| 3b | Face following (deferred 2026-10-15) | Live with voice-direction following for a while first; keep automatic camera head tracking disabled. Face/person detection during requested look-around scans is still in scope | None: faces stay on Mac/LAN | ⏸ |
| 4 | Our public tools | Today/location use ordinary external tools; stay_silent retired. Quiet/resume and voice-follow integration broke after update and need a supported repair. Then search/weather/news and local look-around. Plan: `docs/public-tools.md` | Public queries to providers; faces stay on Mac/LAN; service-side keys | 🟡 (update repair required; phases 2–3 unbuilt) |
| 5 | Private brain | `ask_brain` (on the robot) calls agent-harness on the Mac; persona says "checking", timeout handled; serious mode: automatic for anything from `ask_brain` (plain, exact read-back, confirm changes) and on request ("serious mode" until "back to normal"); start as a rule in Marvin's profile, switch to a separate plain persona via `personalities.apply` only if the rule proves unreliable (links to step 7 modes); safe slice first: reminders and calendar (today's one thing, what's due, add reminder with approval) | Reminder titles reach HF until step 6. No email/messages | ❌ |
| 6 | Local backend on the Mac | speech-to-speech on Mac; median end-of-speech to first audio <= 1.5 s good, <= 2.5 s acceptable; Gemma vs Qwen3.5-4B. Gate for email and messages. | None leaves Mac/LAN | ❌ |
| 7 | Modes and brain-off | General/personal switch; sensible behaviour when the Mac is off | None | ❌ |
| 8 | Our voice | Parakeet STT and Marvin TTS plugged in as HTTP endpoints | None | ❌ |
| 9 | Voice ID gating, then face ID | Some tools only for Simon's voice; stops replying to the TV (seen 2026-10-13: Marvin answered the TV and joined in a game; profile rule is only a partial fix, wake word is the other route); known faces recognised locally | Faces stay local | ❌ |
| 10 | Later, as wanted | Siri capture, always-on node, AI Camera, Echo (write-only), TV/noise handling | | ❌ |

## Current public-tool plan

See [`public-tools.md`](public-tools.md) for Simon's 2026-10-15 requirements, existing functionality, proposed
build order and open decisions. Face following is deferred; voice following is currently broken after update. Broad
scene scans include objects, people and faces with lateral/vertical bearings, confidence and observation time.
Reuse the existing harness Tavily search and page extraction; choose service hosting and key storage before
wiring search, weather and news. “Shut up” is confirmed to stop audio and remain quiet until explicitly told it
can speak again, while retaining listening for that command. Use a provisional editable Cobham, Surrey default
unless corrected. Deliver in **three phases**: context/control + head/body following, search/weather/news + keys,
then local look-around + scene memory. Batch verification and live checks by phase; avoid per-tool approval loops.

Follow-up requirements (2026-10-15): the installed sweep only moves; camera is a separate single-frame capture.
Phase 3 must coordinate actual captures with sweep poses and include explicit body/head alignment, such as a
relative ninety-degree right body turn, held until following is explicitly resumed. Variable voice direction can
be refined separately. After those scan tools exist, refresh room presence on every wake/start: invalidate old
presence immediately, observe again, and never assume a previously seen person is still here from old memory.
Keep enduring knowledge about people separate from temporary presence. Detailed behavior/acceptance is in
[`public-tools.md`](public-tools.md).

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
- **Web search is poor (seen 2026-10-13 via the hub).** Two faults: the AI searched "current movie list 2024" (doesn't know today's date) and Pollen's search Space returned "Electric current - Wikipedia"; it also sometimes returns "web search failed". Fix: step 2 persona gives today's date / uses the time tool and asks for specific, dated queries; step 4/5 replaces Pollen's search with ours via `ask_brain` (agent-harness has web search).
- **Which models answer us? (parked 2026-10-13; Simon wants all the possibilities)**
  - Today (hosted): app names no model; Pollen's forwarder (`pollen-robotics-reachy-mini-realtime-url.hf.space`, supports A/B) sends sessions to a private HF Inference Endpoint (`hkbax8u9qwedr1uv.endpoints.huggingface.cloud`). Voice list = Qwen3-TTS CustomVoice presets, so very likely HF speech-to-speech (Silero VAD -> STT, likely Parakeet -> vision-capable LLM -> Qwen3-TTS). LLM unconfirmed. Hosted reply speed baseline: first audio ~1.45 s after transcript (app's own "Turn latency" log).
  - To confirm: run the app by hand on the robot with `--debug` (Pollen dev workflow) and read `session.created`.
  - Possibilities to compare: (a) Pollen hosted (free, unknown/changeable models, data to HF); (b) speech-to-speech on the Mac (choose each stage: STT Parakeet/Whisper; LLM Qwen3.5-4B in-process or Gemma via LM Studio; TTS Qwen3-TTS presets, Pocket TTS clone, OmniVoice clone, or our Marvin endpoint); (c) our own HF Inference Endpoint (paid, our choice of models, still off-Mac); (d) other realtime providers (OpenAI, Gemini) for general mode only, never personal data.
- **Vision: `look_around` (expanded 2026-10-15).** Replace the movement-only sweep with safe full body/head yaw coverage and pitch bands. Capture settled frames with actual poses, detect objects/people/faces locally and retain a timestamped angular scene model with lateral/vertical location. Account for unseen regions, moving people, uncertainty and changed base placement. Automatic face following stays deferred. See `docs/public-tools.md`.
- **Voice: choosing vs adding.** Hosted: 9 presets only (Aiden, Ryan, Dylan, Eric, Ono_Anna, Serena, Sohee, Uncle_Fu, Vivian), set via `voice =` in profile.md or the UI. Own voice needs our backend (step 6/8): Marvin endpoint (tts-chatterbox), Pocket TTS or OmniVoice clone.
- **Dashboard gap (seen 2026-10-14): when the app hears nothing there is no trace.** "Look up"/"look down" left no transcript, event or log line. Add: peak mic level over the last 10 s next to the sound bar, so a missed request shows whether the mic heard it. Firmware 2.1.4 adds +6 dB on the INPUT (changelog), which may help a quiet mic.
- **More dashboard additions:** `camera.image` event DONE 2026-10-13 (photo size, every picture sent to the AI); still to do: the picture itself (no daemon snapshot route: needs WebRTC from the Mac or a small robot-side helper), `latency` events from the app's "Turn latency" lines, move started/finished from the daemon (movement tools report "done" while still moving).
- **Idle behaviour (traced 2026-10-13).** After 180 s with no conversation (and again every 180 s while idle, only when the robot isn't moving) the app picks a random idle action, with no AI involved: stillness 60%, dance 16%, emotion 16%, move head 8% (`idle_policy.py`), only among tools the persona enables. An idle emotion is random from a curated pool of 47 that includes `dying1`, `rage1`, `scared1`, `sad1`. Timer is hard-coded (`IDLE_BEHAVIOR_THRESHOLD_S = 180.0`, `conversation_handler.py`); weights and pool are hard-coded too. Without forking, the only control is the persona's tool list (dropping `play_emotion` also stops the AI using emotions). Decide in step 2; consider an upstream issue to make it configurable.
- **Dashboard fixes needed:** label idle actions (call id starts `idle-`) as "idle" in the event list; ignore IMU "taps" while the robot moves itself (emotions/dances/speech wobble triggered false taps at 2.0-3.2 m/s^2).
- **Weather tool is limited (2026-10-13 via the hub).** Pollen's tool answers "Cobham, GB" (drops the county) and only gives now + today's high/low: no hourly, no weekend. Temperature matched Open-Meteo within 0.5°C. Later: our own tool with home coordinates fixed and a real forecast (Open-Meteo, no key).
- **SOON: sound-card firmware 2.1.2 -> 2.1.4 (louder speaker).** Robot's "Reachy Mini Audio" (USB 38fb:1001) reports bcdDevice 0212 = 2.1.2. Pollen's 2.1.4 adds +6 dB (changelog says "audio input"; PR #1187 author measured louder playback) and fixes mic-after-USB-reset. File already on robot: `/venvs/mini_daemon/.../reachy_mini/assets/firmware/reachymini_ua_io16_lin_v2.1.4.bin` (standard 2-ch; the 6-ch file adds the 4 raw mics, revisit later). Flash: stop conversation app, `dfu-util -R -e -a 1 -D <file>` (may need sudo), restart daemon if needed. Measure before/after with the same test sound + dashboard robot sound bar. `REACHY_AUDIO_GAIN_DB` is from closed PR #1187, never released: setting it does nothing. ALSA speaker controls already at max (0 dB of -60..0).
- **Dashboard:** read `Domotick/reachy_web` (code and security) first; build only the gaps (sound level, direction, what the app is reacting to, WiFi/CPU log). Our own earlier work: `reachy-mini-aide/first_app` has a small control panel (state badge, wake/sleep, face on/off, speech-animation tests, debug toggle; ~130 lines of HTML/JS), built for the simulator. It is a control panel, not telemetry.
- **Mine from reachy-mini-aide (don't carry over wholesale):** `caldav_client.py` (calendar without macOS EventKit: the route to a brain on a Pi), pluggable sensor interface with simulator fakes (`sensors/interface.py`). Its `llm_tools/` (calendar, email, iMessage, reminders, memory) duplicate agent-harness: pick one brain, agent-harness.
- **Pose limits:** head knocks the body in some poses. Software clamp only, never servo EEPROM. Record the colliding poses first.
- **`reachy_web` reviewed (greps only, not a full audit):** covers daemon control, camera, 3D twin, moves, app store, log console, wifi/OTA, mic level meter. Does NOT show sound direction or "what is reacting". Can run on the Mac with `run.sh` (venv goes to `~/.venvs/reachy_web`, outside Documents), nothing installed on the robot, falls back to port 8043 if 8042 is taken. No shell=True/eval/exec found; no login (same as the daemon's own API, which is open on the LAN). Not yet run.
- **Turn timeline (needed, first custom dashboard panel):** one row per event with a turn id and timestamp: speech start/end, STT, LLM handoff and reply, tool call start/end (`ask_brain`), TTS first audio, interruption, head turn, wake/sleep. Merge sources instead of building a state machine: realtime backend events and its per-turn latency line, conversation-app log (daemon journal on the robot), agent-harness JSONL trace, daemon state (moves, direction, tracking). The aide only had a polled state badge (1 s) and a debug toggle; see `docs/aide-reuse.md`.
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
