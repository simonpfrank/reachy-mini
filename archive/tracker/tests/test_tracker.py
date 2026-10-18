import json
from pathlib import Path

from reachy_hub.tracker import SoundSample, VoiceTracker

DATA = Path(__file__).parent.parent / "data"
RATE = 20  # samples per second


def _feed(tracker: VoiceTracker, seconds: float, angle: float | None, speech_every: int = 1, start: float = 0.0,
          head: float = 0.0) -> list:
    """Feed seconds of samples at 20 Hz; speech flag on for every Nth sample."""
    decisions = []
    for i in range(int(seconds * RATE)):
        sample = SoundSample(start + i / RATE, angle, speech=(i % speech_every == 0) and angle is not None)
        decision = tracker.feed(sample, head)
        if decision:
            decisions.append(decision)
    return decisions


def test_silence_gives_no_decision() -> None:
    assert _feed(VoiceTracker(), 5, angle=None) == []


def test_steady_talker_on_the_right_gives_a_clamped_right_turn() -> None:
    decisions = _feed(VoiceTracker(), 3, angle=145.0)
    assert len(decisions) == 1
    d = decisions[0]
    assert d.offset_deg == -55.0
    assert d.target_head_deg == -35.0  # head-only reach is capped
    assert d.clamped is True


def test_short_burst_like_a_clap_is_ignored() -> None:
    tracker = VoiceTracker()
    assert _feed(tracker, 0.2, angle=100.0) == []
    assert _feed(tracker, 3, angle=None, start=0.2) == []


def test_flickering_source_still_counts_when_steady() -> None:
    decisions = _feed(VoiceTracker(), 4, angle=77.0, speech_every=3)  # speech on about a third of the time
    assert [d.offset_deg for d in decisions] == [13.0]
    assert decisions[0].target_head_deg == 13.0 and decisions[0].clamped is False


def test_source_already_in_front_gives_no_decision() -> None:
    assert _feed(VoiceTracker(), 3, angle=86.0) == []


def test_wandering_angles_are_not_a_steady_source() -> None:
    tracker = VoiceTracker()
    decisions = []
    for i in range(80):
        angle = 40.0 if (i // 5) % 2 else 140.0  # jumps between left and right every quarter second
        decision = tracker.feed(SoundSample(i / RATE, angle, True), 0.0)
        if decision:
            decisions.append(decision)
    assert decisions == []


def test_cooldown_blocks_a_second_turn_then_allows_it() -> None:
    tracker = VoiceTracker(cooldown_s=3.0)
    first = _feed(tracker, 2.0, angle=145.0)  # decision about 1.2 s in (a full window); cooldown until about 4.2 s
    assert len(first) == 1
    assert _feed(tracker, 2.0, angle=60.0, start=2.0) == []  # a new source qualifies from about 3.5 s, still blocked
    later = _feed(tracker, 3, angle=60.0, start=4.3)
    assert len(later) == 1 and later[0].offset_deg == 30.0


def test_turn_is_relative_to_where_the_head_already_points() -> None:
    decisions = _feed(VoiceTracker(), 3, angle=110.0, head=20.0)
    assert decisions[0].target_head_deg == 0.0 and decisions[0].offset_deg == -20.0


def test_strict_threshold_ignores_a_flickering_background_talker() -> None:
    strict = VoiceTracker(min_speech_fraction=0.5)
    assert _feed(strict, 6, angle=77.0, speech_every=3) == []
    assert len(_feed(strict, 3, angle=145.0, start=6.0)) == 1


def _recording() -> list[dict]:
    return json.loads((DATA / "motion_doa_frame.json").read_text())


def _replay(tracker: VoiceTracker) -> list:
    rows = _recording()
    t0 = rows[0]["t"]
    out = []
    for r in rows:
        angle = r["doa_rad"] * 57.29578 if isinstance(r["doa_rad"], float) else None
        head = r["head_yaw_deg"] - r["body_yaw_deg"]
        decision = tracker.feed(SoundSample(r["t"] - t0, angle, bool(r["speech"])), head)
        if decision:
            out.append(decision)
    return out


def test_recording_loose_rule_follows_video_and_voice_but_respects_cooldown_and_cap() -> None:
    decisions = _replay(VoiceTracker())
    assert len(decisions) >= 4
    assert all(abs(d.target_head_deg) <= 35.0 for d in decisions)
    assert all(b.t - a.t >= 3.0 for a, b in zip(decisions, decisions[1:], strict=False))
    assert any(d.source_deg > 120 for d in decisions) and any(60 < d.source_deg < 90 for d in decisions)


def test_recording_strict_rule_reacts_only_to_the_shouting() -> None:
    decisions = _replay(VoiceTracker(min_speech_fraction=0.6))
    assert decisions and all(d.source_deg > 120 for d in decisions)


def test_stray_readings_do_not_hide_a_dominant_source() -> None:
    tracker = VoiceTracker()
    decisions = []
    for i in range(60):
        angle = 70.0 if i % 4 == 0 else 150.0  # a steady talker at 150 with a stray reading every fourth sample
        decision = tracker.feed(SoundSample(i / RATE, angle, True), 0.0)
        if decision:
            decisions.append(decision)
    assert len(decisions) == 1 and decisions[0].source_deg == 150.0 and decisions[0].offset_deg == -60.0


def test_two_equal_sources_are_not_one_dominant_source() -> None:
    tracker = VoiceTracker()
    decisions = []
    for i in range(120):
        angle = 60.0 if (i // 2) % 2 else 140.0  # two talkers alternating every 0.1 s
        decision = tracker.feed(SoundSample(i / RATE, angle, True), 0.0)
        if decision:
            decisions.append(decision)
    assert decisions == []
