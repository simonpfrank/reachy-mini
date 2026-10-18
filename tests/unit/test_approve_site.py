"""approve_site: a site is approved only when the user said yes in conversation, never by the model alone.
The conversation app's Tool base only exists on the robot, so a stand-in module is registered before import."""

import json
import sys
import types
from typing import Any

import pytest

_core_tools = types.ModuleType("reachy_mini_conversation_app.tools.core_tools")
_core_tools.Tool = object  # type: ignore[attr-defined]
_core_tools.ToolDependencies = object  # type: ignore[attr-defined]
for name in ("reachy_mini_conversation_app", "reachy_mini_conversation_app.tools"):
    sys.modules.setdefault(name, types.ModuleType(name))
sys.modules.setdefault("reachy_mini_conversation_app.tools.core_tools", _core_tools)

from robot_tools import approve_site  # noqa: E402

REFUSED_AT = 100


def said(*turns: tuple[str, str]) -> list[dict[str, Any]]:
    """Final transcripts after the refusal, numbered from REFUSED_AT + 1."""
    return [
        {"role": role, "text": text, "final": True, "seq": REFUSED_AT + n} for n, (role, text) in enumerate(turns, 1)
    ]


@pytest.fixture
def chat(monkeypatch, tmp_path):
    """State dir with one refused site, and a conversation the test fills in."""
    monkeypatch.setenv("REACHY_TOOLS_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(approve_site, "ANSWER_WAIT_S", 0)
    (tmp_path / "approved_sites.txt").write_text("example.org\n")
    (tmp_path / "pending_approval.json").write_text(json.dumps({"news.sky.com": REFUSED_AT}))
    events: list[dict[str, Any]] = []
    monkeypatch.setattr(approve_site, "history", lambda: events)
    return types.SimpleNamespace(events=events, state=tmp_path)


def approved(chat) -> list[str]:
    return (chat.state / "approved_sites.txt").read_text().split()


def test_yes_after_the_robot_names_the_site_approves_it(chat):
    chat.events += said(("assistant", "I can't read news.sky.com yet. Shall I allow Sky News?"), ("user", "Yes"))
    result = approve_site.approve("news.sky.com")
    assert result["approved"] == "news.sky.com" and result["already_approved"] is False
    assert "repeat the call that was refused" in result["note"]
    assert approved(chat) == ["example.org", "news.sky.com"]
    assert json.loads((chat.state / "pending_approval.json").read_text()) == {}


def test_model_approving_without_asking_is_refused(chat):
    chat.events += said(("user", "Read me the Sky story"))
    result = approve_site.approve("news.sky.com")
    assert result["approved"] is None and "not asked" in result["refused"]
    assert approved(chat) == ["example.org"]


def test_no_answer_yet_is_refused(chat):
    chat.events += said(("assistant", "Shall I allow news.sky.com?"))
    assert "not answered" in approve_site.approve("news.sky.com")["refused"]
    assert approved(chat) == ["example.org"]


@pytest.mark.parametrize("answer", ["No", "Yes, actually no", "Sure, why not", "Don't", "Hmm, maybe later"])
def test_anything_but_a_clear_yes_is_refused(chat, answer):
    chat.events += said(("assistant", "Shall I allow Sky?"), ("user", answer))
    assert "did not say yes" in approve_site.approve("news.sky.com")["refused"]
    assert approved(chat) == ["example.org"]


def test_a_question_that_does_not_name_the_site_does_not_count(chat):
    chat.events += said(("assistant", "Shall I carry on?"), ("user", "Yes"))
    assert "not asked" in approve_site.approve("news.sky.com")["refused"]


def test_a_yes_from_before_the_refusal_does_not_count(chat):
    chat.events += [
        {"role": "assistant", "text": "Shall I allow Sky?", "final": True, "seq": REFUSED_AT - 2},
        {"role": "user", "text": "Yes", "final": True, "seq": REFUSED_AT - 1},
    ]
    assert "not asked" in approve_site.approve("news.sky.com")["refused"]


@pytest.mark.parametrize("wider", ["sky.com", "sport.sky.com"])
def test_only_the_exact_refused_site_can_be_approved(chat, wider):
    chat.events += said(("assistant", "Shall I allow Sky?"), ("user", "Yes"))
    assert "only the exact site" in approve_site.approve(wider)["refused"].lower()
    assert approved(chat) == ["example.org"]


def test_yes_still_counts_when_the_robot_names_the_site_again_afterwards(chat):
    chat.events += said(("assistant", "Shall I allow Sky?"), ("user", "Yes"), ("assistant", "Thanks, reading Sky now"))
    assert approve_site.approve("news.sky.com")["approved"] == "news.sky.com"


def test_a_later_yes_counts_after_an_earlier_no(chat):
    chat.events += said(("assistant", "Allow Sky?"), ("user", "No"), ("assistant", "Sky, then?"), ("user", "Yes"))
    assert approve_site.approve("news.sky.com")["approved"] == "news.sky.com"


def test_typed_yes_from_the_hub_counts_as_the_users_words(chat):
    chat.events += said(("assistant", "Shall I allow Sky?"))
    (chat.state / "typed_messages.jsonl").write_text(json.dumps({"text": "yes", "after_seq": REFUSED_AT + 1}) + "\n")
    assert approve_site.approve("news.sky.com")["approved"] == "news.sky.com"


def test_typed_text_from_before_the_question_does_not_count(chat):
    chat.events += said(("assistant", "Shall I allow Sky?"))
    (chat.state / "typed_messages.jsonl").write_text(json.dumps({"text": "yes", "after_seq": REFUSED_AT}) + "\n")
    assert "not answered" in approve_site.approve("news.sky.com")["refused"]


def test_partial_transcripts_are_ignored(chat):
    chat.events += said(("assistant", "Shall I allow Sky?"))
    chat.events.append({"role": "user", "text": "Yes", "final": False, "seq": REFUSED_AT + 5})
    assert "not answered" in approve_site.approve("news.sky.com")["refused"]


def test_waits_briefly_for_the_users_answer_to_arrive(chat, monkeypatch):
    chat.events += said(("assistant", "Shall I allow Sky?"))
    monkeypatch.setattr(approve_site, "ANSWER_WAIT_S", 5)

    def answer_arrives(_seconds: float) -> None:
        chat.events.append({"role": "user", "text": "Yes", "final": True, "seq": REFUSED_AT + 9})

    monkeypatch.setattr(approve_site.time, "sleep", answer_arrives)
    assert approve_site.approve("news.sky.com")["approved"] == "news.sky.com"


@pytest.mark.parametrize(
    ("host", "name"),
    [("news.sky.com", "sky"), ("www.bbc.co.uk", "bbc"), ("theguardian.com", "theguardian"),
     ("metoffice.gov.uk", "metoffice"), ("example.org", "example")],
)
def test_site_name_is_what_the_robot_must_say(host, name):
    assert approve_site.site_name(host) == name


def test_the_guardian_spoken_as_two_words_still_names_it(chat):
    (chat.state / "pending_approval.json").write_text(json.dumps({"theguardian.com": REFUSED_AT}))
    chat.events += said(("assistant", "May I read The Guardian?"), ("user", "OK"))
    assert approve_site.approve("theguardian.com")["approved"] == "theguardian.com"


def test_conversation_that_cannot_be_checked_approves_nothing(chat, monkeypatch):
    (chat.state / "pending_approval.json").write_text(json.dumps({"news.sky.com": None}))
    assert "could not be checked" in approve_site.approve("news.sky.com")["refused"]

    def broken() -> list[dict[str, Any]]:
        raise OSError("connection refused")

    (chat.state / "pending_approval.json").write_text(json.dumps({"news.sky.com": REFUSED_AT}))
    monkeypatch.setattr(approve_site, "history", broken)
    assert "could not be checked" in approve_site.approve("news.sky.com")["refused"]
    assert approved(chat) == ["example.org"]


@pytest.mark.parametrize("bad", ["", "com", "localhost", "192.168.0.1", "not a site", "router"])
def test_anything_but_a_website_name_is_refused(chat, bad):
    with pytest.raises(ValueError):
        approve_site.approve(bad)
