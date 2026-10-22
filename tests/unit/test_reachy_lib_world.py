"""reachy_lib.world: boxes become directions, and duplicates across overlapping photos and passes merge."""

import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[2] / "robot_tools"
W, H, HFOV = 1280, 720, 87.0


@pytest.fixture
def world(monkeypatch):
    monkeypatch.syspath_prepend(str(TOOLS))
    for name in ("reachy_lib.world", "reachy_lib.storage", "reachy_lib"):
        sys.modules.pop(name, None)
    from reachy_lib import world as module

    return module


def seen(world, label, box, heading=0.0, score=0.8, tier="now", photo=0):
    """One detection, as the world model receives it: the box in the photo plus the pose the photo was taken at."""
    angles = world.box_angles(box, heading, W, H, HFOV)
    return world.Observation(label, score, tier, photo, angles)


def merged(world, observations, ran=("now",), tolerance=3.0, overlap=0.5):
    return world.merge(observations, ran, tolerance, overlap)


def test_a_box_in_the_middle_is_straight_ahead_of_the_camera(world):
    a = world.box_angles((600, 300, 680, 420), 30.0, W, H, HFOV)
    assert (a.left + a.right) / 2 == pytest.approx(30.0, abs=0.01) and a.left > 30 > a.right
    assert (a.top + a.bottom) / 2 == pytest.approx(0.0, abs=0.01)


def test_the_photo_edge_is_half_the_field_of_view_away(world):
    a = world.box_angles((1200, 0, 1280, 720), 0.0, W, H, 90.0)  # a 90 degree lens: the right edge is 45 degrees
    assert a.right == pytest.approx(-45.0, abs=0.01)  # right of the camera axis is a lower bearing (left is positive)
    assert a.top == pytest.approx(29.36, abs=0.01) and a.bottom == pytest.approx(-29.36, abs=0.01)


def test_an_object_to_the_right_has_a_lower_bearing_than_the_heading(world):
    a = world.box_angles((1000, 300, 1100, 420), 10.0, W, H, HFOV)
    assert a.right < a.left < 10.0


def test_the_same_bottle_in_two_overlapping_photos_is_one_object(world):
    # photo 0 at heading 0 sees it at the right of the frame; photo 1 at heading -30 sees it near the left
    first = seen(world, "bottle", (1100, 300, 1160, 420), heading=0.0, photo=0)
    centre = (first.angles.left + first.angles.right) / 2
    second_box = None
    for x in range(0, 1200, 2):  # find where that direction lands in the second photo
        trial = world.box_angles((x, 300, x + 60, 420), -30.0, W, H, HFOV)
        if abs((trial.left + trial.right) / 2 - centre) < 0.7:
            second_box = (x, 300, x + 60, 420)
            break
    assert second_box is not None
    second = seen(world, "bottle", second_box, heading=-30.0, photo=1)
    objects = merged(world, [first, second])
    assert len(objects) == 1 and objects[0]["photos"] == [0, 1]


def test_two_bottles_in_different_places_stay_two(world):
    left_one = seen(world, "bottle", (100, 300, 160, 420))
    right_one = seen(world, "bottle", (1000, 300, 1060, 420))
    assert len(merged(world, [left_one, right_one])) == 2


def test_different_things_in_the_same_place_stay_separate(world):
    box = (600, 300, 680, 420)
    assert len(merged(world, [seen(world, "bottle", box), seen(world, "cup", box)])) == 2


def test_two_passes_seeing_the_same_thing_make_one_object_known_to_both(world):
    box = (600, 300, 680, 420)
    nano = seen(world, "bottle", box, score=0.5, tier="now")
    big = seen(world, "bottle", box, score=0.8, tier="after")
    [obj] = merged(world, [nano, big], ran=("now", "after"))
    assert obj["tiers"] == ["now", "after"] and obj["best_score"] == 0.8 and obj["confirmed"] is True


def test_something_only_the_weaker_pass_saw_is_not_confirmed_once_the_stronger_pass_ran(world):
    nano_only = seen(world, "tv", (100, 100, 200, 200), tier="now")
    big_only = seen(world, "bottle", (600, 300, 680, 420), tier="after")
    by_label = {o["label"]: o for o in merged(world, [nano_only, big_only], ran=("now", "after"))}
    assert by_label["tv"]["confirmed"] is False and by_label["bottle"]["confirmed"] is True


def test_when_only_the_first_pass_ran_what_it_saw_is_confirmed(world):
    [obj] = merged(world, [seen(world, "tv", (100, 100, 200, 200), tier="now")], ran=("now",))
    assert obj["confirmed"] is True


def test_the_tolerance_lets_nearby_boxes_that_do_not_quite_touch_merge(world):
    a = seen(world, "cup", (500, 300, 560, 360))
    b = seen(world, "cup", (562, 300, 622, 360))  # a gap of two pixels between them
    assert len(merged(world, [a, b], tolerance=0.0)) == 2
    assert len(merged(world, [a, b], tolerance=3.0)) == 1


def test_objects_at_the_same_bearing_but_far_apart_vertically_stay_separate(world):
    low = seen(world, "cup", (600, 500, 660, 560))
    high = seen(world, "cup", (600, 100, 660, 160))
    assert len(merged(world, [low, high])) == 2


def test_an_object_behind_the_robot_seen_from_both_ends_of_the_sweep_is_one_object(world):
    angles = world.Angles
    right_end = world.Observation("chair", 0.8, "now", 0, angles(left=-170.0, right=-182.0, top=5.0, bottom=-5.0))
    left_end = world.Observation("chair", 0.7, "now", 6, angles(left=190.0, right=178.0, top=5.0, bottom=-5.0))
    [obj] = merged(world, [right_end, left_end])
    assert obj["photos"] == [0, 6] and -180 < obj["bearing_deg"] <= 180


def test_the_strongest_observation_sets_the_reported_position(world):
    box = (600, 300, 680, 420)
    weak = seen(world, "bottle", box, heading=0.0, score=0.4, tier="now")
    strong = seen(world, "bottle", box, heading=1.0, score=0.9, tier="after")
    [obj] = merged(world, [weak, strong], ran=("now", "after"))
    assert obj["bearing_deg"] == pytest.approx(1.0, abs=0.2)


# --- the whole picture: coverage, progressive knowledge, stale objects, the file, and the plain-words description ---

from datetime import UTC, datetime, timedelta  # noqa: E402

START = datetime(2026, 10, 22, 12, 0, 0, tzinfo=UTC)


def found(label, box, score=0.8, tier="now"):
    return {"label": label, "score": score, "box": list(box), "tier": tier}


def build(world, photos, detections, status="complete", total=7, previous=None, ran=("now",), now=START):
    return world.build_world(
        photos=photos,
        detections=detections,
        ran_tiers=ran,
        status=status,
        total=total,
        scan_started=START.isoformat(),
        now=now.isoformat(),
        previous=previous,
        width=W,
        height=H,
        hfov_deg=HFOV,
        tolerance_deg=3.0,
        overlap=0.5,
    )


def test_the_picture_records_coverage_and_grows_as_photos_are_analysed(world):
    photos = [(0, 0.0), (1, 60.0), (2, 120.0)]
    one = build(world, photos[:1], {"now": {0: [found("bottle", (600, 300, 680, 420))]}}, status="scanning")
    assert one["coverage"] == {"photos_taken": 1, "photos_total": 7, "analysed": {"now": 1}}
    assert one["status"] == "scanning" and [o["label"] for o in one["objects"]] == ["bottle"]
    both = {0: [found("bottle", (600, 300, 680, 420))], 1: [found("person", (500, 100, 800, 700))]}
    two = build(world, photos[:2], {"now": both})
    assert sorted(o["label"] for o in two["objects"]) == ["bottle", "person"]
    assert two["coverage"]["analysed"] == {"now": 2}


def test_the_previous_picture_is_kept_as_stale_while_a_new_scan_runs(world):
    old = build(world, [(0, 0.0)], {"now": {0: [found("tv", (100, 100, 300, 300))]}})
    now = build(world, [], {}, status="scanning", previous=old, now=START + timedelta(minutes=30))
    assert now["objects"] == [] and [o["label"] for o in now["stale_objects"]] == ["tv"]
    assert now["stale_objects"][0]["stale"] is True and now["stale_objects"][0]["as_of"] == old["updated"]


def test_a_finished_scan_replaces_the_stale_picture(world):
    old = build(world, [(0, 0.0)], {"now": {0: [found("tv", (100, 100, 300, 300))]}})
    done = build(world, [(0, 0.0)], {"now": {0: []}}, previous=old, now=START + timedelta(minutes=30))
    assert done["stale_objects"] == []


def test_an_unfinished_scan_leaves_the_old_picture_as_stale(world):
    old = build(world, [(0, 0.0)], {"now": {0: [found("tv", (100, 100, 300, 300))]}})
    partial = build(world, [(0, 0.0)], {"now": {0: []}}, status="partial", previous=old)
    assert [o["label"] for o in partial["stale_objects"]] == ["tv"]


def test_a_picture_that_was_already_stale_keeps_its_original_date(world):
    first = build(world, [(0, 0.0)], {"now": {0: [found("tv", (100, 100, 300, 300))]}})
    second = build(world, [], {}, status="partial", previous=first, now=START + timedelta(hours=1))
    third = build(world, [], {}, status="scanning", previous=second, now=START + timedelta(hours=2))
    assert third["stale_objects"][0]["as_of"] == first["updated"]


def test_the_world_is_saved_owner_only_and_read_back(world, monkeypatch, tmp_path):
    monkeypatch.setenv("REACHY_TOOLS_SCAN_DIR", str(tmp_path / "scan"))
    assert world.read_world() is None
    picture = build(world, [(0, 0.0)], {"now": {0: [found("bottle", (600, 300, 680, 420))]}})
    world.write_world(picture)
    assert world.read_world() == picture
    assert (tmp_path / "scan" / "world.json").stat().st_mode & 0o777 == 0o600


def test_a_damaged_world_file_is_an_error_not_silence(world, monkeypatch, tmp_path):
    monkeypatch.setenv("REACHY_TOOLS_SCAN_DIR", str(tmp_path / "scan"))
    (tmp_path / "scan").mkdir()
    (tmp_path / "scan" / "world.json").write_text("{broken")
    with pytest.raises(ValueError, match="world.json"):
        world.read_world()


def describe(world, picture, minutes_later=1, stale_after=900):
    return world.describe(picture, START + timedelta(minutes=minutes_later), stale_after)


def test_with_no_scan_the_robot_says_it_has_not_looked(world):
    d = world.describe(None, START, 900)
    assert d["state"] == "no_scan" and d["objects"] == [] and "not scanned" in d["note"]


def test_a_recent_complete_scan_is_fresh_and_described_in_words(world):
    picture = build(world, [(0, 0.0)], {"now": {0: [found("bottle", (600, 300, 680, 420), score=0.9)]}}, total=1)
    d = describe(world, picture)
    assert d["state"] == "fresh" and d["age"] == "1 minute ago" and d["coverage"] == "1 of 1 directions"
    assert d["objects"] == [{"what": "bottle", "where": "straight ahead", "bearing_deg": 0, "how_sure": "sure"}]
    assert d["counts"] == {"bottle": 1}


def test_an_old_scan_is_stale_and_says_so(world):
    picture = build(world, [(0, 0.0)], {"now": {0: [found("bottle", (600, 300, 680, 420))]}}, total=1)
    d = describe(world, picture, minutes_later=120)
    assert d["state"] == "stale" and d["age"] == "2 hours ago" and "old" in d["note"] and "scan" in d["note"]


def test_a_scan_in_progress_and_an_unfinished_scan_are_described_as_incomplete(world):
    scanning = build(world, [(0, 0.0)], {"now": {0: []}}, status="scanning", total=7)
    assert describe(world, scanning)["state"] == "scanning" and "so far" in describe(world, scanning)["note"]
    partial = build(world, [(0, 0.0)], {"now": {0: []}}, status="partial", total=7)
    assert describe(world, partial)["state"] == "partial" and "did not finish" in describe(world, partial)["note"]


@pytest.mark.parametrize(
    ("bearing", "words"),
    [
        (0, "straight ahead"),
        (40, "ahead to the left"),
        (-40, "ahead to the right"),
        (90, "to the left"),
        (-90, "to the right"),
        (140, "behind to the left"),
        (-140, "behind to the right"),
        (175, "directly behind"),
        (-175, "directly behind"),
    ],
)
def test_bearings_are_put_in_plain_words(world, bearing, words):
    assert world.where_words(bearing, 0.0) == words


def test_high_and_low_things_are_said_to_be(world):
    assert world.where_words(0, 25.0) == "straight ahead, high up"
    assert world.where_words(0, -25.0) == "straight ahead, low down"


def test_certainty_follows_the_score_and_unconfirmed_things_are_only_possible(world):
    sure = found("person", (600, 100, 700, 600), score=0.9, tier="after")
    fairly = found("bottle", (100, 300, 160, 420), score=0.5, tier="after")
    guess = found("tv", (900, 100, 1000, 200), score=0.5, tier="now")  # only the weaker pass saw it
    detections = {"now": {0: [guess]}, "after": {0: [sure, fairly]}}
    picture = build(world, [(0, 0.0)], detections, total=1, ran=("now", "after"))
    d = describe(world, picture)
    assert {o["what"]: o["how_sure"] for o in d["objects"]} == {"person": "sure", "bottle": "fairly sure"}
    assert [o["what"] for o in d["possible"]] == ["tv"]


def test_objects_from_an_earlier_scan_are_listed_separately_as_old(world):
    old = build(world, [(0, 0.0)], {"now": {0: [found("tv", (100, 100, 300, 300))]}})
    mid_scan = build(world, [], {}, status="scanning", previous=old, now=START + timedelta(minutes=30))
    d = world.describe(mid_scan, START + timedelta(minutes=31), 900)
    assert d["objects"] == [] and [o["what"] for o in d["older"]] == ["tv"] and "earlier scan" in d["older"][0]["note"]


def test_an_object_from_days_ago_is_dated_in_days(world):
    old = build(world, [(0, 0.0)], {"now": {0: [found("tv", (100, 100, 300, 300))]}})
    mid_scan = build(world, [], {}, status="scanning", previous=old, now=START + timedelta(days=3, hours=5))
    d = world.describe(mid_scan, START + timedelta(days=3, hours=5, minutes=1), 900)
    assert d["older"][0]["note"] == "from an earlier scan, 3 days ago"
