# Architecture (draft)

Personal organiser voiced by Reachy Mini Wireless. Extend Pollen's conversation app; do not fork it.

Current exception to the earlier implementation claims (2026-10-15): our voice-follow and persistent-quiet
prototypes depended on direct installed-app edits. Updating to 1.1.0 removed those hooks and broke both features.
Those patch paths are retired locally. A supported replacement has not been implemented; see
[update-compatibility.md](update-compatibility.md). Do not reapply patches or add a competing motor writer.

## Rule
Private data (email, messages, finances, faces) never leaves the Mac or the LAN.

## Parts
| Part | Where | What |
|---|---|---|
| Body | Reachy Pi | daemon, mic/camera/speaker, motion, wake word (only to wake from sleep) |
| Conversation app | Pi (or Mac while developing) | Pollen's app + our profiles and tools |
| Realtime backend | Mac (personal mode) or HF-hosted (general mode) | VAD + end-of-turn, STT, LLM, TTS (speech-to-speech, our STT/TTS plugged in) |
| Brain | Mac | agent-harness: reminders, calendar, email, letters |
| Capture | Siri / Echo | write-only "remind me" queue, no reads |

## Pi budget (CM4: 4 cores @1.5GHz, 4 GB RAM, 16 GB flash, no ML accelerator)
- Yes: daemon, 50 Hz motion, camera capture, wake word (asleep only), direction of arrival (from the mic array's own chip; angle 0 left, pi right, front/back ambiguous).
- Maybe (unmeasured): face detection a few fps.
- No: LLM, TTS, large STT, face/speaker recognition (Mac).

## Already measured (tts-chatterbox, M4 32 GB; see that repo's docs/)
- STT: Parakeet TDT 0.6B v2, 71 ms for a short clip, WER 3.0% on clean speech (room/TV noise not yet measured).
- TTS "Marvin" clone: Qwen3 Base (best voice, no tags) vs Chatterbox Turbo (tags, slower than real time). Decision open.
- Voice ID: ECAPA, MacBook mic, 1.5 s windows: Simon 0.31-0.71 vs TV <=0.11, threshold 0.39; 1 of 8 held-out Simon clips fell below. Promising, not final; redo on Reachy's mic.
- Not done: end-of-turn (Silero VAD + Smart Turn), Reachy TTS service PRD (interruption, interface).

## Modes
- **Personal**: backend on Mac, brain tools on, camera allowed.
- **General**: HF-hosted backend, no personal tools, camera off. Used when the Mac is off.

## Flow
voice -> backend -> conversation app -> `ask_brain` tool -> agent-harness (HTTP, short timeout)
Brain turns take 4-9 s: persona says "checking" first; on timeout it says the brain is offline.

## Our code (this repo)
- `profiles/`: persona + tool list (external profiles dir)
- `robot_tools/`: external tools; `today`/`location` use the ordinary tool interface. Voice/quiet prototypes
  require removed hooks and are currently unavailable. `ask_brain` is planned.
- Pollen's app and SDK installed as dependencies, so upstream updates flow in.
- `ask_brain` address is config, not hard-coded, so the brain can move between Macs.

## Later (each a swappable stage)
Voice ID gating, face ID, voice-directed head turn, TV/noise handling, custom voice (tts-chatterbox).

## Sensors (later)
- Sound direction: SDK `MediaManager.get_DoA()` already returns `(angle_rad, speech_detected)` from the XVF3800 mic array chip. Start there; raw 4-channel access only if that proves too coarse.
- Object detection for faster head turning: Raspberry Pi AI Camera (IMX500, runs small models on the sensor, so no Pi CPU). Replaces the stock camera (one CSI port); SDK auto-detects only "Reachy", "Arducam_12MP", "imx708". Optimisation after measuring stock head tracking. Frames stay local.

## Pose limits (low priority, safety)
- Head knocks the body in some poses. Limits live in the SDK's `hardware_config.yaml` (per-servo lower/upper, in motor ticks; stewart motors 1138-2958 etc.).
- Do NOT edit servo EEPROM/limits or use motor reflash for this. Fix in software: clamp head poses before sending them. First step: record which poses collide (roll/pitch/yaw/body yaw) and in which app.

## Reuse before build (from the Reachy app catalog, not yet reviewed in code)
- Dashboard: Domotick/reachy_web (Pollen removed the daemon's own dashboard). Review security first (LAN-open, streams mic).
- Sound direction: daemon `/api/state/doa`; blambert/doa-tracker, yzhsjtu/reachy-wheres-the-sound.
- Face detection: daemon-side YuNet (`/api/media/tracking/*`); EryriLabs/look_whos_talking fuses it with DoA.
- Face recognition: receptionist apps (check models; one uses OpenAI Realtime, which our rule excludes).
- Wake word: luisomoreau/hey_reachy_wake_word_detection, fcollonval/reachy_mini_wake_word.
- Local reference stack incl. sound-event classification (YAMNet): ravediamond/baby-reachy-mini-companion.

## Always-on options (not now)
- Intel Mac mini: keep macOS (brain tools need EventKit/Mail). No MLX, so no voice models or fast LLM. Needs supported macOS; lock down (FileVault, firewall, no internet exposure).
- Pi 5 (8 GB): capture queue + heartbeat only. Brain needs macOS until tools move to CalDAV/IMAP. Duplicates Siri -> To-Do for now.
- Echo: needs a public endpoint; defer. Write-only "remind me" if ever built.
- Synology DS215j: backups only, LAN only (end-of-life, too weak for compute).

## Unverified
- HF-hosted backend retention/logging terms.
- Connection mode switchable per profile (README shows it global).
- External tools dir works when app runs on the robot.
- App on Mac with robot as body only: audio routing (SDK has media server/WebRTC client, untested).
- Pi load and heat with the app running; face detection frame rate.
- Intel mini: model and macOS version.
- Whether harness tools can run without its LLM agent loop.

## Unverified (cont.)
- AI Camera (IMX500, same footprint as stock per Simon): connector matches Reachy's board, works on CM4, needs SDK/daemon changes to use it. Much later.
- DoA angle is relative to the array: need to know if it is mounted in the head (moves with it) or the body.
- Raw per-mic audio from the SDK (it exposes processed audio plus DoA).
- Who handles wake from sleep: conversation app has `go_to_sleep` but I found no wake-up path. Pi-side wake word may be ours.
- speech-to-speech accepts OpenAI-style `/v1/audio/transcriptions` and `/v1/audio/speech` endpoints (README); not tried with our Parakeet/Marvin wrapped as such. Streaming and interruption fit unknown.

## Where STT/LLM/TTS run
In the realtime backend, not in the conversation app or the daemon (the daemon is hardware only; the app moves audio, tools and motion).
Default backend is HF-hosted; personal mode swaps it for speech-to-speech on the Mac. That swap, and its latency test, is roadmap step 6 (`docs/roadmap.md`).
STT and TTS are already measured (tts-chatterbox), so step 6 measures only the LLM stage and end-to-end turn time.
