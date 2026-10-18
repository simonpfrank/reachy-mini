# Architecture

Current implementation, 2026-10-16. Functional scope: [roadmap](roadmap.md).

```text
Robot microphone → conversation app → hosted HF speech backend (Pollen, "deployed" mode)
Robot speaker    ← conversation app ← reply audio
                         ├─ tools: today, location, speech_control (volume API), voice_look,
                         │         weather (Open-Meteo), news (BBC RSS/Tavily), web_search (Tavily), read_article (direct fetch)
                         └─ movement manager → daemon → motors

Hub ← app RPC + daemon state/log WebSockets → browser through SSH forwarding
```

| Component | Role |
|---|---|
| Daemon, robot port 8000 | Hardware APIs (including speaker volume), app launcher, state/log WebSockets and media |
| Official conversation app, port 7860 | Audio pipeline, tools, movement owner and `/rpc` |
| External tools (`robot_tools/`) | Model-callable, self-contained files; motion goes through the app's movement owner |
| Hub, 8710 | Aggregates events/state/logs and serves the dashboard |
| `profiles/` | Workspace link to the app's existing custom personalities |

No relay, installed app patches or second motion writer. `voice_look` reads the movement manager's
`_is_speaking` flag, which is internal and version-sensitive. STT, LLM and TTS run on the hosted backend.

## Telemetry interfaces

| Source | Interface |
|---|---|
| Conversation, transcripts, levels, turns | App `ws://127.0.0.1:7860/rpc` |
| Robot state, DoA, IMU | Daemon `/api/state/ws/full` with selected fields/frequencies |
| Tool activity, camera metadata, warnings/errors | Daemon `/logs/ws/daemon`; text format is version-sensitive |
| Typed user turns | Hub `/api/utterances` → app `conversation.say` |

The hub runs on Reachy: `scripts/hub.sh` serves it to the home network, or F5 serves it robot-only through
a forwarded port. RPC/log events describe
processing, not proof of audible output. WebRTC carries A/V, not tool-decision telemetry.
No battery-level API was found in the earlier inspection; voltage alone was not a usable estimate.

## Motion evidence

Recordings from 2026-10-14 are in `tests/data/`:

| Recording | Observation |
|---|---|
| `motion_sweep.json` | Body −134.6° to +150.9°; cables limit travel. Head stayed nearly aligned with body |
| `motion_look.json` | Head relative to body −36.5°/+38.9° for commanded ±40°; not a maximum-reach measurement |
| `motion_look4.json` | Up pitch −30.6°, down +28.3°; body drifted during looks |
| `motion_live_track.json` | Head moved +25.8°; DoA shifted +27.0° for the same source: head-relative frame |
| `motion_doa_frame.json` | Background speech merged into a 67-second hosted utterance; initial frame test inconclusive |

Current follower constants: body −125°/+140°, head reach 35°. DoA has front/back ambiguity.
Cable travel depends on placement; these are measured working margins, not universal hardware limits.
Other measured baselines and unresolved research are recorded in the roadmap and references.
