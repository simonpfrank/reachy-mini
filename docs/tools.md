# Where a tool lives

Our tools for Marvin, and how to decide where each one runs. Answer the questions in order; the first "yes" wins.

| # | Question | If yes |
|---|---|---|
| 1 | Does it touch personal data (reminders, calendar, email, messages, contacts, faces)? | **Mac brain** (roadmap step 5, via `ask_brain`, agent-harness). Never the cloud |
| 2 | Does it need the robot's hardware (camera frames, motors, mics, IMU)? | **On the robot** (external tools folder) |
| 3 | Does it need a secret (API key) or mildly personal settings (home town)? | **Private HF Space** (MCP tool, secrets as Space settings) |
| 4 | Is it heavy (big model, slow third-party calls) or useful to others? | **HF Space** (private, or public if sharable) |
| 5 | Otherwise (small, no network or open no-key services) | **On the robot** |

## The three places

| | On the robot | HF Space (MCP) | Mac brain |
|---|---|---|---|
| How the app finds it | `REACHY_MINI_EXTERNAL_TOOLS_DIRECTORY` (set in `/venvs/.env`) + tool name in the persona's list | `tool_spaces.add` (must be `https://*.hf.space`) + name in the persona's list | One on-robot tool (`ask_brain`) calling the Mac |
| Speed | Fastest, no extra hop | Extra hop; free Spaces sleep (slow first call) | Agent turns take seconds |
| Rules | Standard library only (shares the app's environment; extra packages could break the app). Short timeouts: a slow tool stalls the app | Keep personal data out | Approvals for anything that changes data |
| Robot changes | Copy the file | None | Copy `ask_brain` |

## Deploying robot tools
Files in `robot_tools/` -> robot `/home/pollen/reachy_tools/` (scp). `/venvs/.env` holds `REACHY_MINI_EXTERNAL_TOOLS_DIRECTORY=/home/pollen/reachy_tools` (outside the app and daemon installs, so updates keep it). Add the tool name to the persona's `default_tools`, copy the profile, then restart the conversation app (stop + start via the daemon): the app reads `.env` only at start-up. Check the log for "✓ Loaded external tool: <name>".

## Tool list

| Tool | Place | Why | Status |
|---|---|---|---|
| `today` (date, weekday, spoken time; UK) | Robot | Q5: tiny, no network. Fixes "2024" searches | Live 2026-10-13; 16 tests |
| `stay_silent` (end turn with no speech; `needs_response = False`) | Robot | Q5: stops "staying silent" being said aloud | Live 2026-10-13; 3 tests |
| `look_around` (frames left/centre/right, small, stitched) | Robot | Q2: camera + motors | Idea (roadmap side track) |
| Web search (replace Pollen's) | Private Space | Q3: search API key | To do |
| Weather (Open-Meteo, Cobham fixed) | Private Space, or robot | Q3 if home location counts as personal; otherwise Q5 (no key) | To decide |
| Reminders, calendar, email | Mac brain | Q1 | Step 5 |
