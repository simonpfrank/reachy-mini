"""On-device tool: take a private photo and keep it on the robot with the pose it was taken at.

The first piece of the room scan (roadmap 4c). Speech wobble is off while the frame is taken. The head is not
levelled: commanding roll 0 did not make it level (roadmap 4c, pose correction), so the measured pose is recorded
instead. The photo and its pose replace the previous one-off photo in the camera directory, owner-only. Nothing is
sent to the model or off the robot: use Pollen's ``camera`` tool to have a picture described.
"""

import asyncio
import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
from reachy_mini.utils.rotation import Rotation  # type: ignore[import-untyped]
from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies

LOG = logging.getLogger(__name__)
SETTLE_S = 0.2  # let the wobble offset die away after it is switched off

Pose = npt.NDArray[np.float64]


def camera_dir() -> Path:
    """Where photos are kept: on the robot, outside the repository."""
    return Path(os.environ.get("REACHY_TOOLS_CAMERA_DIR", "~/.local/share/reachy-tools/camera")).expanduser()


def head_angles(pose: Pose) -> tuple[float, float, float]:
    """(roll, pitch, yaw) in degrees, in the SDK's ``create_head_pose`` convention."""
    roll, pitch, yaw = Rotation.from_matrix(pose[:3, :3]).as_euler("xyz", degrees=True)
    return float(roll), float(pitch), float(yaw)


def save(jpeg: bytes, meta: dict[str, Any]) -> None:
    """Replace photo.jpg and photo.json, owner-only."""
    directory = camera_dir()
    directory.mkdir(parents=True, exist_ok=True)
    directory.chmod(0o700)
    for name, data in (("photo.jpg", jpeg), ("photo.json", json.dumps(meta, indent=2).encode())):
        temporary = directory / f".{name}.tmp"
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "wb") as file:
            file.write(data)
        temporary.replace(directory / name)


async def take_photo(deps: ToolDependencies) -> dict[str, Any]:
    """Take one frame with speech wobble off and save it with its measured pose."""
    if deps.movement_manager.get_status().get("queue_size"):
        return {"error": "The robot is moving; try the photo again in a moment."}
    deps.reachy_mini.disable_wobbling()  # speech wobble moves the head up to ±2.25° roll while audio plays
    try:
        await asyncio.sleep(SETTLE_S)
        jpeg = await asyncio.to_thread(deps.reachy_mini.media.get_frame_jpeg)
    finally:
        deps.reachy_mini.enable_wobbling()
    if not jpeg:
        return {"error": "No frame came from the camera, so no photo was taken."}
    shot = deps.reachy_mini.get_current_head_pose()
    shot_joints, _ = deps.reachy_mini.get_current_joint_positions()
    roll, pitch, yaw = head_angles(shot)
    meta = {
        "time": datetime.now(UTC).isoformat(timespec="milliseconds"),
        "head_deg": {"roll": round(roll, 2), "pitch": round(pitch, 2), "yaw": round(yaw, 2)},
        "body_yaw_deg": round(float(np.degrees(float(shot_joints[0]))), 2),
        "resolution": list(deps.reachy_mini.media.camera.resolution),
    }
    await asyncio.to_thread(save, jpeg, meta)
    LOG.info("photo saved head=%s body=%.1f", meta["head_deg"], meta["body_yaw_deg"])
    return {
        "saved": True,
        "note": "Photo saved privately on the robot for later analysis; you cannot see it. To describe what is in "
        "view, use the camera tool.",
    }


class Photo(Tool):  # type: ignore[misc]
    """Take a private photo kept on the robot."""

    name = "photo"
    description = (
        "Take a private photo with the robot's camera and keep it on the robot, with the head and body angles it "
        "was taken at, for later analysis such as room scans. You cannot see the photo. To look at or describe "
        "something, use the camera tool instead."
    )
    parameters_schema: dict[str, Any] = {"type": "object", "properties": {}, "required": []}

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> dict[str, Any]:
        """Take and save the photo, logging failures."""
        try:
            return await take_photo(deps)
        except Exception as error:
            LOG.warning("photo failed: %s", error)
            raise
