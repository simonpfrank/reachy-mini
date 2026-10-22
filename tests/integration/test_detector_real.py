"""The real model files through the real detector: every default model loads, runs and decodes. No mocks.

Needs the model files in the models folder (REACHY_TOOLS_MODELS_DIR, default ~/.local/share/reachy-tools/models):
yolox_nano.onnx, yolox_s.onnx, yolox_m.onnx and object_detection_nanodet_2022nov.onnx. It fails, saying which is
missing. A synthetic picture is used, because accuracy needs real photos, and those stay local (see docs/tools.md).
"""

import sys
import time
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "robot_tools"))

from reachy_lib import detection, detector  # noqa: E402

MODELS = detection.load_models()


def synthetic_photo() -> np.ndarray:
    """A 1280x720 colour picture with structure (gradient, blocks, noise) but nothing a model should call an object."""
    rng = np.random.default_rng(1)
    x = np.linspace(0, 255, 1280, dtype=np.float32)[None, :, None] * np.ones((720, 1, 3), dtype=np.float32)
    picture = x + rng.normal(0, 8, (720, 1280, 3))
    picture[200:500, 300:700] = (40, 90, 160)
    return np.clip(picture, 0, 255).astype(np.uint8)


def test_the_engine_is_installed() -> None:
    ready, reason = detector.engine_available()
    assert ready, reason


@pytest.mark.parametrize("name", list(MODELS))
def test_a_real_model_loads_runs_and_decodes_without_error(name: str) -> None:
    spec = MODELS[name]
    ready, reason = detection.availability(spec)
    assert ready, f"{reason}; copy it into {detection.model_path(spec).parent}"
    model = detector.Detector.load(spec, threads=1)
    started = time.perf_counter()
    found = model.detect(synthetic_photo())
    assert time.perf_counter() - started < 30  # a loose limit; real timings are measured on the robot
    for item in found:
        assert item.label in detector.COCO and 0.35 < item.score <= 1
        left, top, right, bottom = item.box
        assert right > left and bottom > top


def test_a_real_jpeg_round_trips_through_decode() -> None:
    import cv2

    ok, encoded = cv2.imencode(".jpg", synthetic_photo())
    assert ok
    picture = detector.decode_jpeg(encoded.tobytes())
    assert picture.shape == (720, 1280, 3)
    with pytest.raises(ValueError):
        detector.decode_jpeg(b"not a jpeg")
