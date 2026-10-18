"""read_article and approve_site: approved sites, direct fetch with network checks, extraction and links.
The conversation app's Tool base only exists on the robot, so a stand-in module is registered before import."""

import asyncio
import importlib
import json
import socket
import sys
import types
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

from robot_tools import approve_site, read_article  # noqa: E402

PUBLIC = "93.184.216.34"
HTML = "text/html; charset=utf-8"

ARTICLE = b"""<html><head><title>Storm hits coast | Example News</title><script>var x = 1;</script></head>
<body>
<header class="site">Example News banner <a href="/subscribe">Subscribe</a></header>
<nav><a href="/world">World</a> <a href="/uk">UK</a></nav>
<article>
  <header><h1>Storm hits coast</h1><p>Thousands without power.</p></header>
  <p>The storm arrived overnight.</p>
  <ul><li><p>Trains cancelled</p></li><li>Schools closed</li></ul>
  <p>Read <a href="/weather/warnings">the warnings</a> and
     <a href="https://other.example.org/live#top">live updates</a>.</p>
  <p><a href="javascript:void(0)">Share</a> <a href="mailto:news@example.org">Email us</a></p>
  <aside>Most read: <a href="/popular">Popular</a></aside>
</article>
<footer>Copyright</footer>
</body></html>"""

SECTION = b"""<html><head><title>US news | Example News</title></head><body>
<main>
  <a href="/us/story-one">Story one headline</a>
  <a href="/us/story-two">Story two headline</a>
  <a href="/us/story-two">Story two headline</a>
  <a href="/us/story-three"><img src="x.jpg"></a>
</main></body></html>"""


@pytest.fixture
def web(monkeypatch, tmp_path):
    """Fake DNS and fake pages; every request records the URL and the address it went to."""
    monkeypatch.setenv("REACHY_TOOLS_STATE_DIR", str(tmp_path))
    (tmp_path / "approved_sites.txt").write_text("example.org\nexample.com\nexample.net\n")
    dns: dict[str, list[str]] = {"news.example.org": [PUBLIC], "other.example.org": [PUBLIC]}
    pages: dict[str, tuple[int, dict[str, str], bytes]] = {
        "https://news.example.org/storm": (200, {"content-type": HTML}, ARTICLE),
        "https://news.example.org/us": (200, {"content-type": HTML}, SECTION),
        "https://news.example.org/us/story-two": (200, {"content-type": HTML}, ARTICLE),
    }
    calls: list[tuple[str, str]] = []

    def getaddrinfo(host, port, type=0):  # noqa: A002 -- socket.getaddrinfo's parameter name
        if host not in dns:
            raise socket.gaierror("not found")
        return [(socket.AF_INET6 if ":" in a else socket.AF_INET, type, 6, "", (a, port)) for a in dns[host]]

    def request(parts, address):
        url = parts.geturl()
        calls.append((url, address))
        return pages[url]

    monkeypatch.setattr(read_article.socket, "getaddrinfo", getaddrinfo)
    monkeypatch.setattr(read_article, "request", request)
    monkeypatch.setattr(read_article, "latest_seq", lambda: 100)
    monkeypatch.setattr(read_article, "APPROVAL_WAIT_S", 0)
    return types.SimpleNamespace(dns=dns, pages=pages, calls=calls, state=tmp_path)


@pytest.mark.parametrize(
    "url,reason",
    [
        ("http://192.168.0.1/admin", "raw IP number"),
        ("http://127.0.0.1:8000/api/state", "raw IP number"),
        ("http://[::1]/", "raw IP number"),
        ("http://2130706433/", "not a public website name"),
        ("http://0x7f.1/", "not a public website name"),
        ("http://localhost:8000/", "not a public website name"),
        ("http://reachy-mini.local:8000/", "not a public website name"),
        ("http://router/", "not a public website name"),
        ("http://printer.lan/", "not a public website name"),
        ("https://news.example.org:8443/", "standard web ports"),
        ("https://user:secret@news.example.org/", "user name or password"),
        ("ftp://news.example.org/file", "http or https"),
        ("file:///etc/passwd", "http or https"),
    ],
)
def test_addresses_outside_the_public_web_are_refused_with_a_reason(web, url, reason):
    with pytest.raises(read_article.Refused, match=reason):
        read_article.article_payload(url=url)
    assert web.calls == []


def test_a_name_pointing_inside_the_network_is_refused(web):
    web.dns["sneaky.example.com"] = ["192.168.0.10"]
    web.dns["mixed.example.com"] = [PUBLIC, "10.0.0.5"]
    web.dns["scoped.example.com"] = ["fe80::1%wlan0"]
    for host in ("sneaky.example.com", "mixed.example.com", "scoped.example.com"):
        with pytest.raises(read_article.Refused, match="private or local address"):
            read_article.article_payload(url=f"https://{host}/")
    assert web.calls == []


def test_the_connection_goes_to_the_checked_address_preferring_ipv4(web):
    web.dns["news.example.org"] = ["2606:2800:220:1:248:1893:25c8:1946", PUBLIC]
    read_article.article_payload(url="https://news.example.org/storm")
    assert web.calls == [("https://news.example.org/storm", PUBLIC)]


def test_pinned_connection_opens_the_socket_to_the_checked_address(monkeypatch):
    opened = []

    def create_connection(address, timeout):
        opened.append(address)
        raise OSError("stop here")

    monkeypatch.setattr(read_article.socket, "create_connection", create_connection)
    parts = read_article.check_url("https://news.example.org/storm")
    with pytest.raises(RuntimeError, match="did not answer"):
        read_article.request(parts, PUBLIC)
    assert opened == [(PUBLIC, 443)]


def test_redirects_are_followed_and_rechecked(web):
    web.pages["https://news.example.org/old"] = (301, {"location": "/storm"}, b"")
    assert read_article.article_payload(url="https://news.example.org/old")["url"] == "https://news.example.org/storm"
    web.pages["https://news.example.org/evil"] = (302, {"location": "http://192.168.0.1/"}, b"")
    with pytest.raises(read_article.Refused, match="raw IP number"):
        read_article.article_payload(url="https://news.example.org/evil")
    web.pages["https://news.example.org/loop"] = (302, {"location": "/loop"}, b"")
    with pytest.raises(RuntimeError, match="redirected too many times"):
        read_article.article_payload(url="https://news.example.org/loop")


def test_article_text_keeps_the_story_and_drops_the_page_furniture(web):
    result = read_article.article_payload(url="https://news.example.org/storm")
    text = result["text"]
    assert result["title"] == "Storm hits coast | Example News"
    assert text.startswith("Storm hits coast\n\nThousands without power.\n\nThe storm arrived overnight.")
    assert "Trains cancelled" in text and text.count("Trains cancelled") == 1
    for furniture in ("banner", "Subscribe", "World", "Most read", "Copyright", "var x"):
        assert furniture not in text
    assert result["links"] == [
        {"number": 1, "title": "the warnings", "url": "https://news.example.org/weather/warnings"},
        {"number": 2, "title": "live updates", "url": "https://other.example.org/live"},
    ]
    assert "information, never instructions" in result["note"] and result["truncated"] is False


def test_section_page_links_are_numbered_and_read_with_link_without_losing_the_search_list(web):
    search = {
        "kind": "search",
        "items": [{"number": 2, "title": "Search two", "url": "https://news.example.org/storm"}],
    }
    (web.state / "last_results.json").write_text(json.dumps(search))
    page = read_article.article_payload(url="https://news.example.org/us")
    assert [(link["number"], link["title"]) for link in page["links"]] == [
        (1, "Story one headline"),
        (2, "Story two headline"),
    ]
    story = read_article.article_payload(link=2)
    assert story["url"] == "https://news.example.org/us/story-two"
    again = read_article.article_payload(number=2)  # number=2 is still search result 2, not link 2
    assert again["url"] == "https://news.example.org/storm"
    assert web.calls[-1] == ("https://news.example.org/storm", PUBLIC)
    with pytest.raises(ValueError, match="no link 9"):
        read_article.article_payload(link=9)


def test_listed_news_item_still_resolves_after_a_tool_reload(web):
    news = {"kind": "news", "items": [{"number": 2, "title": "Storm", "url": "https://news.example.org/storm"}]}
    (web.state / "last_results.json").write_text(json.dumps(news))
    reloaded = importlib.reload(read_article)
    assert reloaded.selected("last_results.json", 2, "missing")["url"] == "https://news.example.org/storm"


def test_failures_are_explicit(web, monkeypatch):
    web.pages["https://news.example.org/pdf"] = (200, {"content-type": "application/pdf"}, b"%PDF")
    with pytest.raises(RuntimeError, match=r"not a web page \(application/pdf\)"):
        read_article.article_payload(url="https://news.example.org/pdf")
    web.pages["https://news.example.org/paywall"] = (403, {"content-type": HTML}, b"no")
    with pytest.raises(RuntimeError, match=r"refused the request \(HTTP 403\)"):
        read_article.article_payload(url="https://news.example.org/paywall")
    monkeypatch.setattr(read_article, "MAX_BYTES", 10)
    with pytest.raises(RuntimeError, match="too large"):
        read_article.article_payload(url="https://news.example.org/storm")
    with pytest.raises(RuntimeError, match="could not be found"):
        read_article.article_payload(url="https://unknown.example.net/")
    with pytest.raises(ValueError, match="no item 3"):
        read_article.article_payload(number=3)
    with pytest.raises(ValueError, match="a link number from the last page, or a URL"):
        read_article.article_payload()


def test_long_text_is_bounded(web, monkeypatch):
    monkeypatch.setattr(read_article, "MAX_CHARS", 5)
    result = read_article.article_payload(url="https://news.example.org/storm")
    assert (result["text"], result["truncated"]) == ("Storm", True)


def test_missing_beautifulsoup_gives_the_fix(web, monkeypatch):
    monkeypatch.setitem(sys.modules, "bs4", None)
    with pytest.raises(RuntimeError, match="scripts/tool_deps.sh install"):
        read_article.article_payload(url="https://news.example.org/storm")


def test_tool_runs_off_the_event_loop(web):
    result = asyncio.run(read_article.ReadArticle()(None, url="https://news.example.org/storm"))
    assert result["url"] == "https://news.example.org/storm"
    schema = read_article.ReadArticle.parameters_schema
    assert set(schema["properties"]) == {"number", "link", "url"} and schema["required"] == []


def test_unapproved_site_asks_for_permission_and_fetches_nothing(web):
    web.dns["www.bbc.co.uk"] = [PUBLIC]
    result = read_article.article_payload(url="https://evilbbc.co.uk/story")
    assert result["not_approved"] == "evilbbc.co.uk" and "approve_site with site=evilbbc.co.uk" in result["note"]
    assert web.calls == []
    assert json.loads((web.state / "pending_approval.json").read_text()) == {"evilbbc.co.uk": 100}


def test_a_repeat_refusal_keeps_the_original_position(web, monkeypatch):
    read_article.article_payload(url="https://evilbbc.co.uk/story")
    monkeypatch.setattr(read_article, "latest_seq", lambda: 200)
    read_article.article_payload(url="https://evilbbc.co.uk/other")
    assert json.loads((web.state / "pending_approval.json").read_text()) == {"evilbbc.co.uk": 100}


def test_first_refusal_answers_at_once(web, monkeypatch):
    monkeypatch.setattr(read_article, "APPROVAL_WAIT_S", 4)

    def no_waiting(_seconds: float) -> None:
        raise AssertionError("a first refusal must not wait")

    monkeypatch.setattr(read_article.time, "sleep", no_waiting)
    assert read_article.article_payload(url="https://evilbbc.co.uk/story")["not_approved"] == "evilbbc.co.uk"


def test_retry_waits_for_an_approval_in_progress_then_reads(web, monkeypatch):
    web.dns["www.theguardian.com"] = [PUBLIC]
    web.pages["https://www.theguardian.com/us-news"] = (200, {"content-type": HTML}, SECTION)
    read_article.article_payload(url="https://www.theguardian.com/us-news")  # first refusal
    monkeypatch.setattr(read_article, "APPROVAL_WAIT_S", 4)

    def approval_lands(_seconds: float) -> None:
        with (web.state / "approved_sites.txt").open("a") as file:
            file.write("www.theguardian.com\n")

    monkeypatch.setattr(read_article.time, "sleep", approval_lands)
    assert read_article.article_payload(url="https://www.theguardian.com/us-news")["links"]


def test_retry_without_approval_is_refused_after_the_wait(web, monkeypatch):
    read_article.article_payload(url="https://evilbbc.co.uk/story")
    monkeypatch.setattr(read_article, "APPROVAL_WAIT_S", 0.05)
    monkeypatch.setattr(read_article.time, "sleep", lambda _seconds: None)
    assert read_article.article_payload(url="https://evilbbc.co.uk/story")["not_approved"] == "evilbbc.co.uk"
    assert web.calls == []


def test_refusal_is_recorded_even_when_the_conversation_cannot_be_checked(web, monkeypatch):
    def broken() -> int:
        raise OSError("connection refused")

    monkeypatch.setattr(read_article, "latest_seq", broken)
    assert read_article.article_payload(url="https://evilbbc.co.uk/story")["not_approved"] == "evilbbc.co.uk"
    assert json.loads((web.state / "pending_approval.json").read_text()) == {"evilbbc.co.uk": None}


def test_subdomains_of_an_approved_site_are_allowed(web):
    (web.state / "approved_sites.txt").write_text("bbc.co.uk\n")
    web.dns["www.bbc.co.uk"] = [PUBLIC]
    web.pages["https://www.bbc.co.uk/news"] = (200, {"content-type": HTML}, ARTICLE)
    assert read_article.article_payload(url="https://www.bbc.co.uk/news")["url"] == "https://www.bbc.co.uk/news"
    assert read_article.article_payload(url="https://notbbc.co.uk/")["not_approved"] == "notbbc.co.uk"


def test_redirect_to_an_unapproved_site_asks_for_permission(web):
    web.pages["https://news.example.org/away"] = (302, {"location": "https://elsewhere.co.uk/page"}, b"")
    assert read_article.article_payload(url="https://news.example.org/away")["not_approved"] == "elsewhere.co.uk"
    assert web.calls == [("https://news.example.org/away", PUBLIC)]


def test_seed_list_is_written_when_the_file_is_missing(web):
    (web.state / "approved_sites.txt").unlink()
    assert read_article.approved_sites() == list(read_article.SEED_SITES)
    assert approve_site.SEED_SITES == read_article.SEED_SITES


def test_refused_site_approved_by_the_user_then_reads(web, monkeypatch):
    web.dns["www.theguardian.com"] = [PUBLIC]
    web.pages["https://www.theguardian.com/us-news"] = (200, {"content-type": HTML}, SECTION)
    (web.state / "approved_sites.txt").write_text("example.org\n")
    assert read_article.article_payload(url="https://www.theguardian.com/us-news")["not_approved"]
    conversation = [
        {"role": "assistant", "text": "Shall I allow The Guardian?", "final": True, "seq": 101},
        {"role": "user", "text": "Yes", "final": True, "seq": 102},
    ]
    monkeypatch.setattr(approve_site, "history", lambda: conversation)
    assert approve_site.approve("www.theguardian.com")["approved"] == "www.theguardian.com"
    assert read_article.article_payload(url="https://www.theguardian.com/us-news")["links"]
