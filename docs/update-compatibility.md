# Update-compatibility audit — 2026-10-15

Baseline recovery later on 2026-10-15: the supported `profile_tools.save` API removed only `voice_look` and
`speech_control` from default and Marvin selections, retaining the other tools. Selections were backed up locally
before changes; the app applied a normal backend reconnect. Post-change RPC confirms backend connected and both
tools absent; a typed test returned "Conversation is working." Audible playback was not verified. These two
features are now disabled, not repaired. No installed code was edited. Earlier no-robot-change statements below
refer to the audit before this recovery. Local Marvin defaults also exclude them to avoid re-enabling on deployment.

The previous voice-follow and persistent-quiet implementation violated Simon's requirement to extend the
conversation app without forking or editing its installed code. The update to app 1.1.0 removed our hooks.
Both features are currently broken, despite their external files and enabled-tool settings surviving.
The audit and local retirement work do **not** restore those robot features.

## Evidence and scope

The CLI handoff records a read-only comparison of all 52 installed Python files with distribution RECORD
SHA256 values: zero differences and zero unverifiable files. This continuation inspected the saved 1.1.0
sources under `/private/tmp/reachy-current-app/`; it did not repeat that robot-side integrity check.
The active persona at the last live inspection was `default` (Aiden, language auto). Simon had deliberately
enabled today/location/speech_control/voice_look there. The failure is not a Marvin-only restriction or missing
tool selection. No robot files, app settings, secrets or processes were changed in this continuation.

The local audit covers all Python execution paths in `robot_tools/` and `reachy_hub/`, deployment scripts,
profile configuration and project documentation. Prior staged scripts and backups remain on the robot;
local retirement does not disable those old remote copies. Do not execute them.

## Findings

| Component | Dependency or write path | Result |
|---|---|---|
| `install_voice_look_lifecycle.py` | Replaced installed `main.py` to call `start(deps)` / `shutdown(deps)` | Unsupported; write mode removed and always refused |
| `install_phase1.py` | Replaced `main.py`, `console.py`, `huggingface_realtime.py`, `tools/core_tools.py`, `moves.py` | Unsupported; write mode removed and always refused |
| `deploy_phase1.py` | Called installer, edited app-local profile/tool selection, copied tools, stopped/restarted app; rollback also rewrote app files | Replaced with an unconditional refusal; no daemon calls or file writes |
| `voice_look.py` | Needs the injected lifecycle, `set_voice_facing`, idle factory, added status fields and `BreathingMove` internals | External file alone is insufficient; unavailable on stock 1.1.0 |
| `speech_control.py` | Needs startup ownership plus typed-input, realtime-event, response-request, tool-dispatch and final-playback gates | Persisted JSON alone does not enforce quiet; unavailable on stock 1.1.0 |
| `check_phase1_runtime.py` | Transforms copies in a temporary directory and loads patched classes | Historical regression experiment; does not alter the selected app or prove stock compatibility |
| `today.py` / `location.py` | Ordinary external `Tool.__call__` interface; no injected app behavior | No package edits needed; location config is outside the app install |
| Hub / typed utterances | App JSON-RPC, daemon REST/state/log WebSockets | No package edits; `conversation.say` still exists in inspected 1.1.0 source |
| Hub log parser | Matches app log text | Version-sensitive; needs fixtures/live checks when log format changes |
| `reachy_hub.look` | Experimental live mode posts daemon motion while the app also owns movement | Competing motion path; not a production repair; not started by the hub |
| `reachy_hub.track` | Experimental daemon motion; app-running guard has `--allow-app` override | Isolated experiment; not a production repair; not started by the hub |
| Profiles / enabled-tool selections | Old deployer wrote inside installed app; settings survived this update | One successful survival is not a durability contract; use supported profile/tool RPC and external storage |

No additional package-code writers were found in the local execution paths. The quiet prototype's own write
path targets its external `speech.json` state file, not installed app code. Tool modules, state, environment
configuration and enabled-tool names surviving an update does not establish that their integration still works.

## What stock 1.1.0 provides

The inspected `Tool` interface exposes function calls and `needs_response`; it does not expose external-tool
startup/shutdown or audio filtering callbacks. Main starts/stops its own movement manager and stream without
calling the prototype lifecycle methods. Its manager provides `queue_move`, `clear_move_queue`, listening,
speaking and face-tracking controls, but no `set_voice_facing` or custom idle factory contract.
The status payload lacks our added `primary_is_idle`, `primary_settling` and `is_speaking` fields.

`conversation.interrupt` stops the current response; it requires an active backend session. It does not set
persistent quiet. `conversation.mic` controls microphone input, so it cannot preserve listening for a spoken
resume while muting output. `speech.config` controls local VAD and barge-in, not a persistent speech gate.
`needs_response=False` only skips a tool's follow-up reply; it is not a global silence switch.

The local async/audio changes for 1.1 were another patch prototype. They were not deployed and are not the
approved architecture. Existing prototype tests and earlier live tests only establish behavior with those
unsupported hooks in place; they do not establish functionality after the update.

## Repair boundary

Restoring the requested behavior requires a supported integration with lifecycle ownership, reload/shutdown
cleanup, retained idle pose and motion arbitration, plus a persistent output gate that leaves input active.
Any implementation must verify these capabilities rather than assume they exist because dependencies are
injected into a tool. Runtime monkey-patching, import-time workers, garbage-collector discovery and a second
daemon motor writer would reproduce the same unsupported coupling and are not accepted repairs.

Potential routes are an upstream extension contract or a separately owned conversation/backend component with
the required controls. Neither route has been implemented or selected in this audit. Do not silently replace
Pollen's app, downgrade it, mute the microphone, or claim best-effort repeated interrupts provide persistent quiet.
Phase 2 information tools can use the existing external function-call interface, but remain paused under the
handoff's audit priority. Planned news-context ownership should be reviewed against documented reload behavior.

## Local safeguards and verification

Both installer APIs reject a non-`None` backup directory **before reading source or creating backups**.
Their CLIs reject write mode; `--check` remains a historical in-memory source transformation with explicit
`retired: true` and `deployment_allowed: false` results. A `changed` result never authorises installation.
The deployer has no deployment implementation left. No force flag or opt-in bypass exists.

Regression checks cover imported and standalone refusal, missing source paths, existing backups, unchanged
files and read-only check output. Relevant tool/hub checks are recorded in `test_summary.md`. The robot still
needs a supported implementation and a combined live acceptance check; no runtime repair is claimed.
