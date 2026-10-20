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
| 4b | Our sleep and wake word | To define before building: [4b](#step-4b--sleep-and-wake-word-to-define) | To define | ❌ |
| 4c | Room scan | To define before building: [4c](#step-4c--room-scan-to-define) | Images: per 4d | ❌ |
| 4c2 | Voice following and TV fixes | Faults seen 2026-10-18: [4c2](#step-4c2--voice-following-and-tv-fixes-seen-2026-10-18) | None | ❌ |
| 4d | Information security levels | To define before step 5: [4d](#step-4d--information-security-levels-to-define). Gate for the private brain | Defines it | ❌ |
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
- **P2-2 — Read:** `read_article` fetches the page itself and extracts its text with BeautifulSoup. It also
  returns the page's links in page order, numbered (`link=N` reads one) and kept apart from the search/news
  list; the model decides what to offer. Only approved sites are read (`approved_sites.txt`, one per line;
  a site matches exactly or as a whole-dot subdomain; redirects included). For any other site it fetches
  nothing and replies `not_approved`; the robot asks the user, naming the site. `approve_site` adds that exact
  site permanently only if code confirms, from the app's transcript history, that the robot named it after the
  refusal and the user's next words said yes with no "no". The model cannot approve alone. Accepted risk: another
  voice (e.g. the TV) saying yes at that moment. Text is bounded, returned as untrusted page content (never
  instructions) and states when it is partial, refused (with the reason) or unavailable.
- **P2-3 — Forecasts:** `weather` uses the UK Met Office model through Open-Meteo (no key) and C2; explicit place overrides, today/tomorrow,
  hourly, weekend and seven-day periods, units and provider update time; disambiguate places.
- **P2-4 — News:** `news` uses BBC RSS plus topic search. Headline numbering survives unrelated calls, tool
  reloads and reconnects; "the second one" refers to the presented list. Fetch the article (P2-2) before
  detailed answers; distinguish reporting from inference and state incomplete coverage.
- **P2-5 — Guardrails:** search, weather and news call fixed provider endpoints only. `read_article` fetches
  public web pages under fixed checks in code: http/https on ports 80/443; no IP-address hosts or local names;
  every resolved address public, re-checked on each redirect (at most 5), and the connection made to the
  checked address. Timeouts and response-size caps throughout. Standard library plus BeautifulSoup, installed
  in the app environment with `scripts/tool_deps.sh install` (pin in `robot_tools/requirements.txt`). Tavily key encrypted with `systemd-creds --user` and decrypted in memory per request, never
  in source, profiles, prompts or logs; accepted limit: anything running as `pollen` can decrypt it. Each
  search, read and failure is logged. Accepted risk: misuse while unattended.
- **P2-6 — Setup/replacement:** build and unit-test without a key; Simon adds the key with
  `scripts/keys.sh add tavily`. Keep the Pollen's built-in search/weather tools until replacements pass, then
  remove them from the tool selection.

## Step 4b — Sleep and wake word (to define)

Existing notes, moved here; the requirement is still to be agreed:

- From step 1: waking by voice from sleep is not covered; the stock app has no wake word.
- **B-WAKE:** wake word only for sleep, with one classifier thread, cooldown and microphone handoff to conversation;
  compare platform-specific models and gate background directions. Candidate offline reflex responses need no LLM.
- Phases: first make sleep and wake work with a built-in wake-word model; then train "hey Reachy".
- Phase 1 (built 2026-10-18; Simon's live sleep/wake test passed the same day): `sleep` tool starts the `reachy_wake` watcher
  (`systemd-run --user`), then Pollen's sleep; the watcher listens on the shared mic for "hey mycroft"
  (openWakeWord 0.4.0, about half of one CPU core) and starts the app with its last-used personality. Other
  sleep routes need the app started by hand. Setup: [development_setup](development_setup.md#sleep-and-wake-word).
- Custom wake word ("hey Reachy"): train with varied English accents, including South African, Ghanaian and
  Zimbabwean, and test with the carers.
- Anyone may use the wake word: it only starts a conversation. What each person may do is enforced by tools (4d).
- Later sleep/wake behaviour (not in this step): [B-SLEEPWAKE](#further-candidates).

## Step 4c — Room scan (phase 1 agreed 2026-10-20)

**Phase 1 = the capture sequence only** (no analysis); defined in chat, no formal PRD. Iterate from there.

- One row at level pitch, over the robot's full reach: start at full body yaw and full head yaw one way, step to
  the other. Same fixed set of photos every scan, each saved with its measured pose.
- Step = the camera's horizontal field of view × (1 − overlap), spread evenly so the last frame lands on the limit.
  Body turns first; the head adds reach only beyond the body's limit.
- Settings, not constants (environment / `.env`): overlap 25%, horizontal field of view (87°), separate left and
  right limits for body yaw (−125° / +140°, the measured limits in `voice_look`) and head yaw (±35°, also
  `voice_look`; the SDK allows 65°), pitch (0°). Recalibrate when the robot is back.
- Moves go through the app's movement manager using a shared smooth move in `robot_tools/reachy_lib/` (not a
  tool): yaw is interpolated as an angle, so a long turn cannot take the short way round. The scan captures the
  pose first and moves back to it at the end.
- Runs to completion, then the robot carries on with what it was doing (previous pose and state restored).
- Keeps the latest scan's photos only, overwritten each time.
- Callable as plain code by the model's tool now and lifecycle triggers later (wake, noise, PIR); each scan stores
  a `reason`. Trigger rules, analysis and room-change detection come after the sequence is right.
- Until the robot is repaired, testing is on the Mac: plan maths in unit tests; the sim does not move the head
  and returns the same photo every time.

Simon's direction (2026-10-18), later layers still to be agreed as requirements:

- **Build in layers, recording before analysis:**
  1. Capture: the private camera tool takes a photo with its metadata (head/body pose, time).
  2. Scan: repeated captures that cover everything the robot can see, with coverage metadata.
  3. Analysis: a base level that runs on the robot, plus optional enhancements where the user chooses a model
     (e.g. on the Mac), behind one simple interface.
  4. Map: landmarks, objects and people built from the analysis.
  Publish the basic tools later, so keep them free of personal paths and data. Face images wait for 4d.
- **Photos are not levelled (changed 2026-10-20):** commanding roll 0 did not level the head, so levelling was
  removed. Every photo records its measured pose, including roll, and analysis straightens using it.
- **To do: pose correction for level photos.** Measured 2026-10-18: at rest the head's measured roll moved
  between −3° and −6°, while the app's leveling (commanding roll 0) completed at once, so commanding level does
  not make the head level. Cause unknown; investigate first (Pollen's breathing move and the app's continuous
  pose updates, head kinematics, measured versus commanded pose at rest) before any code. Fallback: straighten
  each photo in analysis using its recorded roll.
- **Experiment, after phase 1:** switch to full resolution (4608×2592), take a photo, restore the default, and
  check nothing else is disrupted (Pollen's camera tool, face tracking, video stream, voice following). Also check
  whether it gives real extra detail on the robot or only resizes the default stream.
- **Phase 1 retention, until 4d:** photos stay on the robot only. A scan follows a fixed pattern, so it has a fixed
  number of photo slots, overwritten by each new scan. One-off photos keep only the latest, also overwritten. Leave
  room to keep chosen photos later (e.g. mementos).
- **Built 2026-10-18: `photo`**, the one-off private photo; see [tools](tools.md). It saves the photo and its
  measured pose; levelling was removed 2026-10-20.
- **First build piece: a private camera component.** Takes a photo, records the head/body pose it was taken at,
  and runs detection locally; photos never leave the house. Room scan, people and faces build on it. Pollen's
  `camera` tool stays for conversational descriptions where sending a photo to HF is allowed (4d).
- **The robot's zero moves when it is moved.** Re-anchor to fixed features (kitchen, TV) so observations from an
  hour ago map onto the new scan. No matching features means a different room (e.g. the office): a separate map.
- **Movable objects are labelled by what makes them unique, not where they are:** Lisa's chair moves whenever she
  is put in or taken out, but it is the only black chair in the room.
- **Detection in tiers:** basic detection on the robot always works; a small model on the Mac improves it when
  the Mac is available; the system must work without the Mac.
- **People:** whole body, with a face sub-record, for later face tracking and focusing the camera on a face.
- **Triggers:** start with a tool on request; state changes (wake, long time passed, people coming and going)
  later.

Existing notes, moved here; the requirement is still to be agreed:

- **B-SCAN — Scan:** exclusive cancellable app-owned motion; pause following and restore its previous state.
  Overlapping safe body/head yaw poses and pitch bands; settle before each capture and retain actual pose/time.
  Detect objects, people and faces locally, anonymous until verified identity. Map detections to base-frame azimuth
  and elevation using calibration; merge overlap with uncertainty instead of double counting. Store labels, track
  IDs, angular extents, confidence, first/last seen and source observations. People expire faster than static objects.
  Reset/refresh on changed base placement, not ordinary head movement. Report unseen coverage; never invent objects
  or metric depth. Support scene questions and looking at referenced objects/people using age/confidence.
- **B-PRESENCE — After scanning exists:** invalidate current presence immediately on wake and app/session startup;
  start a fresh observation generation. Keep long-term knowledge separate. Rebuild presence from new scans with
  timestamps/coverage; partial/failed scans leave uncertainty. Old transcripts, names or remembered visitors do
  not prove presence or speaker identity. Require a current introduction/verified evidence for names; ask if unsure.
  Update conversation context and discard results from pre-reset scans. Honour C3; no forced audible greeting.
  Acceptance: visitor A leaves during sleep; wake/restart must not assume A remains, including failed/partial scans.
- **Vision: `look_around` (expanded 2026-10-15).** Replace the movement-only sweep with safe full body/head yaw
  coverage and pitch bands. Capture settled frames with actual poses, detect objects/people/faces locally and retain
  a timestamped angular scene model with lateral/vertical location. Account for unseen regions, moving people,
  uncertainty and changed base placement. Automatic face following stays deferred. Positioning: B-ALIGN (backlog).

## Step 4c2 — Voice following and TV fixes (seen 2026-10-18)

Speaker muted, TV on, 12:20–12:36. Evidence from the app log:

1. **Following switched itself on.** The backend session dropped at 12:31:26 and reconnected at 12:31:32; at
   12:31:33 the model called `voice_look(enabled=true)`, because its description says to turn it on at the start
   of every conversation, and a reconnect looks like a new one. Typing did not trigger it. Fix: an on/off choice
   survives reconnects, decided in code, not re-asked of the model.
2. **Violent body swings.** At 12:33:09 the body went from −105° to +140° (245°), and at 12:34:25 back to −109°
   (249°). A voice heard behind (near ±180°) lies past the body's cable limit (−125°/+140°), so the planner took
   the long way round for zero aim error. Fix: accept a small aim error at the limit instead of a near-full turn;
   cap body travel per turn.
3. **It followed the TV.** All ten turns from 12:31 to 12:36 were during TV speech (transcripts are a TV show),
   on 3–4 readings each. The 3a requirement to ignore the TV's fixed direction is not met.
4. **Front/back ambiguity.** Several turns aimed near ±180° (behind); the sound-direction reading covers a
   half-circle only (3a).
5. **The model answers the TV.** TV speech becomes user turns, and the model replied to each ("I'm not your
   accountant…"), using the backend while muted and confusing typed questions. Related: B-AMBIENT ("that's the
   telly", meeting mode), voice ID (step 9).
6. **Language misdetected.** TV speech was transcribed as Chinese several times; the transcription language is
   unset (left as is for now, 2026-10-18).
7. **Backend session drops** (12:31:26 here; several daily). Pollen's hosted backend; the hub retries typed text once.
8. **Aim drifts away from the speaker (20:10–20:16).** With Simon presumably still, successive heard bearings went
   −58°, −29°, −117°, −144°, −205°, ending behind the robot; the robot apologised for its orientation. Hypothesis
   (unverified): the sound direction and head/body angles are combined in the wrong frame (e.g. the mic array
   turns with the head), so each turn compounds the last. Not a tool conflict: Pollen's `head_tracking` is not
   loaded; persona switches reload tools and `voice_look` replaces its worker cleanly.
9. **Motor communication errors.** "Motor communication error! Check connections and power supply." 34 times on
   2026-10-18 (twice at 20:15); motors reported fine afterwards. Check cable and power; may affect any motion.

## Step 4d — Information security levels (to define)

To be defined before the private brain (step 5), beyond the current rule that private data stays on the Mac/LAN:

- Where memories are stored.
- Where images are stored.
- Where the association between an image and a person is stored.
- A person's right not to be remembered.
- When video may be recorded (e.g. security after a wake event) versus when a face may be captured for memory.
- Who can do what: an unidentified person gets public tools only (the default); private tools check a verified
  identity in code, not the model's word. Needs voice/face ID (step 9).
- Mixed conversations: switching back and forth between private and public tools in one conversation flow.

Related: cross-cutting constraints above; B-WEBGATE (search queries as an outbound channel) and B-APPROVAL below.

## Backlog — not scheduled

Existing requests and ideas below remain in place. Additional detail consolidated from the removed plans:

### Positioning

- **B-ALIGN — Manual positioning:** relative body-angle turns (including ninety degrees right) move the head with
  the body; explicit head yaw/pitch/centre commands have defined reference frames. Report requested versus achieved
  pose after clipping. Manual alignment pauses following and holds idle heading until explicit resume or another
  positioning request. A move is not a scan: observations require fresh settled frames.

### Further candidates

- **B-SLEEPWAKE (follows 4b):** aggressive power management, since battery time is short.
  - Sleep when there is no activity: nobody speaking for a while, nobody in the room (scan), optionally no PIR.
  - Wake triggers beyond the wake word: loud noise (e.g. a door), PIR, other detectors. A trigger means "someone
    may be here": wake, check the room, and go back to sleep if nobody is there.
  - Later, security: noise, look and assess, then act. Recording rules come from 4d.
  - Behaviour may differ on battery versus charger. Charger detection not found yet (no daemon API, SDK or Linux
    power-supply device, checked 2026-10-18); research Pollen docs/Discord.
- **B-CHAT:** a chat app for talking to the robot by text.

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
- **B-BACKEND:** configurable brain endpoint/timeout and offline fallback; pluggable STT/LLM/TTS plus fallback chain.
  Validate end-of-turn detection and interrupted/streaming TTS service interfaces. Voice ID results need retesting
  with Reachy's microphone; end-to-end latency includes the LLM stage. Voice-swap relay is a candidate, not a plan.
- **B-DEPLOY:** reproducible backed-up installation with source/profile/settings rollback and health checks,
  independent companion dependencies, fixed tested revisions and a private source remote. The development lock is
  on 1.1.1 (2026-10-16); environment sync and the reviewed recovery commit remain.
- **B-HUB:** wake watcher events (wake word heard, app started, false wakes) from `journalctl --user -u reachy-wake`;
  daemon loop rate/read-write timing/error counts, WiFi signal, CPU, temperature and throttling;
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
  - Found 2026-10-18: the allocator hands sessions to an HF Inference Endpoint whose public `/health` reports a pipeline of stt `openai`, llm `chat-completions`, tts `openai` (OpenAI-style interfaces; the app requests `gpt-4o-transcribe`), and 15 of 16 sessions in use (possible cause of session drops; unverified). The LLM is still unnamed.
  - To confirm: ask Pollen. Checked 2026-10-18: `--debug` logs only event types, not the `session.created` contents, and Pollen's public session Space forwards to a hidden upstream (`UPSTREAM_SESSION_URL` secret, optional A/B split), so neither names the model.
  - Possibilities to compare: (a) Pollen hosted (free, unknown/changeable models, data to HF); (b) speech-to-speech on the Mac (choose each stage: STT Parakeet/Whisper; LLM Qwen3.5-4B in-process or Gemma via LM Studio; TTS Qwen3-TTS presets, Pocket TTS clone, OmniVoice clone, or our Marvin endpoint); (c) our own HF Inference Endpoint (paid, our choice of models, still off-Mac); (d) other realtime providers (OpenAI, Gemini) for general mode only, never personal data.
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

