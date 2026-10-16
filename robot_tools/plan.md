# Update-compatibility repair (2026-10-15)

## Runtime restoration now explicitly required

Simon rejected disabling the features and explicitly requested both fixed quickly. Implement/deploy/test the
replacement within the existing no-app-edits requirement; no further approval loop for agreed functionality.
Use the stock configurable local realtime endpoint for a separately supervised, transparent HF relay that
preserves microphone/STT while gating output/tool calls and persisting explicit quiet/resume. Keep the existing
hosted allocator and voice. Bootstrap the external voice tool through the realtime function-call protocol, then
let the stock BackgroundToolManager own/cancel its long-running coroutine. Use only public queue_move/get_status
and the Move evaluate contract, without injected manager methods or a second daemon motor writer. Retained
speaker-facing breathing uses an external BreathingMove subclass through that queue and yields to gestures.
Tools are stdlib HTTP adapters to loopback state; service code/deployment lives outside the app/tool install.
Back up tool/config selections and verify stock package hashes before/after. Test quiet, mic/transcription,
no actions/audio while quiet, explicit resume, reload/restart persistence, one follower and gesture/idle heading.
Questions/answers: preserve current default profile/voice/language; no new provider/account; no app code edits.
Earlier audit-only pause is superseded by this explicit runtime-repair request.

This section supersedes the historical delivery/patch instructions below. Simon requires no fork or direct
edits of the installed conversation app. Version 1.1.0 removed our hooks; voice following and persistent quiet
are broken even though their external files and enabled-tool settings remain. The earlier implementation
violated that requirement. A local 1.1 patch prototype is not an acceptable repair and must not be deployed.

Authorised audit work, resumed from the CLI handoff:
1. Trace every package-code write and runtime dependency, including deployment and experimental motion paths.
2. Retire write/deploy entry points before any reads, backups, robot calls or settings changes. Keep historical
   source-transform checks read-only; they do not certify stock-app compatibility.
3. Correct the current status, separate surviving external tools from unsupported integrations, and document
   the missing interfaces needed to restore the promised behavior without patching or competing motor writers.
4. Test refusal through both Python and CLI entry points and run the relevant existing local regression batch.
5. Leave the robot runtime, staged robot scripts, profiles and secrets untouched during this audit.

Answer fields: no new product questions; the existing no-app-edits/update-survival requirement controls this
work. Runtime restoration remains unimplemented until a supported integration satisfies it. Phase 2 stays
authorised but paused while the architecture issue is resolved.

Audit outcome: [docs/update-compatibility.md](../docs/update-compatibility.md). Both local installers now refuse
write mode before source reads/backup creation. The local deployer is a no-side-effect refusal. Read-only
historical transforms remain explicitly retired. 113 focused tests, Ruff and strict mypy passed. No robot file,
profile, process or secret changes; old staged robot scripts remain unsafe to execute. This completes the local
audit/retirement work, **not** the runtime repair.

# Historical repair voice-follow

## Goal
Reachy turns smoothly toward the person speaking at normal volume, keeps facing them during pauses and breathing, and switches when another person speaks. It starts automatically with the conversation app.

## Findings from the running robot (2026-10-14)
- One conversation process started at 23:10:31. It logged follower starts at 23:10:41 and 23:11:19, followed by two staggered heartbeat streams and duplicate turn commands milliseconds apart. Module-level autostart and module-local ownership allow followers to survive tool reloads.
- `FacingBreath` holds its heading until another queued move interrupts it. After that move, the installed manager creates an ordinary `BreathingMove` that returns head and body to neutral. The current fix therefore does not preserve facing across conversation gestures.
- The follower tests the raw sound bearing before clamping to reachable head/body limits. Logs repeatedly request bearings around -225 degrees and clamp to head -160/body -125. There is no check for a useful reachable change or circular bearing handling.
- The live tool has no explicit pause during robot speech and no dominant-source test. Three polls can represent one short detection burst; they do not establish sustained speech.
- The head-relative sound frame matches Pollen's official sound_doa example and the earlier recorded experiment. Do not arbitrarily change its sign or scale.
- Daemon reports enabled motors, no errors, and a running control loop. Six experimental tracker tests fail; that implementation is separate from the live tool.

## Technical approach
1. Repair the existing on-device tool. Preserve unrelated telemetry and experimental files.
2. Give each movement manager one follower owner with locked start/stop and explicit cleanup/reload handling. Stop and join an old follower before replacement; retain the stop preference.
3. Integrate a persistent speaker-facing idle pose with the app's single movement writer. Queue finite smooth turns; restore facing after gestures. Inspect the available lifecycle hooks before choosing a small adapter or narrow app patch; do not add a second motor writer.
4. Use fresh speech evidence, reject ambiguous competing directions, pause evidence during motion and robot output, and log reasons for waiting. Keep initial thresholds conservative and tune from real recordings.
5. Handle circular bearings, clamp to the established body limits (-125/+140 degrees) and head reach (35 degrees), and suppress repeated unreachable/no-change requests. Scale turn duration to angle.
6. Add regression checks for reload/start-stop ownership, facing after idle and gestures, stale/burst/ambiguous evidence, and saturation/wraparound. Exercise the deployed app's actual movement behavior as well as pure decision logic.
7. Back up the robot file, deploy the tested repair, restart only the conversation app to remove existing orphan threads, and check that one heartbeat stream remains.
8. Live acceptance test: normal speech front/left/right at the usual distance, pauses, then an ordinary conversation gesture. Record raw bearing and actual head/body motion. Passing software tests alone does not establish that it faces a person accurately.

## Approval and current scope
- Simon approved implementation and backed-up deployment/restart: "ok make it so".
- This change implements the lifecycle agreed immediately before approval: automatic start with the app, a single app-owned follower, voice-tool enable/disable, shutdown cleanup, and on/off state preserved across tool reloads.
- Speech thresholds, turn planning, and gesture/idle behavior are separate follow-up repairs. Do not bundle them into this lifecycle change.
- The installed app has no external-tool lifecycle callbacks. Add a narrow, reproducible patch to its startup/shutdown to call the voice tool's lifecycle methods with the real injected dependencies. Keep the patch installer in this repository, back up the installed files, and validate the patch against the installed source before deployment.
- Face tracking should be off for voice-follow testing; no live speech acceptance result has been claimed.
- Simon confirmed camera head tracking should remain disabled going forward. Disable the daemon tracker and remove `head_tracking` from Marvin's enabled tool list, backing up the original selection.

## Delivered 2026-10-15
- Removed import-time autostart and garbage-collector dependency discovery. Added explicit `VoiceLook.start(deps)` and `shutdown(deps)` lifecycle methods.
- Controller and creation lock live on the movement manager. Enable/disable is serialized, and stopping waits for the old worker to exit before it can be replaced. A poll finishing after a stop cannot queue a turn.
- Added a version-checked, idempotent installer for the app entry-point hooks. The installed app source was validated and backed up before modification.
- Robot backups: `/home/pollen/reachy_tools_backups/voice-look-20261015T121427Z/`; staged installer and deployment manifest: `/home/pollen/reachy_tools_deploy/voice-look-20261015-lifecycle/`.
- Deployed tool SHA256: `d9d19310c9bc1c5a1fcb692b540cc4d50f191073ddbd4f9234a6ed197ee39712`. Patched main SHA256: `0fe07f01ae1267c864121228c3739344185fd9277cda043c1337a126812db17f`.
- Four installer tests and ten worker lifecycle tests pass. Full unit suite: 110 passed, same 6 pre-existing experimental tracker failures. Lint passes for changed Python files.
- Robot-side checks use its actual `MovementManager`, `ToolDependencies`, and file loader with a quiet worker and no motor writes. They confirm one worker across file reload, disabled-state retention, re-enable, and shutdown from the original startup tool instance.
- Live app logs confirm registry reload at 13:14:54 kept worker `7f9127a210`, shutdown logged that worker off at 13:15:01, and the next app startup at 13:15:18 created one worker `7f65d586b0`. Subsequent heartbeats show only that ID. Times are the robot's local log timestamps.
- App status is running with no error. Installer check reports `changed: false`, confirming hooks remain installed.
- Daemon face-tracking disable returned `enabled: false`; live Marvin tool selection includes `voice_look` and excludes `head_tracking`. Local master persona updated too. Original live tool selection saved alongside backups.
- Physical speaker-facing accuracy and follow-up gesture/idle repairs remain to be tested/addressed separately.

## Next phase: public tools (2026-10-15)

Simon wants to defer face following, use voice direction for a while, and move on to public tools. Detailed
requirements, observed existing capabilities, architecture choices and proposed build order are in
[`docs/public-tools.md`](../docs/public-tools.md).

Answer fields and working assumptions:
- Default location: **provisional, editable Cobham, Surrey, UK from existing context; not explicitly confirmed**.
- “Shut up”: **confirmed: stop current output and stay quiet until explicitly told it can speak again**.
- Reverse phrase: **“you can speak again”, or equivalent explicit wording; keep listening while quiet**.
- Key storage/hosting: **proposal depends on service placement; no credentials changed**.

No new public-tool implementation or robot configuration changes were made during this scoping pass.

### Phase 1 implementation started
Simon explicitly requested implementation ("are you going to build?"). Build the agreed Phase 1 batch now:
location, persistent quiet/resume, retiring stay_silent/redundant time lookup, and useful head/body following fixes.
Use the provisional location default and the confirmed silence semantics. Existing scope authorizes backed-up
deployment and app restart. Reuse the installed app's actual control/audio paths and verify the batch together.

Delivery is grouped into three phases in `docs/public-tools.md`: (1) context, quiet/resume and voice-follow motion,
(2) search/weather/news with credential storage, (3) local look-around and scene memory. Simon requests batched
tests and minimal permission prompts. Use one relevant verification batch and one combined live check per phase;
no per-tool/per-phase approval gates for the already requested scope. System access approvals still apply.

### Phase 1 delivered (2026-10-15)
- Added `location`, with a shared external settings file, validated paired coordinates/timezone and the explicitly
  provisional Cobham default. No exact coordinates guessed.
- Added `speech_control` and app input/output hooks. Quiet commands stop playback without acknowledgement;
  microphone remains active. Quiet state survives registry reload, backend replacement and app restart.
  Resume is explicit. Pending response requests and old response audio are suppressed, including after resume.
- Removed retired `stay_silent` source/tests; archived its robot copy. Kept `today`; removed duplicate stock time
  from local and live Marvin tool selection. Added location/speech instructions without replacing live persona/voice.
- Added circular/reachable turn planning, scaled head/body duration and interpolation around the yaw seam,
  saturation suppression, sustained/dominant speech evidence, motion/output pauses and restoration of the chosen
  heading when normal breathing restarts after a gesture. Single worker and single motor writer are retained.
- Installed validated five-file app patch with `install_phase1.py`; it and the earlier lifecycle check are
  idempotent together. `deploy_phase1.py` backs up touched tools/profile/selection, replaces files with rollback
  on deployment failure and restarts the conversation app.
- Local verification: 103 focused tests passed; lint and type checks passed. No broad rerun of the six known
  experimental tracker failures. Real installed-class check passed with 804 sampled yaw paths and simulated
  gesture-to-idle restoration, plus actual playback and request/tool gates; no hardware connection in that check.
- Combined live verification passed: tools available, microphone active while quiet, ordinary typed request
  suppressed with zero assistant audio events, quiet retained across tool reload and full app restart, explicit
  resume enabled speech, then location/today produced the spoken Cobham/current-date answer (seven audio events).
  The live harness was corrected to retry temporary HTTP 403 responses while the app WebSocket route mounts.
- Release: `/home/pollen/reachy_tools_deploy/phase1-20261015/`.
  Backups: `/home/pollen/reachy_tools_backups/phase1-20261015T175850Z/`.
- Remaining acceptance: real speech left/front/right at normal distance and an ordinary gesture. These checks do
  not claim physical speaker-facing accuracy. TV rejection and automatic face following remain deferred.
- Remaining build: Phase 2 search/weather/news/key storage; Phase 3 look-around and local angular scene memory.

### Follow-up observations and scope (2026-10-15)
- Verified installed `sweep_look` only queues motion; it does not capture any pictures or recognise objects.
  `camera` separately reads one JPEG. `move_head` has five fixed presets and resets body yaw to zero, without
  exposing a precise body-angle turn. Existing tools are not coordinated visual scanning.
- Expand Phase 3 with explicit relative body turns and head yaw/pitch positioning, including actual achieved-angle
  results when limited. Manual alignment must pause voice following and hold its idle pose until explicit resume.
  The scan itself captures fresh settled frames at actual recorded poses/times, then analyses that coverage.
- Voice-bearing variability is acknowledged and can be refined later; do not let it block the next tools batch.
- Record a requested follow-up after scan tools exist: refresh current room presence on wake/start. Old observed
  people become unknown immediately; fresh observations rebuild the room context. Preserve long-term knowledge
  while expiring presence, and prevent old conversation/late scan results from being treated as current evidence.
  Names require current verified evidence, not an old visitor assumption. Failed/partial scans retain uncertainty.
  Honor quiet mode. No runtime/memory behavior changed in this recording pass.

### Phase 2 implementation authorised (2026-10-15)
Simon requested building the next phase and key-placement instructions after the build. Implement search,
page reading, shared-location forecasts, news headline selection and grounded story follow-up now. Keep
Phase 3 scan/alignment and later wake-presence refresh out of this batch.

- Build a small private HF Docker Space service in `public_tools/`, independently of the app environment.
  Reuse the harness's direct Tavily HTTP search and hidden-content removal/trafilatura extraction approach.
  No broad harness agent/session API and no additional LLM loop. No new robot app is needed.
- A standard-library external `public_info` tool dispatches search/read/weather/headlines/story operations.
  It reads canonical location directly from the enabled location tool and keeps bounded news selections and
  retrieved story text on the movement manager so tool reloads/backend reconnects retain numbering/context.
- Provider secrets live only in backend Space Secrets. The robot gets a read-only token for that private
  Space in a separate 0600 config file. No credentials in command arguments, source, prompts or telemetry.
  No HF login is currently available on the Mac; finish code and tests without borrowing existing harness keys.
- Include a setup command that privately prompts for deployment authentication, Tavily key and read-only
  robot access, creates/uploads the private Space, verifies the live service and installs/enables the tool with
  backup. Keep working stock search/weather enabled until replacement live checks pass.
- BBC RSS headlines and Open-Meteo weather need no provider keys. Topic-specific news and general web search
  use Tavily. News follow-ups return retrieved article evidence to the conversation model; unavailable/partial
  articles are explicit. Selected story IDs/indices refer to the actual presented headline set.
- Bound network duration, redirects, payload sizes and caches; public-page fetching must reject private/local
  targets, including redirects, and connect to vetted IPs. Extracted page text is untrusted source material.
- Batch unit/contract checks once the feature set exists; then one real-provider/local-service integration batch.
  Keyed live search and final hosted robot acceptance must be reported separately if keys are still absent.
