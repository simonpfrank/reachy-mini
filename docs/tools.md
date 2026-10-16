# Where a tool lives

Baseline recovery later on 2026-10-15: the supported `profile_tools.save` API removed only `voice_look` and
`speech_control` from default and Marvin selections, retaining the other tools. Selections were backed up locally
before changes; the app applied a normal backend reconnect. Post-change RPC confirms backend connected and both
tools absent; a typed test returned "Conversation is working." Audible playback was not verified. These two
features are now disabled, not repaired. No installed code was edited. Earlier no-robot-change statements below
refer to the audit before this recovery. Local Marvin defaults also exclude them to avoid re-enabling on deployment.

Current status (2026-10-15): the app update to 1.1.0 removed our unsupported hooks. **Voice following and
persistent quiet/resume are broken.** External files and settings survived, but their app integration did not.
The earlier implementation violated the no-fork/no-app-edits requirement. The patch installers and deployment
entry point are retired locally. See [the audit](update-compatibility.md) for dependencies, evidence and repair gaps.

## Placement

| Need | Place | Integration |
|---|---|---|
| Personal data: reminders, calendar, email, messages, contacts, faces | Mac/LAN brain | Planned `ask_brain`; private data stays local |
| Robot hardware | External on-robot tool | Supported tool calls; coordinate motion with the app's owner |
| Provider API keys or public-information service | Private backend HF Space | Backend Secrets; a narrow external tool or supported Space tool integration |
| Small date/location lookup | External on-robot tool | Standard-library `Tool.__call__`, no package edits |

On-robot tools share the conversation app environment. Keep them standard-library-only and bound network
calls. Host heavy dependencies separately. Do not use a robot tool to expose broad private harness APIs.

## Current tool status

| Tool | Status |
|---|---|
| `today` | External tool; no injected hooks required. Last live date/time use verified before update |
| `location` | External tool; no injected hooks required. Provisional Cobham, Surrey, UK, with editable external config |
| `stay_silent` | Retired; local source removed and robot copy archived during earlier Phase 1. Its intended replacement is currently broken |
| `voice_look` | Unavailable on stock 1.1.0; requires removed lifecycle/motion hooks. Keep as historical prototype |
| `speech_control` | Unavailable on stock 1.1.0; requires removed input/output hooks. A saved quiet setting alone does not enforce quiet |
| Typed telemetry input | Uses public `conversation.say` RPC; no app edits. It is a user text turn requesting a reply |
| Search/weather/news replacement | Phase 2 authorised, plan only; no service or tool code exists yet |
| Look-around, alignment, scene memory | Phase 3 plan; local vision, coordinated fresh captures, single motion owner required |
| Reminders/calendar/email brain | Roadmap step 5; not built |

The last inspected active persona was `default` (Aiden, language auto), with today/location/voice_look/
speech_control deliberately enabled by Simon. These tools are not restricted to Marvin. Enabled-tool names
cannot make missing app hooks work. Existing stock search/weather remain in place.

## Installing ordinary external tools

The configured external directory is `/home/pollen/reachy_tools/`, selected through
`REACHY_MINI_EXTERNAL_TOOLS_DIRECTORY` in `/venvs/.env`, outside the installed app. Copy only actual tool modules
there; installers and diagnostics are not discoverable tools. Use supported profile/tool configuration interfaces
to enable ordinary tools. Keep master profiles in external storage; do not write installed package files.

External files/config survived the observed update. Future compatibility still depends on the supported tool API
and verifying that the app continues to discover the configured directory. App-local profiles/tool selections
also survived this update, but their long-term durability is not established. Loading a tool is not a functional
acceptance test, especially for the unsupported prototypes.

## Settings

`location` reads `~/.config/reachy_tools/location.json`. Fields are `place`, `region`, `country`, `country_code`,
`timezone`, optional paired `latitude`/`longitude`, and `provisional`. The default is explicitly provisional
Cobham, Surrey, United Kingdom, Europe/London, without guessed coordinates. `REACHY_TOOLS_STATE_DIR` overrides
the settings directory.

The historical quiet prototype stores `speech.json` in the same directory. That state survives independently
of the installed app, but stock 1.1.0 does not apply its gate. Do not infer that the robot will remain quiet from
this file. The prototype's in-memory gates, persistence and explicit resume semantics remain requirements for
a supported replacement.

## Retired patch paths

`install_voice_look_lifecycle.py` and `install_phase1.py` no longer write installed files. Imported installation
calls and CLI `--backup-dir` mode always refuse before filesystem access. `--check` is only a historical source
transformation: results state `retired: true` and `deployment_allowed: false`. It cannot certify compatibility
or authorise reinstallation. `deploy_phase1.py` always exits without file writes or robot calls.

This retirement applies to the local repository. Old scripts remain staged at
`/home/pollen/reachy_tools_deploy/voice-look-20261015-lifecycle/` and
`/home/pollen/reachy_tools_deploy/phase1-20261015/`; do not execute them. The earlier backups remain untouched
under `/home/pollen/reachy_tools_backups/`. `check_phase1_runtime.py` only transforms temporary copies and tests
patched classes; passing it does not prove stock-app compatibility or restored live behavior.

The historical voice prototype splits head/body travel within head reach ±35° and body −125/+140°, using the
app's move queue. Its retained idle pose, speech/motion pauses and automatic startup depended on patched internals.
Do not replace it with experimental `reachy_hub.look` running daemon motion alongside the conversation app.
Automatic face following remains deferred. No robot changes were made by the resumed audit.

Public-tool requirements remain in [public-tools.md](public-tools.md); Phase 2 architecture is in
[phase2.md](phase2.md). These plans must respect the supported interfaces identified by the audit.
