# Reuse from reachy-mini-aide

Aide was an experiment (simulator only; robot arrived later). Paths are in `../reachy-mini-aide/`. Most design notes are "discussed, not built". We take ideas and small assets, not the pipeline, state machine or `llm_tools/` (agent-harness is the brain).

| Take | Where | Use at |
|---|---|---|
| Voice confirm for write actions: read-only needs no confirm; create/send/delete need yes/no; send reads message back; delete double-confirms | `docs/design-notes.md` "Confirmation / Permission Flow" | Step 5: agent-harness approvals need a spoken version |
| Pre-recorded clips ("one moment", "got it", "didn't catch that", tones), picked at random so they don't repeat | `sounds/`, `scripts/generate_sounds.py`, `audio/sound_library.py`, `motion/pick.py` | Step 4: mask the 4-9 s brain delay. Regenerate in the final voice at step 8 |
| Barge-in: stop speech, cancel gesture (`cancel_move`), return to listening; separate case for stop-while-listening | design-notes "STOP / Barge-In" | Step 2/7: check what Pollen's app already does first |
| Wake word facts: Edge Impulse "Hey Reachy" model, 24 kHz, 0.5 s windows, one classifier thread only, cooldown, hand the mic to STT while conversing, pick the `.eim` per platform | design-notes "Hey Reachy Wake Word" | Wake from sleep (Pi). Note: our wake word is for sleep only, aide used it every turn |
| Gate wake word with sound direction (reject if direction is clearly background/TV) | design-notes "DOA" | Step 9 (TV/noise) |
| Sound -> head turns -> camera finds face -> engaged; on a head-mounted camera use a feedback loop (P-controller), not position mapping | design-notes "Session Learnings" | Step 3. Daemon tracking and `look_whos_talking` already do this: reuse theirs |
| SDK audio facts: use `reachy_mini.media` only; samples are stereo float32 16 kHz, variable chunks; buffer 1280 samples (80 ms); `mono = raw.mean(axis=1)` | design-notes "Media / Sensors" | Anything that touches audio |
| Small UX items: "I didn't catch that" (one retry), first-run self-introduction, touch/knock reaction via IMU, volume by voice, "what do you see" | design-notes "UX Polish" | Step 2 persona, later |
| Interaction initiation: reactive (wake) vs proactive (greet on recognised face), face enrolment first | design-notes "Interaction Initiation Models" | Step 9 |
| Memory and identity layers, proactive scheduler | design-notes "Memory & Identity", "Proactive Scheduler" | Brain side (agent-harness has memory and nudge) |
| Pluggable STT/TTS/LLM provider seam, fallback chain | `conversation/provider.py`, `stt_service.py`, `tts_service.py`, `reachy_voice_service/` | Step 8: same idea as OpenAI-style endpoints |
| CalDAV calendar client (no macOS dependency) | `llm_tools/caldav_client.py` | Brain on a Pi/other box (roadmap step 10) |
| Pluggable sensor interface with simulator fakes | `sensors/interface.py` | Testing without the robot |
| macOS GStreamer/`gi` install pain and fixes (brew packages, segfault fixed by reboot, symlinks) | `install-issues.md` | Only if we run SDK media on the Mac |

## Leave behind
- HSM state machine, `main.py`, conversation pipeline (OpenAI/HF), `llm_tools/`: replaced by Pollen's app + agent-harness.
- `moves.py`, `dance_emotion_moves.py`, `speech_tapper.py`, `head_wobbler.py`: Pollen's app and the daemon already provide dances, emotions and speech wobble.
