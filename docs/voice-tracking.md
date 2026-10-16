# Voice tracking design (roadmap 3a, with 3b)

Current status (2026-10-15): these are historical design/experiment notes. The later voice-follow prototype
depended on unsupported app patches; update to 1.1.0 removed them and following is currently broken. Local patch
deployment is retired. Do not run experimental daemon motion alongside the conversation app as a repair.
See [update-compatibility.md](update-compatibility.md). Automatic face following remains deferred; TV following
when the room is empty was subsequently accepted, so the ambient/face decisions below are not current scope.

Draft 2026-10-14. Decisions are Simon's unless marked open. Everything starts as a dry run (dashboard shows what it *would* do; no motors driven by us).

## Decision order
1. **Speech heard:** mic chip says speech, direction steady for about 1 s. A burst (clap, door slam) never qualifies, so there is nothing to turn back from.
2. **Known TV/ambient direction?** Ignore.
3. **Face visible?** Centre on the face (3b).
4. **Otherwise** trust the speech direction and turn there.

## What "ambient" really means
Not "TV" but **speech not addressed to the robot**: TV, radio, a Teams/Zoom meeting (including Simon talking to the screen), a conversation in another room. The AI's judgement (answered vs `stay_silent`) is the main signal; direction rules are the backup. Experiments fake all of these with a phone or a YouTube video.
Open: a deliberate "meeting mode" (voice command or dashboard button): no tracking and no replies until Simon ends it. Links to step 7 modes.

## Learning what is ambient (the TV)
- AI calls `stay_silent` for speech from a direction -> mark it ambient. AI answers -> mark it a person.
- Simon says "that's the telly" -> tool marks the current direction.
- Persistent speech from one direction for minutes with no conversation -> ambient.
- Map is keyed to the robot's base frame and reset at start-up and whenever the IMU shows the robot was lifted or moved.
- Open: a turn that finds no face within about 3 s also marks the direction "not a person". TV faces may fool face checks; voice ID (step 9) is the real fix.

## Behaviour
- **Graded:** weak evidence = small eased head glance (20 deg or less); sustained evidence = full turn.
- **Cooldown:** 2-3 s after every move (head still moving, motor noise, avoids ping-pong). Also freeze while the robot speaks, plus 0.5 s.
- **No return to centre:** stay at the last speech direction. Only unwind if the body is within about 10 deg of its limit and it is quiet.
- **Two sides of a conversation:** follow whoever speaks (switch after a steady ~1 s plus cooldown). Addressed-to-robot is known from the AI (answered vs `stay_silent`). Open: whether to follow two humans talking to each other ("observer" mode).
- Cap each decision at about 90 deg and the total excursion from the placement heading, so a source behind cannot make it spiral.
- Front/back: sound direction covers a half circle only (0 left, 90 front or back, 180 right). Assume front.

## Head and body
- Pollen's table: head yaw +-180, body yaw +-160, max 65 deg head-vs-body difference. `sweep_look` commands +-162 body.
- **Measured 2026-10-14** (`sweep_look`, 20 Hz, `tests/data/motion_sweep.json`): body yaw reached **-134.6 to +150.9 deg (span 285.5)**; positive is left. Asymmetric and short of the commanded +-162, and it held about 1 s at each extreme as coded, so these are real stops. Simon: **the cables prevent the final turn**, so they are physical and probably depend on how the cable lies (may differ between placements and over time: re-measure after the robot is moved). The reported head yaw is the head's heading from the base, so it includes the body's turn; head minus body is the head's own turn, and it stayed between -8.7 and +4.2 (about zero). So in the sweep **only the body turned; the head did not yaw on its own** (matches what Simon saw). The head-only reach beyond 40 deg is **not yet measured**.
- **Head-only turn measured 2026-10-14** (`move_head` left/right, `tests/data/motion_look.json`): head minus body reached **-36.5 / +38.9 deg** while the body stayed within -1.5 / +6.9. The tool commands **+-40 deg** (up/down pitch +-30), so this shows the head follows a commanded 40 deg accurately, **not** its maximum reach. The head's reach (Pollen: 65) is still unmeasured: it needs a commanded turn past 40.
- **Four looks measured 2026-10-14** (`tests/data/motion_look4.json`): up pitch -30.6, down +28.3 (negative pitch = up), left +35.2, right -36.1 (head relative to body). The head reaches about 90% of a commanded angle. The body drifted to -10 deg during the looks although the tool recentres it: the app's movement code moves the body a little; understand before wiring our tracking.
- **Lesson:** the hosted voice detection ignores very short utterances ("look up"): use full sentences. Relevant to wake word design (step 9).
- Blind arc behind the robot: about 75 deg wide, centred about 188 deg (from +151 round to -135).
- Working limits for planning: body +140 / -125 (10 deg margin) until the stops are understood.
- **Never command past the working limits** and never rely on the stop to halt a move. `sweep_look` commands +-162, past both stops, every run (possible motor strain/cable wear: check motor errors/temperature during a sweep; our `look_around` must stay inside the safe range).
- Unwind towards centre when idle, so the cable does not rest at an extreme.
- Slight change: head yaws. Genuine person and the turn needs the body: body turns and the head recentres relative to it.
- Keep a margin inside the body limit. Body moves are slow (about 3 s for 160 deg): only on sustained evidence.

## Unknowns to test (dry run)
1. Real head/body yaw limits: body done (see above). Head-only reach still to measure: ask Marvin to look left, right, up, down while recording; watch head minus body. (The sound direction stayed fixed during the sweep, speech flag false throughout, so it said nothing about its frame.)
2. Is the sound direction relative to the head or the base? Fixed phone speech, ask Marvin to look left/right, record direction plus yaws.
3. TV stand-in (phone or YouTube speech, steady, 5 min): does ambient learning ignore it?
4. Simon talking from left, right, front.
5. Claps and door slams: zero turns.
6. Simon plus the stand-in together.
7. How the conversation app's own head control works (`moves.py`), so we cooperate rather than fight it.

## Result 2026-10-14: first frame test (inconclusive) and a key lesson
`tests/data/motion_doa_frame.json`: YouTube talk on a screen about 70 deg left, Simon about 80 deg right, speaker muted. Head barely moved (one look left), so head-relative vs base-relative is **still open**; redo with the app stopped and the head moved through the daemon (no voice commands needed).
- Simon's shouted voice read 143-153 deg with the speech flag on (higher = further right: consistent with 80 deg right; scale confirmed).
- The video at 70 deg left did NOT read about 20 deg: the steady background reading was about 77 deg all the time. Unclear whether the chip locked onto the video or something else.
- **Continuous background speech merged everything into one 67 s "utterance"** (hosted voice detection never saw a pause); commands only got through after 3 shouted attempts right next to the robot; Marvin also acted on the video (`move_head`). The hosted pipeline cannot cope with a TV/meeting: our own gating (3a now, wake word and voice ID at step 9) is a core requirement.
- The dashboard's level bar is rms x 6 capped at 1.0, so 1.0 means loud, not clipped.

## Result 2026-10-14: tracker v0 dry run (60 s, YouTube about 70 deg left, Simon about 80 deg right)
- Rule changed from "all speech angles within 20 deg" (too brittle: stray readings) to "densest 20 deg cluster must hold >= 30% of the window and >= 60% of speech samples", plus no decision on a window less than 80% full.
- The video read a steady 67-72 deg, so the tracker would turn the head about 20 deg left (a decision every 3 s while the head stays put in a dry run). Simon's voice read 143 deg, a 53 deg right turn capped at 35.
- Estimates vs readings: screen said to be 70 deg left reads about 21 deg left of front; Simon (80 deg right) reads 53 deg right of front. Either the estimates are generous or the scale is compressed toward the front. Settle by eye in the live run: does the head face the screen after turning?

## Result 2026-10-14: the frame is HEAD-RELATIVE (measured)
`tests/data/motion_live_track.json` (live run, head-only, YouTube plus Simon): with the head at -32.6 deg the video read a steady 21-22 deg; after the head returned to -6.8 deg it read 48 deg. The head moved +25.8 deg and the reading moved +27.0 deg. The video's implied direction in the base frame is 35-36 deg left of front in both phases. So the sound direction is relative to the head: turning toward a source brings its reading to 90.
- The first live run stopped turning because my frame check compared Simon's voice (122 deg, before the turn) with the video (20 deg, after): different sources. Fixed: the verdict now accounts for the head's own move and says "inconclusive" for a mismatch; the runner no longer halts.
- Head-only cap (35 deg) meant a source more than 35 deg off front could not be fully reached: the body is needed next (opt-in `--body`, working limits +140/-125, head recentres).

## Dashboard work this needs
Held "last voice from X deg, n s ago"; "would turn to ..." decisions with reason; ambient map; moved/lifted detection from the IMU; recording of direction with head and body yaw.
