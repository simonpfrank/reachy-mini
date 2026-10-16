# Telemetry and hooks

Sources: Pollen docs (core concepts, media architecture, lifecycle contract, cloud-backend consumer, motors diagnosis), the SDK's `jsonrpc_server.py`, and the conversation app source.

Update audit (2026-10-15): the hub uses public app/daemon interfaces without package edits. Our separate
voice-follow and quiet prototypes did edit the app and broke after update to 1.1.0; they are not examples of
supported hooks. Their installers are retired locally. See [update-compatibility.md](update-compatibility.md).

## 1. How Reachy is put together
- **Daemon** (on the robot) owns the motors, camera, mic and speaker. API on port 8000: REST plus WebSockets.
- **App** (on the robot, one at a time), e.g. the conversation app. Every app can serve a JSON-RPC WebSocket at `/rpc`. This is Pollen's designed channel for UIs and clients: ask the app for status, call its methods, and receive the events it pushes. The same channel is reachable remotely through the daemon.
- **Media**: apps on the robot read camera and mic directly. Off-robot clients get them over WebRTC. Browsers connect through Pollen's relay, which allows **one viewer per robot**.
- **Voice backend** (speech-to-text, LLM, text-to-speech): HF-hosted now, on the Mac from roadmap step 6.

## 2. What we watch, and where it comes from
| Area | What | Source | Verified |
|---|---|---|---|
| Body | Motor mode, head pose, joints, antennas, body yaw | Daemon `/api/state/ws/full` (or REST `/api/state/full`) | REST yes, WebSocket not yet |
| Motor health | Control-loop rate, read/write time, error count, hardware errors (e.g. "Overload Error") | `/api/daemon/status`; hardware errors in the daemon log | Status yes. Motor temperature/current: not found in the API |
| Movement | Moves running, face-tracking target | `/api/move/running`, `/api/media/tracking/face` | Yes |
| Sensors | Sound direction + speech flag, IMU | State WebSocket (`with_doa`), `/api/state/doa`, `/api/state/imu` | Direction yes, IMU not tried |
| App lifecycle | Which app, starting/running/error, app slot | `/api/apps/current-app-status`, `/api/daemon/robot-app-lock-status` | Yes |
| Conversation | Phase, turn (listening/speaking), transcripts both sides, sound level both sides, activity | Conversation app `/rpc`: events `conversation.phase`, `.turn`, `.transcript`, `.level`, `.activity`; method `conversation.status` | Live from the Mac (2026-10-13, Mac app open, no clash): `conversation.status` and `conversation.level` (~12/s) yes; turn/transcript need speech |
| Errors | Exceptions and warnings from daemon and apps (app output goes into the daemon log) | Daemon `/logs/ws/daemon` (no `/api` prefix; Wireless only; plain text lines) | Yes, connected from the Mac |
| System | WiFi signal, CPU, temperature, throttling | SSH, every few seconds | Yes |
| Voice timing (step 6) | Speech-to-text, LLM, first-audio times per turn | speech-to-speech latency log | Later |
| Live audio/video | Hear and see what the robot does | WebRTC | Later, only for a watch/listen panel |
| Battery / power LED | Charge level, power LED colour | Not available: no API (checked SDK, docs; Simon checked further). Motor supply voltage is read only inside the daemon, and a LiFePO4 voltage curve is too flat to estimate charge anyway | Not possible |

## 3. Design
- **Hub on the Mac**: one small Python service that connects to the sources above and serves one dashboard page on localhost. Nothing is installed on the robot for telemetry.
- **Structured events plus logs**: `/rpc` supplies conversation events; logs also supply tool call/results,
  camera-image metadata and errors. Those log-derived fields depend on message formatting across app updates.
- **Not WebRTC for telemetry**: it carries audio/video, not what the app decided; the relay allows one viewer; sound level already arrives on `/rpc`.

```
Robot:  daemon :8000  (state WS, REST, log WS)        conversation app :7860 /rpc (events)
             \                                            /
Mac:          hub  --->  dashboard (localhost)   <--- SSH stats (WiFi, CPU, temp)
```

## 4. How our features plug into the conversation app (no fork)
| Need | Mechanism |
|---|---|
| Personality, instructions, voice, which tools | Profile folder (`profile.md`) |
| New abilities, e.g. `ask_brain` | External Python `Tool.__call__`; directory configured through `/venvs/.env`. No external-tool startup/shutdown or persistent audio gate in the inspected stock 1.1.0 source |
| Submit text or stop current speech | App `/rpc`: `conversation.say` submits a user text turn and requests a response; `conversation.interrupt` stops the current response, requiring an active backend. Neither sets persistent quiet |
| Microphone input | `conversation.mic` mutes input; it cannot keep listening for a spoken resume while suppressing output |
| Move the robot (look, emotions) | External tools should use the app's movement owner; standalone daemon API is available for isolated control. A second daemon writer alongside the app is not a production integration |
| Our own events in the timeline | Our tools report to the hub |
| Ruled out | Private-data tools through hosted MCP; forks, installed-app edits and runtime monkey-patching. Public-info Space tools remain an available integration |

## 5. Current status
Hub/dashboard and typed input have already been delivered. The resumed update audit makes no robot changes.
Voice following and persistent quiet still require a supported repair; telemetry is not an audio or motion gate.
