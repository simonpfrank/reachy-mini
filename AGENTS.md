# Reachy Mini Development Guide for AI Agents

This guide helps AI agents assist users in developing Reachy Mini applications.

---

## Agent Behavior

### FIRST: Check for agents.local.md

**Before doing anything else**, search for `agents.local.md` in the current directory:

```
IF agents.local.md exists:
    Read it immediately
    It contains user configuration and session context
ELSE:
    → Stop and ask Simon
```

This file stores the user's robot type, preferences, and setup status. Always check it first.

### Working Style

Simon is an experienced developer. We work as a team: discuss, agree, disagree, challenge. Near-production quality, pragmatic security, no gold-plating.

- **Short replies.** A few lines, bad news first. No essays.
- **Decisions:** one recommendation plus a yes/no question.
- **Flag on its own line, never buried:** deviations, security gaps, failing tests.
- **Decisions happen in conversation,** not in documents. Docs record what was agreed, with no excuses or history; Simon should never learn of a decision by reading a doc.
- **Nail it first time.** A feature is done when it is right. Later changes come from new learning, not from fixing a poor first build.

### Development Standards

- **Check for existing functionality** before adding any; never duplicate it.
- **Simplicity first.** No over-engineering, no stubs or placeholders, delete commented-out code. Max 500 lines per file, ~50 per function.
- **TDD.** Write the failing unit test first; every bug fix gets a regression test. Keep `docs/test_summary.md` current.
- **Unit tests** (`tests/unit/`) may mock. Aim for ~90% coverage; check it once per feature, not on every run.
- **Integration tests** (`tests/integration/`) **never mock** — no `unittest.mock`, `MagicMock`, `@patch` or `monkeypatch`. Write one wherever a real run would catch a failure before the live robot test (real APIs, real files, real daemon/app, real installed packages).
- **Test honesty.** No skips: a test that cannot run fails and is reported. Every failing test is yours to fix, including old ones; never call a failure "pre-existing" or unrelated.
- **Evidence.** Never claim a result without running it and showing the output. Say "NOT TESTED" when it wasn't.
- **After a rename, deletion or scope change,** grep for every reference and fix it, and fix all lint errors, including pre-existing ones.
- **Before reporting done,** check every item in the agreed plan has working code.
- **Security.** No `shell=True`; validate external input (paths, web content, tool arguments); secrets never in code or logs.

### Python First

This project is Python-first. Use a JS app only where it is clearly the more convenient way to do something, such as a browser UI.

| Flavour | Use for | Where it runs |
|---|---|---|
| **Python (default)** | Robot tools, on-robot control loops, motion sequencing, offline/LAN. | On the robot (CM4), optionally with a bundled web UI. |
| **JS app** | Browser UIs where JS is clearly more convenient. | Static HF Space; reaches the robot over WebRTC via the central signaling server. |

Both coexist — a Python app can bundle a browser UI, and a JS app can call the Python daemon's REST API.

---

**Python path (for developers):**

- **NEVER create app folders manually** — use `reachy-mini-app-assistant`.
- **If a command fails**, diagnose the cause from its output and fix it. Hand it to the user only when the fix needs their access, hardware or a decision.

```bash
# Default template (minimal app - good for most cases):
reachy-mini-app-assistant create <app_name> <path>

# Conversation template (for LLM integration, speech, making robot talk):
reachy-mini-app-assistant create --template conversation <app_name> <path>
```

Never publish (`--publish`, HF push) unless Simon asks.

Python apps put web UIs in `static/`. See `skills/create-app.md` for details.

### Keep Project Documentation in docs/

Keep project documentation, including implementation and component plans, under the repository's `docs/` directory, not in the repository root or source folders such as `robot_tools/` and `reachy_hub/`. Agent instruction files and local session configuration remain in their designated locations.

Functional requirements belong only in `docs/roadmap.md`. Unscheduled work belongs in its backlog.
Phase plans reference roadmap requirement IDs instead of repeating requirements. See `docs/README.md`
for document ownership; completed plans are consolidated and removed rather than kept as competing guidance.

### Agree, Then Build Autonomously

For any change (apps, tools, hub, scripts):
1. **Agree first.** Discuss, argue, agree. Then restate the agreed build list in a few bullets and wait for Simon's go. Record the agreed list in the relevant plan under `docs/`.
2. **Then build without check-ins.** Build only that list, write tests, and run `pytest`, `ruff check .` and `mypy` (no arguments; scope is set in `pyproject.toml`) until clean.
3. **Any change of direction: stop.** Before or during the build, if anything should differ from the agreed list, stop and raise it as its own question. Discuss, agree, then continue. Never substitute an approach or add behaviour on your own judgement.
4. **Verify, don't assert.** Check packages, APIs and behaviour against the installed source or by running them before stating them as fact.
5. **Hand back** for the live robot test, starting with "Built as agreed: yes" or "no, with these differences". End with a **To test** block: numbered steps in order, exact copy-paste commands, every restart needed (conversation app for `robot_tools/`; `scripts/hub.sh stop && scripts/hub.sh start` for `reachy_hub/`), and what Simon should see when it works.

**Hard limits, unless Simon asks:** never restart the live app, move motors, publish, `git push`, fork apps, patch installed packages or add a second motor writer.

### agents.local.md

Holds current setup facts only. Update it only when Simon asks.

---

## Robot Basics

**Reachy Mini** is a small expressive robot:

| Component | Description |
|-----------|-------------|
| **Head** | 6 DOF: x, y, z, roll, pitch, yaw (via Stewart platform) |
| **Body** | Rotation around vertical axis |
| **Antennas** | 2 motors, also usable as physical buttons |

**Hardware variants:**
- **Lite**: USB connection to laptop (full compute power)
- **Wireless**: Onboard CM4, connects via WiFi (limited compute)

---

## SDK Essentials

### Connection

```python
from reachy_mini import ReachyMini

with ReachyMini() as mini:
    # Your code here
```

### Two Motion Methods

| Method | Use when |
|--------|----------|
| `goto_target()` | **Default** - smooth interpolation for gestures that last at least 0.5s each |
| `set_target()` | Real-time control loops (e.g. tracking) at 10Hz+ |

### Before Writing Code

Before using an SDK or conversation-app API, read its installed source:
- Live (what the robot runs): `/venvs/apps_venv/lib/python3.12/site-packages/` (`reachy_mini`, `reachy_mini_conversation_app`)
- Dev: `.venv/lib/python3.12/site-packages/`

Paths below such as `ts/…`, `docs/source/…`, `examples/` and `RELEASE.md` are in the upstream [pollen-robotics/reachy_mini](https://github.com/pollen-robotics/reachy_mini) repository, not this project.

---

## Live/Web/JS Apps

> ### START HERE: [`ts/APP_CREATION_GUIDE.md`](ts/APP_CREATION_GUIDE.md)
>
> That guide is the **single source of truth** for building a Reachy Mini JS app: scaffolding, `public/icon.svg`, host shell, `sdk: static` deploy, `mountHost()` / `connectToHost()` API, local dev, FAQ, and the host ↔ embed architecture reference. Everything that used to live in `SPEC.md` and `APP_AUTHOR_GUIDE.md` is folded in.
>
> **SDK pin**: all three reference apps pin the latest stable `@pollen-robotics/reachy-mini-sdk` release from [npm](https://www.npmjs.com/package/@pollen-robotics/reachy-mini-sdk). Install with `npm install @pollen-robotics/reachy-mini-sdk@latest`. See [§10 SDK version pinning](ts/APP_CREATION_GUIDE.md#10-sdk-version-pinning).

Browser apps that drive a Reachy Mini over WebRTC, deployed as Hugging Face Spaces. Any HF-authenticated user opens the Space URL from anywhere and reaches any robot they have access to, through the central signaling server.

**What this flavour unlocks:**

- **Zero-install sharing** - the Space URL *is* the product. No LAN, no USB, no local daemon on the end-user side.
- **Off-robot compute** - work lives in the browser or the Space backend; the robot stays a pure IO device.
- **Bidirectional media** - robot camera/mic → browser; optionally user's mic → robot speaker.
- **Free OAuth + robot picker + top bar + leave flow** via the host shell (`@pollen-robotics/reachy-mini-sdk/host`). You only write the app's UI; use any framework you want inside the iframe.

> **Agent shortcut**: to scaffold a JS app fast (any author profile, "vibe coding"), read [`skills/create-js-app.md`](skills/create-js-app.md) first - it gives the golden path, the Always/Ask-First/Never boundaries, a copy-paste scaffold with animation best-practices pre-wired, and a definition of done. Use [`ts/APP_CREATION_GUIDE.md`](ts/APP_CREATION_GUIDE.md) as the deep reference it points into.

### Clone a reference app and trim

| Reference app | Stack | Use it for |
|---|---|---|
| [`pollen-robotics/reachy_mini_minimal_conversation`](https://huggingface.co/spaces/pollen-robotics/reachy_mini_minimal_conversation) | **Vanilla TS + Vite** | Smallest runtime, zero framework. |
| [`pollen-robotics/reachy_mini_emotions`](https://huggingface.co/spaces/pollen-robotics/reachy_mini_emotions) | React 19 + MUI 7 + Vite | UI-rich apps (rich components, theming, deep links). |
| [`pollen-robotics/reachy_mini_telepresence`](https://huggingface.co/spaces/pollen-robotics/reachy_mini_telepresence) | React 19 + MUI 7 + Vite | Camera / media-stream apps. |

These are kept in lockstep with every SDK release. **Mimicking them is the fastest path to a working app.** The 3-file contract, deploy steps, gotchas, and SDK pin all live in [`ts/APP_CREATION_GUIDE.md`](ts/APP_CREATION_GUIDE.md) - read it before scaffolding anything non-trivial.

> **One non-negotiable**: write the relevant plan under `docs/` first (same rule as Python apps) and wait for user approval before scaffolding.

### Mobile-first by default

Unless the user explicitly asks for a desktop-only / kiosk / dev-tool UI, **assume the app will be opened on a smartphone**. The Space URL is shareable, and "open this link on your phone and play with the robot" is the most common end-user flow. The reference apps are already responsive; cloning them gets you the mobile baseline for free - don't undo it by hardcoding desktop widths. Use the viewport meta with `width=device-width, initial-scale=1, viewport-fit=cover`, fluid `rem` / `vh` / `vw` units, touch hit targets ≥ 44×44 px, no hover-only affordances, and test in Chrome devtools' phone emulation before declaring the app done.

### SDK runtime API (motion + media + daemon-side playback)

Once `connectToHost()` resolves you get a live `ReachyMini` instance (`handle.reachy`). The full method/event reference lives in [`docs/source/SDK/javascript-sdk.md`](docs/source/SDK/javascript-sdk.md). The quick mental model:

- **Motion (degrees)**: `setHeadRpyDeg(r, p, y)`, `setAntennasDeg(right, left)`, `setBodyYawDeg(yaw)`. Atomic raw-units: `setTarget({ head?: number[16], antennas?: [rRad, lRad], body_yaw?: rad })`. The head matrix is in world frame, so `body_yaw` alone pivots the body under the head — to make the head follow the body, ship a `head` matrix in the same call with the body delta added to the head yaw. Use your own last-commanded buffer as the baseline, not telemetry (lags by one RTT).
- **Recorded-move playback (daemon-side, single-clock A/V sync)**: `playMove(motion, { audioBlob?, audioLeadMs? = -100 })` → `{finished|cancelled|error}`. `cancelMove()` stops mid-play. For record-time flows: `uploadAudio(blob)` returns `uploadId`, then `playUploadedAudio(uploadId)` resolves on the daemon's `started` broadcast (sync anchor). **Use these instead of hand-rolling `sendRaw` chunked uploads.**
- **Audio**: `setAudioMuted(bool)`, `setMicMuted(bool)`, `getVolume()` / `setVolume(0-100)`, `getMicrophoneVolume()` / `setMicrophoneVolume(0-100)`. `playSound(file)`.
- **Wake / torque**: `setMotorMode("enabled"|"disabled"|"gravity_compensation")`, `wakeUp()` / `gotoSleep()` / `isAwake()` / `ensureAwake()`.
- **Media flow**: `<video>` passed to `handle.media.attachVideo()` receives the **robot's** camera/mic over WebRTC (in a standalone `mountHost` app, use `reachy.attachVideo()`). Do NOT call `navigator.mediaDevices.getUserMedia()` to read robot media - that grabs the user's *own* laptop camera. Bidirectional audio is automatic when `enableMicrophone: true` is passed to `mountHost()`.
- **Events**: `connected`, `disconnected`, `robotsChanged`, `streaming`, `sessionStopped`, `sessionRejected` (robot busy - inspect `e.detail.activeApp`), `state` (every ~500 ms), `videoTrack`, `micSupported`, `error`.
- **Math utilities**: `rpyToMatrix`, `matrixToRpy`, `degToRad`, `radToDeg`.
- **Motion utilities** (subpath `@pollen-robotics/reachy-mini-sdk/animation`): `Pose` / `PartialPose` types, `INIT_POSE` safe-rest constant, `distanceBetweenPoses` (per-channel raw distance, head in magic-mm), `scaledDuration` → `{ duration, limiter, perChannel }` (synchronous client-side duration math, mirrors the daemon so you can sync audio cues without an RPC), `safelyReturnToPose(reachy)` (canonical `onLeave` one-liner: enables torque safely, computes scaled duration, dispatches goto to `INIT_POSE`, returns synchronously after dispatch), `installShutdownHandler(reachy)` (**standalone apps only** - host-shell apps use `handle.onLeave()` instead, mixing both double-fires the goto). Full recipe and anti-patterns: [§14 of the JS App Creation Guide](ts/APP_CREATION_GUIDE.md#14-robotics-best-practices).

**The host owns all teardown** - never call `reachy.stopSession()` yourself, register an `onLeave` callback instead. For the canonical `onLeave` body, see [§14.3](ts/APP_CREATION_GUIDE.md#143-safe-return-to-home-pose-safelyreturntopose).

### Alternative: bare HTML + CDN (no bundler)

For prototypes, learners, or anyone who'd rather not run `npm install`, a JS app can ship as a single `index.html` that imports the SDK from jsDelivr. No `package.json`, no `app_build_command`, no build step. Two sub-variants exist in the wild:

- **Modern (recommended for new apps)**: import the npm SDK from `cdn.jsdelivr.net/npm/@pollen-robotics/reachy-mini-sdk@<sha>/+esm` and use the host shell (`mountHost` + `connectToHost`). Same OAuth / picker / top bar / mode-B handoff as the bundled path - the host shell is identical, just loaded from the CDN instead of npm.
- **Legacy single-file (pre-host-shell)**: import the SDK bundle from `cdn.jsdelivr.net/gh/pollen-robotics/reachy_mini@<tag>/js/reachy-mini.js`, instantiate `new ReachyMini(...)` directly, render your own picker / gate / top bar. Useful when you want full control over the pre-session UI; otherwise prefer the modern variant.

The two variants are interoperable at the daemon level - they hit the same REST + WebRTC surface, so the motion API (`setTarget`, `setMotorMode`, `gotoTarget`, `setHeadRpyDeg`, `setAntennasDeg`, etc.) is identical on both. Migrating an existing legacy app to the modern host shell is a four-step swap that leaves motion code untouched.

Full recipe (frontmatter, CDN imports, scaling guidance, when to graduate to Vite, legacy -> modern migration): [§11.5 of the App Creation Guide](ts/APP_CREATION_GUIDE.md#115-alternative-bare-html--cdn-no-bundler).

---

## REST API

The daemon exposes an HTTP/WebSocket API at `http://{daemon-ip}:8000/api`.

> REST and the JS SDK's WebRTC data channel are **sibling transports** into the same `process_command()` backend on the daemon — WebRTC is a JSON subset (motion, audio, state). Commands you send from JS (`setHeadRpyDeg`, `setAntennasDeg`, …) reach the same handler as the corresponding REST endpoints; picking one transport or the other is a deployment choice, not a functional one.

- **Lite**: `localhost:8000` (daemon runs on your machine)
- **Wireless**: `reachy-mini.local:8000` or the robot's IP address

**Use REST API for:** Web UIs, non-Python clients, remote control, AI/LLM integration via HTTP. => Note: for the app to be discoverable, it must be a python app for now, this will change in a future release.

**Interactive docs:** `http://{daemon-ip}:8000/docs` (when daemon is running)

See `skills/rest-api.md` for details.

---

## Platform Compatibility

| Setup | Compute | Camera | Notes |
|-------|---------|--------|-------|
| **Lite** | Full (laptop) | Direct USB | Most flexible, best for dev |
| **Wireless (local)** | Limited (CM4) | Direct | Memory/CPU constrained |
| **Wireless (streamed)** | Full (laptop) | Via network | Some tracking quality loss |
| **Simulation** | Full | N/A | Can't test camera features |

---

## Safety Limits

| Joint | Range |
|-------|-------|
| Head pitch/roll | [-40, +40] degrees |
| Head yaw | [-180, +180] degrees |
| Body yaw | [-160, +160] degrees |
| Yaw delta (head - body) | Max 65° difference |

Gentle collisions with body are safe. SDK clamps values automatically.

For coordinate systems and architecture details, see `docs/source/SDK/core-concept.md`.

---

## Example Apps

| App | Key Patterns | Source |
|-----|--------------|--------|
| **reachy_mini_conversation_app** | AI integration, control loops, LLM tools | [GitHub](https://github.com/pollen-robotics/reachy_mini_conversation_app) |
| **marionette** | Recording motion, safe torque, HF dataset | [HF Space](https://huggingface.co/spaces/RemiFabre/marionette) |
| **fire_nation_attacked** | Head-as-controller, leaderboards, games | [HF Space](https://huggingface.co/spaces/RemiFabre/fire_nation_attacked) |
| **spaceship_game** | Head-as-joystick, antenna buttons | [HF Space](https://huggingface.co/spaces/apirrone/spaceship_game) |
| **reachy_mini_radio** | Antenna interaction pattern | [HF Space](https://huggingface.co/spaces/pollen-robotics/reachy_mini_radio) |
| **reachy_mini_simon** | No-GUI pattern (antenna to start) | [HF Space](https://huggingface.co/spaces/apirrone/reachy_mini_simon) |
| **hand_tracker_v2** | Camera-based control loop | [HF Space](https://huggingface.co/spaces/pollen-robotics/hand_tracker_v2) |
| **reachy_mini_dances_library** | Symbolic motion definition | [GitHub](https://github.com/pollen-robotics/reachy_mini_dances_library) |

---

## Documentation

| Topic | File |
|-------|------|
| **Build a JS app (single source of truth)** | **[`ts/APP_CREATION_GUIDE.md`](ts/APP_CREATION_GUIDE.md)** |
| JavaScript SDK runtime API (motion, events, daemon-side playback) | [`docs/source/SDK/javascript-sdk.md`](docs/source/SDK/javascript-sdk.md) |
| Quickstart | `docs/source/SDK/quickstart.md` |
| Python SDK | `docs/source/SDK/python-sdk.md` |
| Core concepts | `docs/source/SDK/core-concept.md` |
| Media architecture (WebRTC / GStreamer) | `docs/source/SDK/media-architecture.md` |
| AI integration | `docs/source/SDK/integration.md` |
| Troubleshooting | `docs/source/troubleshooting.md` |

For platform-specific guides (Lite, Wireless, Simulation), see `docs/source/platforms/`.

**Releasing the package:** see [`RELEASE.md`](RELEASE.md) — the `Release` workflow
(`workflow_dispatch`, modes `minor-prerelease` / `minor-release` / `patch-release`)
handles version bump, tag, PyPI publish, AI release notes, and downstream RC testing.

---

## Skills Reference

Read these files in `skills/` when you need detailed knowledge:

| Skill | When to use |
|-------|-------------|
| **setup-environment.md** | First session, no `agents.local.md` exists |
| **create-js-app.md** | Creating a browser/JS app (HF Space, host shell + SDK) - the agent-first golden path for vibe-coding shareable apps |
| **create-app.md** | Creating a new on-robot Python app with `reachy-mini-app-assistant` |
| **control-loops.md** | Building real-time reactive apps (tracking, games) |
| **motion-philosophy.md** | Choosing between `goto_target` and `set_target` |
| **safe-torque.md** | Enabling/disabling motors without jerky motion |
| **ai-integration.md** | Building LLM-powered apps |
| **symbolic-motion.md** | Defining motion mathematically (dances, rhythms) |
| **interaction-patterns.md** | Using antennas as buttons, head as controller |
| **debugging.md** | App crashes, connectivity issues, basic checks |
| **testing-apps.md** | Testing before delivery (sim vs physical) |
| **rest-api.md** | HTTP/WebSocket API for non-Python clients |
| **deep-dive-docs.md** | When to read full SDK documentation |

---

## Quick Reference

**Motor names:** `body_rotation`, `stewart_1-6`, `right_antenna`, `left_antenna`

**Interpolation methods:** `linear`, `minjerk` (default), `ease_in_out`, `cartoon`

**Emotions library:**
```python
from reachy_mini.motion.recorded_move import RecordedMoves
moves = RecordedMoves("pollen-robotics/reachy-mini-emotions-library")
mini.play_move(moves.get("happy"), initial_goto_duration=1.0)
```

---

## Community

- **App guide**: https://huggingface.co/blog/pollen-robotics/make-and-publish-your-reachy-mini-apps
- **Source code**: https://github.com/pollen-robotics/reachy_mini
- **Community apps**: https://huggingface.co/spaces?q=reachy_mini
- **Discord**: https://discord.gg/Y7FgMqHsub
