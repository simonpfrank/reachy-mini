"""Run a detection model on a photo: resize, run the network, decode its output, merge overlapping boxes.

Needs numpy and ONNX Runtime, plus OpenCV to decode and resize photos; those two are imported only when used, so this
module always imports and ``engine_available`` says whether analysis can run. It reads photos and returns results:
it imports nothing that can reach a network, and a test keeps it that way.

Usage:
    detector = Detector.load(load_models()["yolox_nano"], threads=1)
    for found in detector.detect(decode_jpeg(jpeg_bytes)):
        print(found.label, found.score, found.box)  # box in the photo's own pixels: left, top, right, bottom
"""

from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np
import numpy.typing as npt

from .detection import ModelSpec, model_path

Image = npt.NDArray[np.uint8]
Array = npt.NDArray[np.float32]

COCO = (
    "person bicycle car motorcycle airplane bus train truck boat traffic_light fire_hydrant stop_sign parking_meter "
    "bench bird cat dog horse sheep cow elephant bear zebra giraffe backpack umbrella handbag tie suitcase frisbee "
    "skis snowboard sports_ball kite baseball_bat baseball_glove skateboard surfboard tennis_racket bottle wine_glass "
    "cup fork knife spoon bowl banana apple sandwich orange broccoli carrot hot_dog pizza donut cake chair couch "
    "potted_plant bed dining_table toilet tv laptop mouse remote keyboard cell_phone microwave oven toaster sink "
    "refrigerator book clock vase scissors teddy_bear hair_drier toothbrush"
).split()
NANODET_MEAN = np.array([103.53, 116.28, 123.675], dtype=np.float32)
NANODET_STD = np.array([57.375, 57.12, 58.395], dtype=np.float32)
NANODET_REG_MAX = 7  # each box side is a distribution over 8 distances


@dataclass(frozen=True)
class Detection:
    """One object found: its name, how sure the model is (0 to 1), and its box in the photo's own pixels."""

    label: str
    score: float
    box: tuple[float, float, float, float]  # left, top, right, bottom


class Runtime(Protocol):
    """Whatever runs the network: blob in, the model's raw output arrays out."""

    def run(self, blob: Array) -> list[Array]:
        """Run the network once."""


def engine_available() -> tuple[bool, str]:
    """Whether analysis can run here: ONNX Runtime and OpenCV importable. If not, why (for the scan's record)."""
    for module in ("onnxruntime", "cv2"):
        try:
            __import__(module)
        except ImportError:
            return False, f"{module} is not installed in this environment"
    return True, "ok"


def decode_jpeg(data: bytes) -> Image:
    """A JPEG's bytes as a colour picture (blue, green, red); ValueError if it is not a readable image."""
    import cv2

    picture = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if picture is None:
        raise ValueError("The photo could not be decoded")
    return np.asarray(picture, dtype=np.uint8)


def letterbox(image: Image, size: int, pad: int) -> tuple[Image, float]:
    """Shrink (or grow) the photo to fit a size x size square, keeping its shape, padded bottom and right with ``pad``.

    Returns:
        The square, and the scale applied (divide box coordinates by it to get back to the photo's pixels).
    """
    import cv2

    height, width = image.shape[:2]
    scale = min(size / height, size / width)
    new_h, new_w = int(round(height * scale)), int(round(width * scale))
    canvas = np.full((size, size, 3), pad, dtype=np.uint8)
    canvas[:new_h, :new_w] = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
    return canvas, scale


def to_blob(family: str, canvas: Image) -> Array:
    """The network's input: float32, channels first, with the family's own normalisation."""
    pixels = canvas.astype(np.float32)
    if family == "nanodet":
        pixels = (pixels - NANODET_MEAN) / NANODET_STD
    return np.ascontiguousarray(pixels.transpose(2, 0, 1)[None])


def nms(boxes: Array, scores: Array, classes: npt.NDArray[Any], iou: float) -> list[int]:
    """Greedy non-maximum suppression per class on (left, top, right, bottom) boxes; returns the indices kept."""
    if len(boxes) == 0:
        return []
    shifted = boxes + classes[:, None] * 10000.0  # boxes of different classes can never overlap
    x1, y1, x2, y2 = shifted.T
    area = (x2 - x1) * (y2 - y1)
    order = scores.argsort()[::-1]
    keep: list[int] = []
    while order.size:
        i = order[0]
        keep.append(int(i))
        rest = order[1:]
        width = np.clip(np.minimum(x2[i], x2[rest]) - np.maximum(x1[i], x1[rest]), 0, None)
        height = np.clip(np.minimum(y2[i], y2[rest]) - np.maximum(y1[i], y1[rest]), 0, None)
        overlap = width * height / (area[i] + area[rest] - width * height)
        order = rest[overlap <= iou]
    return keep


def _strongest(boxes: Array, scores: Array, conf: float, iou: float) -> tuple[Array, Array, npt.NDArray[Any]]:
    classes, best = scores.argmax(1), scores.max(1)
    mask = best > conf
    boxes, best, classes = boxes[mask], best[mask], classes[mask]
    keep = nms(boxes, best, classes, iou)
    return boxes[keep], best[keep], classes[keep]


def decode_yolox(outputs: list[Array], size: int, conf: float, iou: float) -> tuple[Array, Array, npt.NDArray[Any]]:
    """Boxes, scores and class numbers (in the size x size square) from a YOLOX model's raw output."""
    dets = outputs[0][0].copy()
    grids, strides = [], []
    for stride in (8, 16, 32):
        cells = size // stride
        xv, yv = np.meshgrid(np.arange(cells), np.arange(cells))
        grids.append(np.stack((xv, yv), 2).reshape(-1, 2))
        strides.append(np.full((cells * cells, 1), stride))
    dets[:, :2] = (dets[:, :2] + np.concatenate(grids)) * np.concatenate(strides)
    dets[:, 2:4] = np.exp(dets[:, 2:4]) * np.concatenate(strides)
    boxes = np.concatenate([dets[:, :2] - dets[:, 2:4] / 2, dets[:, :2] + dets[:, 2:4] / 2], axis=1)
    return _strongest(boxes, dets[:, 4:5] * dets[:, 5:], conf, iou)


def decode_nanodet(outputs: list[Array], size: int, conf: float, iou: float) -> tuple[Array, Array, npt.NDArray[Any]]:
    """Boxes, scores and class numbers (in the size x size square) from a NanoDet model's raw output.

    The class maps and box maps are told apart by shape, not position, so any output order works.
    """
    project = np.arange(NANODET_REG_MAX + 1, dtype=np.float32)
    by_size = lambda o: -o.reshape(-1, o.shape[-1]).shape[0]  # noqa: E731 -- biggest map (smallest stride) first
    class_maps = sorted((o for o in outputs if o.shape[-1] == 80), key=by_size)
    box_maps = sorted((o for o in outputs if o.shape[-1] == 4 * (NANODET_REG_MAX + 1)), key=by_size)
    all_boxes, all_scores = [], []
    for scores, reg in zip(class_maps, box_maps, strict=True):
        scores, reg = scores.reshape(-1, 80), reg.reshape(-1, 4 * (NANODET_REG_MAX + 1))
        cells = int(round(scores.shape[0] ** 0.5))
        stride = size // cells
        xv, yv = np.meshgrid(np.arange(cells) * stride, np.arange(cells) * stride)
        points = np.column_stack([xv.flatten() + 0.5 * (stride - 1), yv.flatten() + 0.5 * (stride - 1)])
        exp = np.exp(reg.reshape(-1, NANODET_REG_MAX + 1))
        distance = ((exp / exp.sum(axis=1, keepdims=True)) @ project).reshape(-1, 4) * stride
        all_boxes.append(np.clip(np.column_stack([points - distance[:, :2], points + distance[:, 2:]]), 0, size))
        all_scores.append(scores)
    return _strongest(np.concatenate(all_boxes), np.concatenate(all_scores), conf, iou)


class _OrtRuntime:
    def __init__(self, session: Any, input_name: str) -> None:
        self._session, self._input = session, input_name

    def run(self, blob: Array) -> list[Array]:
        return list(self._session.run(None, {self._input: blob}))


class Detector:
    """One model, ready to find objects in photos."""

    def __init__(self, spec: ModelSpec, runtime: Runtime, conf: float = 0.35, iou: float = 0.5) -> None:
        """Wrap ``runtime`` (anything with ``run``) for the model described by ``spec``.

        Args:
            spec: The model's size, family and padding.
            runtime: Runs the network; ``Detector.load`` builds an ONNX Runtime one from the model file.
            conf: Detections scoring this or less are dropped.
            iou: Boxes of one class overlapping more than this are merged into the strongest.
        """
        self.spec, self._runtime, self._conf, self._iou = spec, runtime, conf, iou

    @classmethod
    def load(cls, spec: ModelSpec, threads: int = 1, conf: float = 0.35, iou: float = 0.5) -> "Detector":
        """Open the model's file from the models folder with ONNX Runtime, using ``threads`` CPU threads.

        Raises:
            ImportError: ONNX Runtime is not installed.
            FileNotFoundError: The model's file is not in the models folder.
        """
        import onnxruntime as ort  # type: ignore[import-untyped]

        path = model_path(spec)
        if not path.is_file():
            raise FileNotFoundError(f"{spec.file} is not in the models folder")
        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        options.log_severity_level = 3  # errors only: these model files print hundreds of harmless warnings
        session = ort.InferenceSession(str(path), options, providers=["CPUExecutionProvider"])
        input_name = next(i.name for i in session.get_inputs() if len(i.shape) == 4)
        return cls(spec, _OrtRuntime(session, input_name), conf, iou)

    def detect(self, image: Image) -> list[Detection]:
        """The objects in a colour photo, strongest first, with boxes in the photo's own pixels."""
        canvas, scale = letterbox(image, self.spec.size, self.spec.pad)
        outputs = self._runtime.run(to_blob(self.spec.family, canvas))
        decode = decode_yolox if self.spec.family == "yolox" else decode_nanodet
        boxes, scores, classes = decode(outputs, self.spec.size, self._conf, self._iou)
        return [
            Detection(COCO[int(classes[i])], float(scores[i]), tuple(float(v / scale) for v in boxes[i]))  # type: ignore[arg-type]
            for i in scores.argsort()[::-1]
        ]
