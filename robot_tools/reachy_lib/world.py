"""What the robot knows about the room, built from what its detectors found. Everything here is anonymous.

A detection box becomes directions (a bearing from the robot's front, and how far above or below the camera axis).
The same object seen in overlapping photos, or by two passes, is merged into one. Nothing here can hold a name or an
identity: an object is a label, a place and how sure we are.

Bearings are degrees, positive to the robot's left, as the SDK does. The lens is treated as a pinhole: the real
lens's distortion (large at the edges) is not corrected yet, so bearings near a photo's edge are a few degrees off.
"""

import json
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .storage import scan_dir, write_private

TIER_RANK = {"now": 1, "after": 2, "remote": 3}  # a higher pass is the stronger model
WORLD_FILE = "world.json"
MAX_LISTED = 30  # the most objects described in words at once


@dataclass(frozen=True)
class Angles:
    """A box as directions, in degrees.

    ``left`` and ``right`` are the bearings of its edges (positive is to the robot's left); ``top`` and ``bottom``
    are how far its edges are above (positive) or below the camera axis.
    """

    left: float
    right: float
    top: float
    bottom: float


@dataclass(frozen=True)
class Observation:
    """One detection in one photo: what, how sure, which pass found it, which photo, and where."""

    label: str
    score: float
    tier: str
    photo: int
    angles: Angles


def box_angles(
    box: tuple[float, float, float, float], heading_deg: float, width: int, height: int, hfov_deg: float
) -> Angles:
    """The directions a box covers, for a photo taken with the camera pointing at ``heading_deg``.

    Args:
        box: Left, top, right, bottom in the photo's pixels.
        heading_deg: Where the camera pointed: body yaw plus head yaw, positive to the left.
        width: Photo width in pixels.
        height: Photo height in pixels.
        hfov_deg: The camera's horizontal field of view.
    """
    focal = (width / 2) / math.tan(math.radians(hfov_deg) / 2)  # in pixels; square pixels, so the same both ways
    x1, y1, x2, y2 = box

    def bearing(x: float) -> float:
        return heading_deg - math.degrees(math.atan((x - width / 2) / focal))  # right of centre is a lower bearing

    def vertical(y: float) -> float:
        return math.degrees(math.atan((height / 2 - y) / focal))

    return Angles(left=bearing(x1), right=bearing(x2), top=vertical(y1), bottom=vertical(y2))


def merge(
    observations: list[Observation], ran_tiers: tuple[str, ...], tolerance_deg: float, overlap: float
) -> list[dict[str, Any]]:
    """Merge observations of the same thing into objects, strongest pass first.

    Two observations are the same object if they have the same label and their direction boxes, each widened by
    ``tolerance_deg`` (parallax and lens error), overlap by at least ``overlap`` of the smaller one. Bearings wrap
    around, so something behind the robot seen from both ends of the sweep is one object.

    Args:
        observations: Every detection from every photo and pass.
        ran_tiers: The passes that produced results; an object is confirmed if the strongest of these saw it.
        tolerance_deg: Extra angle allowed between two views of one object.
        overlap: Fraction of the smaller box that two views must share, above 0 up to 1.

    Returns:
        JSON-ready objects: label, bearing and edges, vertical position, best score, the passes that saw it, the
        photos it appears in, and whether it is confirmed.
    """
    top_rank = max((TIER_RANK[tier] for tier in ran_tiers), default=0)
    ordered = sorted(observations, key=lambda o: (-TIER_RANK[o.tier], -o.score))
    clusters: list[list[Observation]] = []
    for item in ordered:
        for members in clusters:
            if members[0].label == item.label and _same_object(members[0], item, tolerance_deg, overlap):
                members.append(item)
                break
        else:
            clusters.append([item])
    return [_as_object(members, top_rank) for members in clusters]


def _same_object(a: Observation, b: Observation, tolerance: float, overlap: float) -> bool:
    a_low, a_high = a.angles.right - tolerance, a.angles.left + tolerance
    b_low, b_high = b.angles.right - tolerance, b.angles.left + tolerance
    shared_width = max(min(a_high, b_high + turn) - max(a_low, b_low + turn) for turn in (-360.0, 0.0, 360.0))
    shared_height = min(a.angles.top, b.angles.top) - max(a.angles.bottom, b.angles.bottom) + 2 * tolerance
    if shared_width <= 0 or shared_height <= 0:
        return False
    area_a = (a_high - a_low) * (a.angles.top - a.angles.bottom + 2 * tolerance)
    area_b = (b_high - b_low) * (b.angles.top - b.angles.bottom + 2 * tolerance)
    return shared_width * shared_height / min(area_a, area_b) >= overlap


def _wrap(bearing: float) -> float:
    return (bearing + 180.0) % 360.0 - 180.0


def _as_object(members: list[Observation], top_rank: int) -> dict[str, Any]:
    lead = members[0]  # the strongest pass, then the highest score: it sets where the object is
    tiers = sorted({m.tier for m in members}, key=TIER_RANK.__getitem__)
    return {
        "label": lead.label,
        "bearing_deg": round(_wrap((lead.angles.left + lead.angles.right) / 2), 1),
        "left_deg": round(_wrap(lead.angles.left), 1),
        "right_deg": round(_wrap(lead.angles.right), 1),
        "vertical_deg": round((lead.angles.top + lead.angles.bottom) / 2, 1),
        "best_score": round(max(m.score for m in members), 3),
        "tiers": tiers,
        "photos": sorted({m.photo for m in members}),
        "confirmed": TIER_RANK[tiers[-1]] >= top_rank,
    }


def build_world(
    *,
    photos: list[tuple[int, float]],
    detections: dict[str, dict[int, list[dict[str, Any]]]],
    ran_tiers: tuple[str, ...],
    status: str,
    total: int,
    scan_started: str,
    now: str,
    previous: dict[str, Any] | None,
    width: int,
    height: int,
    hfov_deg: float,
    tolerance_deg: float,
    overlap: float,
) -> dict[str, Any]:
    """The robot's picture of the room from a scan, as it stands now (call again as each result arrives).

    Args:
        photos: (index, heading in degrees) for every photo taken so far.
        detections: Pass name to photo index to that photo's detections (label, score, box, tier).
        ran_tiers: The passes that produced results.
        status: ``scanning``, ``complete`` or ``partial`` (the scan ended early).
        total: How many photos the whole scan will have.
        scan_started: When this scan began (ISO text).
        now: The time of this update (ISO text).
        previous: The picture from before this scan, or None. Its objects are kept as stale until this scan completes.
        width: Photo width in pixels.
        height: Photo height in pixels.
        hfov_deg: Camera horizontal field of view.
        tolerance_deg: Angle allowed between two views of one object.
        overlap: Share of the smaller direction box two views must share to be one object.

    Returns:
        A JSON-ready dict: status, coverage, merged objects, and the older picture's objects flagged stale.
    """
    headings = dict(photos)
    observations = [
        _observe(item, index, headings[index], width, height, hfov_deg)
        for per_photo in detections.values()
        for index, items in per_photo.items()
        if index in headings
        for item in items
    ]
    return {
        "scan_started": scan_started,
        "updated": now,
        "status": status,
        "coverage": {
            "photos_taken": len(photos),
            "photos_total": total,
            "analysed": {tier: len(per_photo) for tier, per_photo in detections.items() if per_photo},
        },
        "objects": merge(observations, ran_tiers, tolerance_deg, overlap),
        "stale_objects": [] if status == "complete" else _carry_over(previous),
    }


def _observe(
    item: dict[str, Any], photo: int, heading: float, width: int, height: int, hfov_deg: float
) -> Observation:
    x1, y1, x2, y2 = item["box"]
    angles = box_angles((x1, y1, x2, y2), heading, width, height, hfov_deg)
    return Observation(item["label"], item["score"], item["tier"], photo, angles)


def _carry_over(previous: dict[str, Any] | None) -> list[dict[str, Any]]:
    """The last picture's objects, flagged stale and dated; ones that were already stale keep their own date."""
    if not previous:
        return []
    carried = [{**item, "stale": True, "as_of": previous["updated"]} for item in previous.get("objects", [])]
    return carried + list(previous.get("stale_objects", []))


def read_world() -> dict[str, Any] | None:
    """The saved picture, or None if there has never been a scan.

    Raises:
        ValueError: The file exists but is damaged. That is reported, not hidden as "no scan".
    """
    path = scan_dir() / WORLD_FILE
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except ValueError as error:
        raise ValueError(f"{WORLD_FILE} is damaged ({error})") from error
    if not isinstance(data, dict):
        raise ValueError(f"{WORLD_FILE} is damaged (it is not an object)")
    return data


def write_world(world: dict[str, Any]) -> None:
    """Save the picture beside the photos, owner-only, replacing the last one."""
    write_private(scan_dir(), {WORLD_FILE: json.dumps(world, indent=2).encode()})


def where_words(bearing_deg: float, vertical_deg: float) -> str:
    """A direction in plain words, as the robot would say it: relative to the robot's own front."""
    side = "left" if bearing_deg > 0 else "right"
    size = abs(bearing_deg)
    if size <= 20:
        words = "straight ahead"
    elif size <= 60:
        words = f"ahead to the {side}"
    elif size <= 120:
        words = f"to the {side}"
    elif size <= 160:
        words = f"behind to the {side}"
    else:
        words = "directly behind"
    if vertical_deg > 15:
        words += ", high up"
    elif vertical_deg < -15:
        words += ", low down"
    return words


def _seconds_since(stamp: str, now: datetime) -> float:
    return (now - datetime.fromisoformat(stamp)).total_seconds()


def _age(seconds: float) -> str:
    if seconds < 45:
        return "a few seconds ago"
    minutes = round(seconds / 60)
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    hours = round(seconds / 3600)
    if hours < 48:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    return f"{round(seconds / 86400)} days ago"


def _how_sure(score: float) -> str:
    return "sure" if score >= 0.7 else "fairly sure" if score >= 0.45 else "possible"


def _entry(item: dict[str, Any], how_sure: str | None) -> dict[str, Any]:
    entry = {
        "what": item["label"],
        "where": where_words(item["bearing_deg"], item["vertical_deg"]),
        "bearing_deg": int(round(item["bearing_deg"] / 5) * 5),
        "how_sure": how_sure or _how_sure(item["best_score"]),
    }
    if "note" in item:
        entry["note"] = item["note"]
    return entry


def _listed(objects: list[dict[str, Any]], how_sure: str | None = None) -> list[dict[str, Any]]:
    strongest_first = sorted(objects, key=lambda o: -o["best_score"])[:MAX_LISTED]
    return [_entry(item, how_sure) for item in strongest_first]


def describe(world: dict[str, Any] | None, now: datetime, stale_after_s: float) -> dict[str, Any]:
    """The picture in plain words for the LLM: anonymous objects, where, how sure, and how old and complete it is.

    Args:
        world: The saved picture, or None.
        now: The time to measure the age against.
        stale_after_s: Older than this and the picture is called stale.

    Returns:
        Plain data only (text, numbers, lists, dicts): state, age, coverage, objects, possible, older, counts, note.
    """
    if world is None:
        return {
            "state": "no_scan", "objects": [], "possible": [], "older": [], "counts": {},
            "note": "I have not scanned the room yet.",
        }  # fmt: skip
    age_s = _seconds_since(world["updated"], now)
    coverage = world["coverage"]
    analysed = max(coverage["analysed"].values(), default=0)
    progress = f"{analysed} of {coverage['photos_total']} directions"
    if world["status"] == "scanning":
        state, note = "scanning", f"A scan is in progress: {progress} analysed so far, so the picture is incomplete."
    elif world["status"] == "partial":
        state, note = "partial", f"The last scan did not finish ({progress}), so the picture is incomplete."
    elif age_s > stale_after_s:
        state = "stale"
        note = f"This is old information (scanned {_age(age_s)}); the room may have changed. Say so and offer to scan."
    else:
        state, note = "fresh", f"Scanned {_age(age_s)}. Directions are relative to the robot's own front."
    confirmed = [o for o in world["objects"] if o["confirmed"]]
    counts: dict[str, int] = {}
    for item in confirmed:
        counts[item["label"]] = counts.get(item["label"], 0) + 1
    older = [
        {**item, "note": "from an earlier scan, " + _age(_seconds_since(item["as_of"], now))}
        for item in world.get("stale_objects", [])
    ]
    unconfirmed = [o for o in world["objects"] if not o["confirmed"]]
    return {
        "state": state,
        "age": _age(age_s),
        "coverage": progress,
        "objects": _listed(confirmed),
        "possible": _listed(unconfirmed, "not confirmed by the stronger check"),
        "older": _listed(older),
        "counts": counts,
        "note": note,
    }
