"""reachy_lib.replies: the one check every tool reply passes through; raw media and private paths never get through."""

import asyncio
import sys
from pathlib import Path

import numpy as np
import pytest

TOOLS = Path(__file__).resolve().parents[2] / "robot_tools"


@pytest.fixture
def replies(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(TOOLS))
    for name in ("reachy_lib.replies", "reachy_lib.storage", "reachy_lib"):
        sys.modules.pop(name, None)
    monkeypatch.setenv("REACHY_TOOLS_CAMERA_DIR", str(tmp_path / "camera"))
    monkeypatch.setenv("REACHY_TOOLS_SCAN_DIR", str(tmp_path / "scan"))
    monkeypatch.setenv("REACHY_TOOLS_KEYS_DIR", str(tmp_path / "keys"))
    from reachy_lib import replies as module

    return module


def test_plain_data_passes_unchanged_and_is_returned(replies):
    reply = {"saved": True, "count": 3, "ratio": 0.5, "note": "ok", "none": None, "items": [1, "a", {"x": [2.5]}]}
    assert replies.check_reply(reply) is reply
    assert replies.check_reply(("a", 1)) == ("a", 1)  # a tuple is a list to the LLM


def test_long_ordinary_text_is_fine(replies):
    article = "A sentence of ordinary words about a thing. " * 400  # about 17,000 characters
    assert replies.check_reply({"text": article})["text"] == article


@pytest.mark.parametrize(
    "value", [b"raw", bytearray(b"raw"), memoryview(b"raw"), np.zeros(3), Path("somewhere/x"), {1, 2}, object()]
)
def test_anything_but_plain_data_is_refused(replies, value):
    with pytest.raises(replies.ReplyRefused):
        replies.check_reply({"deep": [{"x": value}]})


def test_a_dict_key_must_be_text(replies):
    with pytest.raises(replies.ReplyRefused):
        replies.check_reply({1: "a"})


def test_the_shape_of_an_image_reply_is_refused_by_key_name(replies):
    with pytest.raises(replies.ReplyRefused, match="b64"):
        replies.check_reply({"b64_im": "short"})  # Pollen's camera tool puts the photo under this key
    with pytest.raises(replies.ReplyRefused):
        replies.check_reply({"photo_b64": "x"})


def test_encoded_image_data_in_a_string_is_refused(replies):
    blobs = ("data:image/jpeg;base64,AAAA", "/9j/4AAQSkZJRgABAQ" + "A" * 300, "iVBORw0KGgo" + "A" * 300, "A" * 250)
    for blob in blobs:
        with pytest.raises(replies.ReplyRefused):
            replies.check_reply({"note": blob})


def test_the_private_folders_are_never_named_in_a_reply(replies, tmp_path):
    for folder in ("camera", "scan", "keys"):
        with pytest.raises(replies.ReplyRefused) as error:
            replies.check_reply({"note": f"saved to {tmp_path / folder}/photo.jpg"})
        assert str(tmp_path) not in str(error.value)  # the refusal does not repeat the path


def test_an_enormous_reply_is_refused(replies):
    with pytest.raises(replies.ReplyRefused, match="large"):
        replies.check_reply({"text": "words " * 30_000})


def test_the_refusal_never_contains_the_data(replies):
    with pytest.raises(replies.ReplyRefused) as error:
        replies.check_reply({"x": b"SECRET-BYTES"})
    assert "SECRET-BYTES" not in str(error.value)


def test_the_decorator_checks_what_a_tool_returns(replies):
    class FakeTool:
        @replies.checked
        async def __call__(self, deps, **kwargs):
            return kwargs["value"]

    tool = FakeTool()
    assert asyncio.run(tool(None, value={"ok": 1})) == {"ok": 1}
    with pytest.raises(replies.ReplyRefused):
        asyncio.run(tool(None, value={"photo": b"raw"}))
