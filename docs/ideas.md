# References and reuse notes

Research sources, not a second backlog. All proposed capabilities are in [roadmap](roadmap.md).
Links were recorded in earlier investigations; no fresh upstream review was performed during this tidy-up.
Read code/licences before reuse.

| Source | Technical notes / inspection status |
|---|---|
| [Reachy Mini Reactions](https://huggingface.co/spaces/8bitkick/reachy_mini_reactions) | Apache-2.0; local VAD, Moonshine, MiniLM, Supertonic/Piper. Lite/Pi 5; mic script uses 2886:001a, ours 38fb:1001 |
| Supertonic (`pip install supertonic`) | Local after model download; cloning unverified |
| [Reachy Web](https://huggingface.co/spaces/Domotick/reachy_web) | Greps only, no full audit/run. Daemon control, camera, twin, moves, logs, WiFi/OTA, mic meter, LED eyes; no auth found |
| [Look Who's Talking](https://huggingface.co/spaces/EryriLabs/look_whos_talking) | YuNet + DoA; numpy gaze implementation |
| [DoA tracker](https://huggingface.co/spaces/blambert/doa-tracker), [Where's the Sound](https://huggingface.co/spaces/yzhsjtu/reachy-wheres-the-sound) | Short DoA polling examples |
| [Edge Impulse wake word](https://huggingface.co/spaces/luisomoreau/hey_reachy_wake_word_detection), [openWakeWord](https://huggingface.co/spaces/fcollonval/reachy_mini_wake_word) | Platform-specific models; aide notes describe 24 kHz, 0.5-second windows |
| [Baby Reachy companion](https://huggingface.co/spaces/ravediamond/baby-reachy-mini-companion) | Ollama, Faster-Whisper, Silero, YOLO, YAMNet; tests/lint/typing noted |
| [ElevenLabs app](https://mindmodelai-reachy-mini-elevenlabs.static.hf.space/index.html) | Cloud service; not a private-data backend |
| [Local conversation fork](https://github.com/dwain-barnes/reachy_mini_conversation_app_local) | Kokoro; not reviewed |
| [Qwen3-TTS](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice) | Hosted app exposed nine presets in earlier inspection; custom voice work needs a different backend |
| [Reachy chatbox](https://huggingface.co/spaces/pollen-robotics/reachy-mini-chatbox) | User-supplied reference; unreviewed |
| [TrekCore audio](https://www.trekcore.com/audio/) | User-supplied sound library reference; licence/use not reviewed |
| XVF3800 parameters | SDK `media/audio_control_utils.py`; older daemon parameter-read route returned Not Found, apply untested |
| Community eyes | `reachy_web/eyes.py`: RP2350 USB “Reachy Eyes” (no licence found) and ESP32 `rmeyes.local` (Apache-2.0) |

## Local reuse sources

- `../agent-harness/agent_harness/tools.py`: Tavily `web_search` and readable `web_fetch`; importing the whole
  module brings dependencies. Phase 2 adapts the narrow HTTP/extraction code, not the agent/session API.
- `../reachy-mini-aide/`: simulator experiment, not the live stack. Useful source references:
  `docs/design-notes.md`, `sounds/`, `scripts/generate_sounds.py`, `audio/sound_library.py`, `motion/pick.py`,
  `llm_tools/caldav_client.py`, `sensors/interface.py`, `install-issues.md`, `first_app/` control panel.
  Its state machine, pipeline and llm_tools are not the chosen app/brain implementation.
- `tts-chatterbox`: earlier M4/32-GB measurements: Parakeet TDT 0.6B v2 71 ms short-clip STT, 3.0% clean WER;
  Qwen3 Base voice versus slower Chatterbox Turbo; ECAPA Simon 0.31–0.71 versus TV ≤0.11, threshold 0.39,
  one of eight held-out Simon clips below threshold. MacBook microphone, not Reachy's. Room/TV STT unmeasured.
- Aide media notes: stereo float32, 16 kHz, variable chunks, 1280-sample/80-ms buffer; verify against the installed SDK.

## Hardware research context

CM4: four 1.5-GHz cores, 4 GB RAM, 16 GB flash, no ML accelerator. Face-detection performance unmeasured.
IMX500 replaces the stock camera on the single CSI connector; CM4/SDK compatibility was not established.
Intel Mac mini lacks MLX; EventKit/Mail require macOS. Pi 5/CalDAV is a possible alternative.
Synology DS215j was considered for LAN backups, not compute. These are research notes, not deployment decisions.
