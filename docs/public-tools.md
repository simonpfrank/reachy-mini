# Public tools: next phase

Requested by Simon, 2026-10-15. This is the implementation brief and proposed build order. Face following is
deferred. Existing home/media ideas remain recorded for later.

Current correction: app 1.1.0 removed our unsupported integration hooks. **Voice following and persistent
quiet/resume are broken.** The earlier implementation violated the no-fork/no-app-edits requirement. Local patch
deployment is retired; a supported runtime repair remains unimplemented. See [update-compatibility.md](update-compatibility.md).

## Requested behavior

| Capability | Required behavior |
|---|---|
| Today | Keep the existing date/time tool |
| Stay silent | Retire `stay_silent`; remove it from enabled tools and archive the external file rather than deleting history |
| Location | Like `today`: return the configured place reliably so the model does not guess it; weather and local searches share this setting |
| Voice following | Use head and body to look further within the established working limits; live-test reach and holding a heading |
| Stop / resume speaking | Confirmed: “shut up” stops current output and keeps the robot quiet until explicitly told it can speak again |
| Look around | Scan using safe body/head yaw and several head pitch angles; detect objects, people and faces throughout the observed coverage |
| Explicit alignment | Support instructions such as “turn your body ninety degrees right” and precise head yaw/pitch; report actual achieved angles and prevent following/idle motion immediately undoing the command |
| Scene memory | Keep objects/people/faces with horizontal and vertical location, confidence and observation time; support later questions about what is where |
| Search | Reuse the working agent-harness web search and readable-page extraction; replace the weak stock search |
| Weather | Use the shared location, or an explicitly requested other place; useful hourly/daily/weekend forecasts with units and update times |
| News | Headlines, then a selected story, then questions about that story grounded in its retrieved text |
| Provider keys | Choose secure storage appropriate to where each service runs; no keys in source, profiles, prompts, browser code or telemetry |

## Earlier pre-update findings (historical)

The version/marker observations below predate the update to 1.1.0 and are not current runtime status.

- Release preflight checked 2026-10-15: the [official release list](https://github.com/pollen-robotics/reachy_mini_conversation_app/releases)
  labels v1.0.1 latest; the robot's installed package reports 1.0.1, its app is running, and the voice-follow lifecycle
  marker remains present. v1.0.1 documents external tool creation and preserves older profiles; v1.0.0 introduced
  the JSON-RPC surface already used by telemetry. These notes do not announce the requested persistent quiet mode
  or scene memory. A matching package version does not establish an identical HF deployment/source commit.
- `today` remains in the local persona. `stay_silent` is already absent from the local master and the most recently
  checked live enabled-tool list, but its external Python file and historical documentation still exist.
- `voice_look.plan_turn` already splits head/body motion: head reach 35 degrees; body limits -125/+140 degrees.
  Wider useful coverage needs verification and reliable planning/holding behavior, not blindly raising these limits.
  Saturated targets can currently be requeued, and ordinary gestures can still lose the held speaker-facing idle.
- The app has `conversation.interrupt` to clear current playback. Persistent quiet mode and a reliable spoken
  reverse are additional behavior, not established by interrupting one reply.
- Reusable search code is in sibling `agent-harness/agent_harness/tools.py`: `web_search(query)` calls Tavily
  using `TAVILY_API_KEY`; `web_fetch(url)` fetches and extracts readable article text. These functions are callable
  without running another LLM turn, although importing the whole module currently brings substantial dependencies.
  No key values were read during this investigation.
- Public-tool hosting was previously planned as private Hugging Face services, keeping general tools available
  when the Mac is off. Reusing harness code does not require exposing the full harness agent/session API.
- Existing privacy rule: faces and private visual data stay on the Mac/LAN. Scene analysis must respect that rule.

Follow-up inspection of the installed tools (2026-10-15) confirms Simon's observation: `sweep_look` only queues
motion; it neither captures frames nor performs recognition. `camera` separately calls `get_frame_jpeg()` once
and returns that still image for the conversation backend to interpret. It is not continuous visual perception,
and the two tools do not coordinate captures with sweep poses. `move_head` exposes only left/right/up/down/front
presets and resets body yaw to zero; the current enabled tool set has no explicit body-turn-by-angle command.
Simon reports voice direction varies; refine it from observations later rather than block the public-tool work.

## Shared location

Use one configured location record: place, region, country, town-level coordinates, timezone, source and update time.
The location tool reports that record; weather and relevant search/news requests consume it directly. A weather
request for another city is a per-request override and does not silently change home location.

Suggested default from earlier notes: Cobham, Surrey, UK. **Confirmation pending.** No GPS/IP-based guessing or
precise street address is required for the first version. Store user settings outside committed source.

## Speech control

Keep separate operations for interrupting current output and changing the ongoing speech mode. Simon confirmed:
**“shut up” immediately stops current audio and stays quiet until explicitly told it can speak again.**
Do not speak an acknowledgement of the request to become quiet. “You can speak again” is the reverse command;
equivalent explicit wording should also restore speech.
Quiet mode must continue accepting the resume command through speech and typed input. Muting the microphone or
stopping the conversation app would prevent that spoken reverse. The speech preference belongs to the app and
must not be reset by tool-registry reloads, backend reconnects or app restarts; retain the setting until an explicit
resume instruction. Voice following is a separate setting. Specify ordinary tool execution while quiet before
implementing persistent quiet mode.

Playback must stop at the app/audio layer, including queued chunks, rather than relying on a spoken promise from
the model. Add a visible state/reason in existing telemetry so interruption and persistent quiet are distinguishable.

## Look around and scene memory

Treat this as a separate, larger feature with its own acceptance tests:

1. Acquire exclusive scan motion through the app's movement manager; temporarily pause voice following and restore
   its previous enabled state afterwards. Keep explicit cancellation available throughout.
2. Plan safe head/body yaw poses and multiple head-pitch bands with overlapping camera coverage. Settle at each
   pose before capturing; associate every frame with its actual camera/head/body pose and timestamp.
3. Run object, person and face detection locally. Associate faces with people when supported by the observations;
   use anonymous track IDs. Identifying named people is a separate later feature.
4. Convert image detections to base-frame azimuth and elevation using camera calibration and pose. Merge overlapping
   observations with uncertainty rather than counting an object in adjacent frames twice.
5. Keep label, track ID, bearing/elevation or angular extent, confidence, first/last seen and source observations.
   Moving people become stale quickly; static objects can last longer. Refresh or explicitly reset the scene when
   the robot's base placement changes. Head movement alone must not reset or invalidate the map.
6. Report observed coverage and unseen regions. A single-camera angular scene model is the first target; precise
   metric distance or a full 3D room map requires additional depth/calibration evidence. Never fill unseen areas
   with invented detections.
7. Support questions such as “what is on my left?”, “where is the television?”, “how many people?” and “look at
   the person beside the lamp”, using timestamps/confidence to qualify old or uncertain observations.

Automatic face following remains deferred. Face/person detection during a requested scan is included.

### Explicit alignment with the scan tools

Include precise body/head positioning in Phase 3, using the same app motion owner and measured working limits:

- “Turn your body ninety degrees right” means a relative body turn from the current body heading. Move the head
  with the body to maintain its relative orientation, rather than leaving the camera pointing in the old direction.
- Support explicit head yaw/pitch as well as a forward/centre request, with clear reference frames for any absolute
  angles. Return requested and achieved poses; a clipped turn must not be reported as the full requested angle.
- Manual alignment takes priority: pause voice following and retain the chosen idle pose until an explicit resume
  command or another manual positioning request. Breathing and automatic following must not immediately undo it.
- Distinguish moving from observing. A successful turn is not a successful scan; a scan requires fresh frames
  captured after settling, associated with actual poses/times, and analysed across the observed coverage.

### Later follow-up: refresh room presence on wake

Simon reports that people seen around two p.m. can still be treated as present when Reachy wakes later, even
though they have left. The storage/context source of that stale assumption has not yet been traced. Address this
after the scan tools are available; record it now without changing startup or memory behavior in this phase.

- Separate lasting knowledge about people from time-limited observations that someone is in the room.
- On every wake, invalidate prior current-presence claims immediately and start a new observation generation.
  Apply the same rule to app/session startup. An old name in memory or conversation is not evidence of presence.
- Use a fresh scan to rebuild who/how many are currently observed and their locations. Preserve timestamps,
  coverage, uncertainty and unseen areas; camera/scan failure leaves presence unknown, not inherited from before.
- Do not identify the current speaker from the last remembered visitor. Anonymous person/face observations do
  not establish a name; use a current introduction or other verified identity evidence and ask when uncertain.
- Feed the refreshed presence context into the active conversation before making person-specific assumptions,
  so invalidation applies even if the old conversation transcript remains available. Suppress old in-flight scan
  results arriving after a wake/reset. Respect persistent quiet mode during refresh; no forced spoken greeting.
- Acceptance: observe visitor A, sleep, A leaves, then wake. Reachy must not address A as present; fresh evidence
  establishes the current room. Include partial coverage, failed scan and restart with retained old conversation.

## Search, weather and news

- Reuse the harness search/extraction logic behind a small public-tool service with a narrow callable interface.
  Preserve useful sources, publication/update dates and explicit failure results. Avoid adding an extra agent loop
  just to perform an HTTP lookup. Keep retrieved page content separate from executable tool instructions.
- Weather shares the canonical location record and supports explicit place overrides. Return useful forecast
  periods, units, provider/update times and relevant alerts if the chosen provider supports them.
- News keeps stable story IDs for the current conversation: headline -> chosen story -> follow-up questions.
  Retrieve article text before detailed answers; retain its source URL/date and the text used. Give spoken summaries,
  distinguish reporting from inference, and state when an article is unavailable or only partially accessible.
  “The second one” must continue referring to the headlines actually just presented.
- As each replacement is verified, remove the equivalent stock search/weather/time tool from the enabled list
  so the model has one clear choice. Preserve working capabilities until their replacement passes a live check.

## Key storage and service placement

The storage decision follows the service host:

- A Mac service can use macOS Keychain, with provider credentials made available only to the executing service.
  Verify unattended/startup access before depending on it.
- A backend Hugging Face Space can use managed Space Secrets. Keep vendor calls on that backend; do not expose
  secrets in a static/browser Space. Preserve private deployment by default.
- The robot needs only the narrowly scoped service credential where authentication is required. A shared secret
  granting access to every harness agent/session is not a suitable general public-tool credential.
- Keep a credential-name inventory and rotation/revocation instructions. Never log credential values or put them
  in model-visible results. No credentials have been moved or configured by this planning work.

References: [Apple Keychain](https://support.apple.com/guide/keychain-access/welcome/mac),
[backend Space Secrets](https://huggingface.co/docs/hub/en/spaces-overview#managing-secrets-and-environment-variables).

## Three implementation phases

Simon wants substantial batches, few permission prompts and batched verification rather than a separate approval
and test cycle for each tool.

| Phase | Deliver together | Acceptance |
|---|---|---|
| 1. Context and control | Keep today; retire stay_silent and redundant time lookup; add editable shared location; persistent shut-up/resume; fix useful head/body following and retained heading within working limits | One combined automated batch and one live session covering context, silence/resume, reload persistence and motion |
| 2. Search, weather and news | Reuse harness search/extraction; service-side key storage; useful shared-location forecasts; headlines, selected-story summaries and article-grounded questions; retire replaced stock tools | One combined automated batch and one end-to-end information session, including provider failure cases |
| 3. Look-around, alignment and scene memory | Safe full reachable yaw/pitch coverage with body/head; explicit relative body turns and head positioning; fresh pose-linked captures; local object/person/face detection; merged angular observations, confidence/age and questions about what is where | One combined automated batch and one live alignment/scan/cancel/scene-question session |

Phase 3 is the largest engineering task. Automatic face following stays deferred throughout all three phases.
Home/media integrations remain recorded for later: Hue, Harmony, Spotify, BBC Sounds, podcasts, Bluetooth amplifier
playback and remembered favourites. Proposed extra tools below are not silently added to these three phases.
Wake-time presence refresh is a requested follow-up after Phase 3, once the necessary scan tools exist.

Phase 1 previously passed a combined live check on the patched 1.0.1 app, including quiet across reload/restart,
explicit resume and location/date calls. The subsequent 1.1.0 update removed the app hooks and broke quiet and
voice following. External tool files/settings surviving does not preserve their integration. Today/location do
not require those hooks. Current tools/settings and retired deployment paths are documented in `tools.md`.
Phases 2 and 3 remain unbuilt; stock search/weather and `sweep_look` have not been replaced. Phase 2 remains
authorised but paused under the audit priority. Supported runtime restoration and live acceptance are outstanding.

## Execution and verification agreement

- Treat the requested scope as authorization for routine implementation, reversible fixes, backups and the
  deployment/restart steps needed to make the tools usable. Do not add per-tool or per-phase approval gates.
- Batch independent reads, remote staging and verification commands where practical. Platform-enforced access
  approvals cannot be bypassed; request a sensible reusable permission where supported, and explain any genuinely
  necessary user action. Ask only for missing account access/credentials, scope changes or consequential choices
  that cannot reasonably be resolved from the existing instructions.
- Build tools together within each phase and run one relevant combined verification batch before its deployment,
  plus one combined live acceptance session. Rerun checks only when a failure, changed code or unresolved concern
  justifies it. Do not repeatedly run the full suite to rediscover the six already documented experimental tracker
  failures; retain the baseline and report any new failures explicitly.
- Reuse the typed telemetry input for repeatable instruction checks. Report phase results together rather than
  narrating or seeking approval for every individual test or tool.
- Use Cobham, Surrey, UK as a clearly provisional, editable default from the existing context unless Simon corrects
  it. This assumption is not a claim that he explicitly confirmed his location, and need not block independent work.
- The existing `plan.md` remains the implementation contract; update it when scope changes instead of restarting
  an approval loop for routine choices already within this scope.

## Possible additions to consider

- Timers and alarms.
- Consistent playback controls: pause, resume, cancel, repeat, continue, volume and mute.
- Capability/status help: available tools, current location, speech/following mode and service availability.

These are proposals, not additional implementation scope approved by Simon.
