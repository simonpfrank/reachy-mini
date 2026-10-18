"""Tests for web_search and news with mocked providers, key decryption and a recorded BBC feed.
The conversation app's Tool base only exists on the robot, so a stand-in module is registered before import."""

import asyncio
import io
import json
import subprocess
import sys
import types
import urllib.error
from pathlib import Path
from typing import Any

import pytest


class _StandInTool:
    name: str
    description: str
    parameters_schema: dict[str, Any]


_core_tools = types.ModuleType("reachy_mini_conversation_app.tools.core_tools")
_core_tools.Tool = _StandInTool  # type: ignore[attr-defined]
_core_tools.ToolDependencies = object  # type: ignore[attr-defined]
for name in ("reachy_mini_conversation_app", "reachy_mini_conversation_app.tools"):
    sys.modules.setdefault(name, types.ModuleType(name))
sys.modules.setdefault("reachy_mini_conversation_app.tools.core_tools", _core_tools)

from robot_tools import news, web_search  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
BBC_FEED = (ROOT / "tests" / "data" / "news_bbc_top.xml").read_bytes()
KEY = "tvly-test-secret"


@pytest.fixture
def web(monkeypatch, tmp_path):
    """An encrypted key file, a fake systemd decrypt and fake providers that record each request."""
    monkeypatch.setenv("REACHY_TOOLS_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("REACHY_TOOLS_KEYS_DIR", str(tmp_path / "keys"))
    key = tmp_path / "keys" / "tavily.cred"
    key.parent.mkdir()
    key.write_text("encrypted")
    decrypts: list[list[str]] = []
    decrypted: dict[str, Any] = {"returncode": 0, "stdout": (KEY + "\n").encode()}

    def run(argv, **kwargs):
        decrypts.append(argv)
        return subprocess.CompletedProcess(argv, decrypted["returncode"], decrypted["stdout"], b"")

    monkeypatch.setattr(web_search.subprocess, "run", run)
    calls: list[dict[str, Any]] = []
    replies: dict[str, Any] = {
        web_search.SEARCH_URL: {
            "results": [
                {"title": "First", "url": "https://example.org/a", "content": "alpha", "published_date": "2026-10-16"},
                {"title": "Second", "url": "https://example.org/b", "content": "beta"},
            ]
        },
    }

    def urlopen(request, timeout):
        url = request.full_url
        calls.append(
            {
                "url": url,
                "body": json.loads(request.data) if request.data else None,
                "auth": request.get_header("Authorization"),
            }
        )
        reply = BBC_FEED if url.startswith("https://feeds.bbci.co.uk/") else replies[url]
        if isinstance(reply, Exception):
            raise reply
        return io.BytesIO(reply if isinstance(reply, bytes) else json.dumps(reply).encode())

    for module in (web_search, news):
        monkeypatch.setattr(module.urllib.request, "urlopen", urlopen)
    return types.SimpleNamespace(
        calls=calls, replies=replies, state=tmp_path, key=key, decrypts=decrypts, decrypted=decrypted
    )


def test_search_sends_key_privately_and_numbers_results(web):
    result = web_search.search_payload("UK interest rates October 2026", "week")
    assert [r["number"] for r in result["results"]] == [1, 2]
    assert result["results"][0] == {
        "number": 1,
        "title": "First",
        "url": "https://example.org/a",
        "published": "2026-10-16",
        "snippet": "alpha",
    }
    call = web.calls[0]
    assert call["auth"] == f"Bearer {KEY}"
    assert call["body"]["time_range"] == "week" and KEY not in json.dumps(call["body"])
    saved = json.loads((web.state / "last_results.json").read_text())
    assert saved["kind"] == "search" and saved["items"][1]["url"] == "https://example.org/b"


def test_key_is_decrypted_by_systemd_for_this_user(web):
    web_search.search_payload("anything")
    assert web.decrypts == [[web_search.SYSTEMD_CREDS, "--user", "--name=tavily", "decrypt", str(web.key), "-"]]


def test_undecryptable_or_missing_key_stops_before_any_request(web):
    web.decrypted.update(returncode=1, stdout=b"")
    with pytest.raises(RuntimeError, match="could not be decrypted") as error:
        web_search.search_payload("anything")
    assert KEY not in str(error.value)
    web.key.unlink()
    for call in (
        lambda: web_search.search_payload("anything"),
        lambda: news.news_payload("Rugby World Cup"),
    ):
        with pytest.raises(RuntimeError, match=r"not set up: no Tavily key \(scripts/keys.sh add tavily\)"):
            call()
    assert web.calls == []


def keys(*args: str, stdin: bytes | None = None) -> bytes:
    """Run scripts/keys.sh and return its output."""
    script = ROOT / "scripts" / "keys.sh"
    command = ["/bin/bash", "-n", str(script)] if args == ("-n",) else [str(script), *args]
    return subprocess.run(command, input=stdin, check=True, capture_output=True).stdout  # noqa: S603 -- fixed local script


def test_keys_script_is_valid_bash():
    keys("-n")


def test_keys_script_stores_encrypted_key_the_tools_can_read(monkeypatch, tmp_path):
    monkeypatch.setenv("REACHY_TOOLS_KEYS_DIR", str(tmp_path))
    keys("add", "tavily", stdin=b"dummy-not-a-key\n")
    assert b"dummy-not-a-key" not in (tmp_path / "tavily.cred").read_bytes()
    assert (tmp_path / "tavily.cred").stat().st_mode & 0o077 == 0
    assert web_search.tavily_key() == "dummy-not-a-key"
    assert keys("list") == b"tavily\n"
    keys("remove", "tavily")
    with pytest.raises(RuntimeError, match="not set up"):
        web_search.tavily_key()


def test_provider_refusal_is_explicit_and_never_shows_the_key(web):
    web.replies[web_search.SEARCH_URL] = urllib.error.HTTPError(web_search.SEARCH_URL, 432, "quota", {}, None)
    with pytest.raises(RuntimeError, match=r"refused the request \(HTTP 432\)") as error:
        web_search.search_payload("anything")
    assert KEY not in str(error.value)


def test_search_refuses_bad_arguments(web):
    with pytest.raises(ValueError, match="query"):
        web_search.search_payload("  ")
    with pytest.raises(ValueError, match="recent"):
        web_search.search_payload("x", "decade")


def test_bbc_headlines_skip_videos_and_are_numbered(web):
    result = news.news_payload()
    headlines = result["headlines"]
    assert len(headlines) == news.MAX_HEADLINES
    assert [h["number"] for h in headlines] == list(range(1, news.MAX_HEADLINES + 1))
    assert all("/videos/" not in h["url"] and "?" not in h["url"] for h in headlines)
    assert headlines[0]["source"] == "BBC News" and headlines[0]["published"]
    assert web.calls[0]["url"] == "https://feeds.bbci.co.uk/news/rss.xml" and web.calls[0]["auth"] is None


def test_other_topics_use_news_search(web):
    web.replies[news.SEARCH_URL] = {
        "results": [{"title": "Rugby", "url": "https://www.example.com/r", "content": "c", "published_date": "d"}]
    }
    result = news.news_payload("Rugby World Cup")
    assert web.calls[0]["body"]["topic"] == "news" and web.calls[0]["auth"] == f"Bearer {KEY}"
    assert result["headlines"][0] == {
        "number": 1,
        "title": "Rugby",
        "summary": "c",
        "url": "https://www.example.com/r",
        "published": "d",
        "source": "www.example.com",
    }


def test_tools_run_off_the_event_loop(web):
    assert asyncio.run(news.News()(None, topic="uk"))["topic"] == "uk"
    assert web.calls[-1]["url"] == "https://feeds.bbci.co.uk/news/uk/rss.xml"
    assert asyncio.run(web_search.WebSearch()(None, query="q"))["results"]
