"""reachy_lib.detector: preprocessing, decoding and overlap-merging, checked against outputs built by hand."""

import ast
import sys
from pathlib import Path

import numpy as np
import pytest

TOOLS = Path(__file__).resolve().parents[2] / "robot_tools"


@pytest.fixture
def det(monkeypatch):
    monkeypatch.syspath_prepend(str(TOOLS))
    for name in ("reachy_lib.detector", "reachy_lib.detection", "reachy_lib"):
        sys.modules.pop(name, None)
    from reachy_lib import detection, detector

    return type("Det", (), {"detector": detector, "detection": detection})


class FakeRuntime:
    def __init__(self, outputs):
        self.outputs, self.blobs = outputs, []

    def run(self, blob):
        self.blobs.append(blob)
        return self.outputs


def yolox_output(size, cell_x, cell_y, stride=8, score=0.9, cls=0):
    """A model output with one confident box: centre ((0.5 + x) * stride, (0.5 + y) * stride), 4 cells wide."""
    cells = sum((size // s) ** 2 for s in (8, 16, 32))
    out = np.zeros((1, cells, 85), dtype=np.float32)
    index = cell_y * (size // stride) + cell_x  # stride 8 comes first in the output
    out[0, index, 0:2] = 0.5
    out[0, index, 2:4] = np.log(4.0)
    out[0, index, 4] = score
    out[0, index, 5 + cls] = 0.95
    return [out]


def nanodet_output(size, cell_x, cell_y, stride=8):
    """Six outputs (three class maps, three box maps) with one confident anchor whose four distances are 4 * stride."""
    counts = [(size // s) ** 2 for s in (8, 16, 32)]
    classes = [np.zeros((1, c, 80), dtype=np.float32) for c in counts]
    boxes = [np.zeros((1, c, 32), dtype=np.float32) for c in counts]
    index = cell_y * (size // stride) + cell_x
    classes[0][0, index, 0] = 0.9
    boxes[0][0, index].reshape(4, 8)[:, 4] = 50.0  # one-hot at bin 4 after the softmax
    return classes + boxes


def test_letterbox_shrinks_to_fit_and_pads_the_bottom_and_right(det):
    image = np.full((720, 1280, 3), 200, dtype=np.uint8)
    canvas, scale = det.detector.letterbox(image, 640, 114)
    assert scale == 0.5 and canvas.shape == (640, 640, 3)
    assert (canvas[:360] == 200).all() and (canvas[360:] == 114).all()


def test_overlapping_boxes_of_one_class_merge_but_other_classes_stay(det):
    boxes = np.array([[0, 0, 100, 100], [5, 5, 105, 105], [0, 0, 100, 100]], dtype=np.float32)
    scores = np.array([0.6, 0.9, 0.5], dtype=np.float32)
    classes = np.array([1, 1, 2])
    assert det.detector.nms(boxes, scores, classes, 0.5) == [1, 2]  # the stronger of the pair, and the other class


def test_yolox_output_is_decoded_to_a_box_in_the_input_square(det):
    boxes, scores, classes = det.detector.decode_yolox(yolox_output(416, 5, 3), 416, conf=0.35, iou=0.5)
    assert len(boxes) == 1 and classes[0] == 0 and scores[0] == pytest.approx(0.855)
    assert boxes[0] == pytest.approx([28, 12, 60, 44])


def test_nanodet_output_is_decoded_whatever_order_the_maps_arrive_in(det):
    outputs = nanodet_output(416, 5, 3)
    for ordered in (outputs, outputs[::-1]):
        boxes, scores, classes = det.detector.decode_nanodet(ordered, 416, conf=0.35, iou=0.5)
        assert len(boxes) == 1 and classes[0] == 0 and scores[0] == pytest.approx(0.9)
        assert boxes[0] == pytest.approx([11.5, 0, 75.5, 59.5])  # the top edge is clipped to the picture


def test_a_detector_returns_labelled_boxes_in_the_original_photo_pixels(det):
    spec = det.detection.DEFAULT_MODELS["yolox_s"]  # 640 input
    detector = det.detector.Detector(spec, FakeRuntime(yolox_output(640, 10, 5)))
    found = detector.detect(np.zeros((720, 1280, 3), dtype=np.uint8))  # shrunk by 0.5 on the way in
    assert [d.label for d in found] == ["person"] and found[0].score == pytest.approx(0.855)
    assert found[0].box == pytest.approx((136, 56, 200, 120))  # the 640-square box (68, 28, 100, 60), doubled


def test_the_detector_feeds_the_model_a_float_blob_of_the_right_shape(det):
    runtime = FakeRuntime(yolox_output(416, 5, 3))
    det.detector.Detector(det.detection.DEFAULT_MODELS["yolox_nano"], runtime).detect(
        np.zeros((100, 200, 3), dtype=np.uint8)
    )
    assert runtime.blobs[0].shape == (1, 3, 416, 416) and runtime.blobs[0].dtype == np.float32


def test_detections_come_back_strongest_first(det):
    out = yolox_output(416, 5, 3, score=0.9)
    extra = yolox_output(416, 20, 10, score=0.6, cls=39)[0]  # a bottle, weaker
    out[0][...] = np.maximum(out[0], extra)
    found = det.detector.Detector(det.detection.DEFAULT_MODELS["yolox_nano"], FakeRuntime(out)).detect(
        np.zeros((416, 416, 3), dtype=np.uint8)
    )
    assert [d.label for d in found] == ["person", "bottle"]


def test_analysis_code_has_no_network():
    """Analysis only reads photos and writes results: it must not be able to send anything anywhere."""
    forbidden = {"socket", "ssl", "http", "urllib", "requests", "httpx", "websockets", "ftplib", "smtplib"}
    forbidden |= {"huggingface_hub"}  # model downloads happen in a separate script, never here
    tree = ast.parse((TOOLS / "reachy_lib" / "detector.py").read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported & forbidden == set()
