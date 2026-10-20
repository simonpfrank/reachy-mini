"""On-device tool: approve a website for read_article, only when the user said yes in conversation.

The model cannot approve on its own. A site is added to approved_sites.txt only if read_article refused that
exact site (recorded in pending_approval.json with the conversation position), the robot's own words after the
refusal named the site, and the user's next words say yes with no "no". The words come from the conversation
app's transcript history over its /rpc, plus text typed in the hub (which the hub records in
typed_messages.jsonl, since the app keeps no record of typed turns), never from the model. Approval is permanent;
remove a site by deleting its line. Accepted gap: another voice (e.g. the TV) saying yes at that moment.
"""

import asyncio
import json
import logging
import os
import re
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any

from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies
from websockets.sync.client import connect

sys.path.insert(0, str(Path(__file__).resolve().parent))  # the app loads tools by path; see reachy_lib
from reachy_lib.storage import state_dir  # noqa: E402

LOG = logging.getLogger(__name__)
SEED_SITES = ("bbc.co.uk", "bbc.com", "theguardian.com", "reuters.com", "apnews.com", "metoffice.gov.uk")
SITE = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}$")
RPC_URL = os.environ.get("REACHY_APP_RPC_URL", "ws://127.0.0.1:7860/rpc")
ANSWER_WAIT_S = 3.0  # the user's transcript can arrive just after the model's tool call
YES = frozenset({"yes", "yeah", "yep", "yup", "sure", "ok", "okay", "allow", "approve", "fine"})
NO = frozenset({"no", "nope", "not", "don't", "dont", "never", "stop", "cancel"})
SECOND_LEVEL = frozenset({"co", "com", "org", "gov", "ac", "net"})  # e.g. bbc.co.uk


def host_of(site: str) -> str:
    """The website name in ``site`` (a name or URL), or ValueError."""
    if not isinstance(site, str) or not site.strip():
        raise ValueError("site must be a website name, e.g. theguardian.com")
    raw = site.strip().lower()
    host = ((urllib.parse.urlsplit(raw).hostname if "//" in raw else raw.split("/")[0]) or "").rstrip(".")
    if not SITE.match(host):
        raise ValueError(f"{site} is not a website name")
    return host


def site_name(host: str) -> str:
    """The word the robot must say for the site: news.sky.com -> sky, www.bbc.co.uk -> bbc."""
    labels = host.split(".")[:-1]
    if len(labels) > 1 and labels[-1] in SECOND_LEVEL:
        labels = labels[:-1]
    return labels[-1]


def history() -> list[dict[str, Any]]:
    """The conversation app's transcripts (role, text, final, seq), from its JSON-RPC history."""
    with connect(RPC_URL, open_timeout=3, close_timeout=1) as socket:
        socket.send(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "conversation.history", "params": {}}))
        while True:  # broadcasts can arrive before the reply
            message = json.loads(socket.recv(timeout=5))
            if message.get("id") == 1:
                break
    if "result" not in message:
        raise RuntimeError(f"conversation.history failed: {message.get('error')}")
    return [event["params"] for event in message["result"]["events"] if event["method"] == "conversation.transcript"]


def typed() -> list[dict[str, Any]]:
    """Text typed in the hub, as user turns placed just after the conversation position it was sent at."""
    path = state_dir() / "typed_messages.jsonl"
    lines = path.read_text().splitlines() if path.exists() else []
    records = [json.loads(line) for line in lines if line.strip()]
    return [{"role": "user", "text": r["text"], "final": True, "seq": r["after_seq"] + 0.5} for r in records]


def is_yes(text: str) -> bool:
    """A clear yes: a yes word and no "no" word."""
    words = set(re.findall(r"[a-z']+", text.lower()))
    return bool(words & YES) and not words & NO


def verdict(host: str, refused_seq: int, events: list[dict[str, Any]]) -> tuple[str, str]:
    """("approved" | "waiting" | "refused", reason), from what was said after the refusal.

    Approved when, after any robot line naming the site, the user's next words are a clear yes.
    """
    name = site_name(host)
    later = sorted((e for e in events if e.get("final") and e["seq"] > refused_seq), key=lambda e: e["seq"])
    asks = [e for e in later if e["role"] == "assistant" and name in re.sub(r"[^a-z0-9]", "", e["text"].lower())]
    if not asks:
        return "refused", f"You have not asked the user. Ask whether to allow reading {host}, naming it."
    replies = [next((e for e in later if e["role"] == "user" and e["seq"] > ask["seq"]), None) for ask in asks]
    if any(reply is not None and is_yes(reply["text"]) for reply in replies):
        return "approved", ""
    if replies[-1] is None:
        return "waiting", f"The user has not answered yet. Wait for their answer about {host}, then call again."
    return "refused", f"The user did not say yes, so {host} was not approved."


def approve(site: str) -> dict[str, Any]:
    """Add a refused site to the approved list if the user said yes to it in conversation."""
    host = host_of(site)
    pending_path = state_dir() / "pending_approval.json"
    pending: dict[str, int | None] = json.loads(pending_path.read_text()) if pending_path.exists() else {}
    if host not in pending:
        return {"approved": None, "refused": f"Only the exact site read_article refused can be approved, not {host}."}
    refused_seq = pending[host]
    deadline = time.monotonic() + ANSWER_WAIT_S
    try:
        if refused_seq is None:
            raise RuntimeError("no conversation position was recorded at the refusal")
        status, reason = verdict(host, refused_seq, history() + typed())
        while status == "waiting" and time.monotonic() < deadline:
            time.sleep(0.3)
            status, reason = verdict(host, refused_seq, history() + typed())
    except Exception as error:  # any failure to read the conversation approves nothing
        LOG.warning("approve_site unchecked site=%s error=%s", host, error)
        return {"approved": None, "refused": f"The conversation could not be checked, so {host} was not approved."}
    if status != "approved":
        LOG.info("approve_site refused site=%s status=%s", host, status)
        return {"approved": None, "refused": reason}
    path = state_dir() / "approved_sites.txt"
    if not path.exists():
        path.write_text("\n".join(SEED_SITES) + "\n")
    already = host in path.read_text().split()
    if not already:
        with path.open("a") as file:
            file.write(host + "\n")
    del pending[host]
    pending_path.write_text(json.dumps(pending))
    LOG.info("approve_site approved site=%s", host)
    note = f"Approved {host}. Now repeat the call that was refused."
    return {"approved": host, "already_approved": already, "note": note}


class ApproveSite(Tool):  # type: ignore[misc]
    """Add a website to the sites read_article may read, after the user says yes."""

    name = "approve_site"
    description = (
        "Approve a website that read_article replied not_approved for. First ask the user whether to allow "
        "that site, saying its name, and wait for their answer. It is approved only if the user really said "
        "yes; otherwise it replies refused with the reason. Approval is permanent. Once approved, repeat the call "
        "that was refused."
    )
    parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {"site": {"type": "string", "description": "The exact site read_article reported."}},
        "required": ["site"],
    }

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> dict[str, Any]:
        """Check and approve without blocking the conversation loop."""
        try:
            return await asyncio.to_thread(approve, kwargs.get("site", ""))
        except Exception as error:
            LOG.warning("approve_site failed: %s", error)
            raise
