"""reachy_lib.detection: the table of detection models, which one runs in which pass, and whether its file is there."""

import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[2] / "robot_tools"


@pytest.fixture
def det(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(TOOLS))
    for name in ("reachy_lib.detection", "reachy_lib.storage", "reachy_lib"):
        sys.modules.pop(name, None)
    monkeypatch.setenv("REACHY_TOOLS_MODELS_DIR", str(tmp_path / "models"))
    from reachy_lib import detection as module

    return module


def test_the_default_table_holds_the_models_we_tested(det):
    models = det.load_models()
    assert {n: (m.size, m.family, m.pad) for n, m in models.items()} == {
        "yolox_nano": (416, "yolox", 114),
        "yolox_s": (640, "yolox", 114),
        "yolox_m": (640, "yolox", 114),
        "nanodet": (416, "nanodet", 0),
    }


def test_an_entry_in_the_file_can_change_one_field_of_a_known_model(det):
    models = det.load_models({"yolox_nano": {"size": 480}})
    assert models["yolox_nano"].size == 480 and models["yolox_nano"].file == det.DEFAULT_MODELS["yolox_nano"].file


def test_a_new_model_needs_a_file_a_size_and_a_family(det):
    models = det.load_models({"yolox_l": {"file": "yolox_l.onnx", "size": 640, "family": "yolox"}})
    assert models["yolox_l"].pad == 114  # the padding a family normally uses
    with pytest.raises(ValueError, match="yolox_x.*family"):
        det.load_models({"yolox_x": {"file": "yolox_x.onnx", "size": 640}})


@pytest.mark.parametrize(
    "entry",
    [
        {"family": "mystery"},
        {"size": 100},  # not a multiple of 32
        {"size": 4096},
        {"size": "big"},
        {"pad": 300},
        {"file": "../elsewhere.onnx"},
        {"file": "sub/model.onnx"},
        {"file": "C:\\models\\m.onnx"},
        {"colour": "red"},
    ],
)
def test_a_bad_entry_is_refused_and_names_the_model(det, entry):
    with pytest.raises(ValueError, match="yolox_nano"):
        det.load_models({"yolox_nano": entry})


def test_a_model_name_is_plain_lower_case(det):
    with pytest.raises(ValueError, match="name"):
        det.load_models({"Bad Name": {"file": "a.onnx", "size": 416, "family": "yolox"}})


def test_the_default_tiers_are_nano_then_s_then_m(det):
    assert det.load_tiers(det.load_models()) == {"now": "yolox_nano", "after": "yolox_s", "remote": "yolox_m"}


def test_tiers_can_be_changed_or_switched_off(det):
    models = det.load_models()
    tiers = det.load_tiers(models, {"after": "nanodet", "remote": None})
    assert tiers == {"now": "yolox_nano", "after": "nanodet", "remote": None}


def test_a_tier_must_name_a_known_model_and_a_known_pass(det):
    models = det.load_models()
    with pytest.raises(ValueError, match="nope"):
        det.load_tiers(models, {"now": "nope"})
    with pytest.raises(ValueError, match="later"):
        det.load_tiers(models, {"later": "yolox_nano"})


def test_model_files_are_looked_for_only_in_the_models_folder(det, tmp_path):
    spec = det.load_models()["yolox_nano"]
    assert det.model_path(spec) == tmp_path / "models" / spec.file
    available, reason = det.availability(spec)
    assert available is False and spec.file in reason
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / spec.file).write_bytes(b"x")
    assert det.availability(spec) == (True, "ok")
