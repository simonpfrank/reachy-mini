"""The table of detection models, which model runs in which pass, and whether a model's file is there.

Models are data, not code: an entry in ``scan.json`` adds a model or changes one field of a known one. A model's
file is looked for only in the models folder, so a setting cannot point the scan at an arbitrary file.

Usage:
    models = load_models(settings_file.get("models"))
    tiers = load_tiers(models, settings_file.get("tiers"))
    spec = models[tiers["now"]]
    ready, reason = availability(spec)
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .storage import models_dir

FAMILIES = {"yolox": 114, "nanodet": 0}  # how the output is decoded -> the grey level its padding normally uses
PASSES = ("now", "after", "remote")  # during the scan on the robot, after it on the robot, on the Mac
NAME = re.compile(r"[a-z0-9_]+")
FIELDS = ("file", "size", "family", "pad")


@dataclass(frozen=True)
class ModelSpec:
    """One detection model.

    Attributes:
        name: Short lower-case name used in settings.
        file: File name (``.onnx``) inside the models folder.
        size: The square input, in pixels, the file was built for.
        family: How its output is decoded: ``yolox`` or ``nanodet``.
        pad: Grey level (0 to 255) of the padding around the resized photo.
    """

    name: str
    file: str
    size: int
    family: str
    pad: int


DEFAULT_MODELS = {
    "yolox_nano": ModelSpec("yolox_nano", "yolox_nano.onnx", 416, "yolox", 114),
    "yolox_s": ModelSpec("yolox_s", "yolox_s.onnx", 640, "yolox", 114),
    "yolox_m": ModelSpec("yolox_m", "yolox_m.onnx", 640, "yolox", 114),
    "nanodet": ModelSpec("nanodet", "object_detection_nanodet_2022nov.onnx", 416, "nanodet", 0),
}
DEFAULT_TIERS: dict[str, str | None] = {"now": "yolox_nano", "after": "yolox_s", "remote": "yolox_m"}


def load_models(overrides: Mapping[str, Any] | None = None) -> dict[str, ModelSpec]:
    """The default models, with ``overrides`` (the ``models`` entry of scan.json) added or applied on top.

    Args:
        overrides: Model name to a dict of fields. For a known model any fields given replace its own; a new model
            needs ``file``, ``size`` and ``family``.

    Returns:
        Model name to its spec.

    Raises:
        ValueError: An entry is malformed; the message names the model and the field.
    """
    models = dict(DEFAULT_MODELS)
    for name, entry in (overrides or {}).items():
        if not isinstance(name, str) or not NAME.fullmatch(name):
            raise ValueError(f"A model name is lower-case letters, digits or _, got {name!r}")
        models[name] = _spec(name, entry, models.get(name))
    return models


def load_tiers(models: Mapping[str, ModelSpec], overrides: Mapping[str, Any] | None = None) -> dict[str, str | None]:
    """Which model runs in each pass: the defaults, with ``overrides`` applied; ``None`` switches a pass off.

    Raises:
        ValueError: A pass that does not exist, or a model that is not in ``models``.
    """
    tiers = dict(DEFAULT_TIERS)
    for pass_name, model in (overrides or {}).items():
        if pass_name not in PASSES:
            raise ValueError(f"There is no pass called {pass_name!r}; the passes are {', '.join(PASSES)}")
        if model is not None and model not in models:
            raise ValueError(f"Pass {pass_name!r} names a model that is not in the table: {model!r}")
        tiers[pass_name] = model
    return tiers


def model_path(spec: ModelSpec) -> Path:
    """Where the model's file is expected: only ever inside the models folder."""
    return models_dir() / spec.file


def availability(spec: ModelSpec) -> tuple[bool, str]:
    """Whether the model's file is there, and if not why (for the scan's record of what ran)."""
    if model_path(spec).is_file():
        return True, "ok"
    return False, f"{spec.file} is not in the models folder"


def _spec(name: str, entry: Any, base: ModelSpec | None) -> ModelSpec:
    if not isinstance(entry, Mapping):
        raise ValueError(f"Model {name!r}: the entry must be a JSON object")
    unknown = sorted(set(entry) - set(FIELDS))
    if unknown:
        raise ValueError(f"Model {name!r} has fields that do not exist: {', '.join(unknown)}")
    values: dict[str, Any] = {}
    if base:
        values = {"file": base.file, "size": base.size, "family": base.family, "pad": base.pad}
    values.update(entry)
    missing = [field for field in ("file", "size", "family") if field not in values]
    if missing:
        raise ValueError(f"Model {name!r} needs: {', '.join(missing)}")
    family, size, file = values["family"], values["size"], values["file"]
    if family not in FAMILIES:
        raise ValueError(f"Model {name!r}: family must be one of {', '.join(FAMILIES)}")
    if not isinstance(size, int) or isinstance(size, bool) or not 64 <= size <= 2048 or size % 32:
        raise ValueError(f"Model {name!r}: size must be a whole number from 64 to 2048, a multiple of 32")
    pad = values.get("pad", FAMILIES[family])
    if not isinstance(pad, int) or isinstance(pad, bool) or not 0 <= pad <= 255:
        raise ValueError(f"Model {name!r}: pad must be a whole number from 0 to 255")
    if not isinstance(file, str) or not file.endswith(".onnx") or any(c in file for c in "/\\") or ".." in file:
        raise ValueError(f"Model {name!r}: file must be a plain .onnx file name inside the models folder")
    return ModelSpec(name, file, size, family, pad)
