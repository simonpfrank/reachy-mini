"""Submit typed user turns through the conversation app's existing JSON-RPC surface.

The app keeps no record of typed turns, so each one is also noted in typed_messages.jsonl (tool state
directory) with the app's history position, for approve_site to count as the user's own words.
"""

import asyncio
import json
import logging
import os
from pathlib import Path

import websockets
from websockets.exceptions import WebSocketException

LOG = logging.getLogger(__name__)
TYPED_KEEP = 50
RECONNECT_WAIT_S = 7.0  # the app retries its backend after 5 s and is ready about a second later
NO_SESSION = "no active session"


def typed_log() -> Path:
    """Where typed turns are noted: the same state directory the robot tools use."""
    state = Path(os.environ.get("REACHY_TOOLS_STATE_DIR", "~/.config/reachy_tools")).expanduser()
    return state / "typed_messages.jsonl"


async def record_typed(url: str, text: str, path: Path | None = None, timeout_s: float = 3.0) -> bool:
    """Note typed text with the app's latest history position; False, noting nothing, if it cannot be read."""
    request = {"jsonrpc": "2.0", "id": 1, "method": "conversation.history", "params": {}}
    try:
        async with asyncio.timeout(timeout_s):
            async with websockets.connect(url, open_timeout=3, close_timeout=1) as connection:
                await connection.send(json.dumps(request))
                async for raw in connection:
                    reply = json.loads(raw)
                    if isinstance(reply, dict) and reply.get("id") == 1:
                        break
                else:
                    return False
        seq = max((int(e["params"]["seq"]) for e in reply["result"]["events"]), default=0)
    except (TimeoutError, OSError, WebSocketException, ValueError, KeyError, TypeError) as exc:
        LOG.warning("typed text not recorded for approvals: %s", exc)
        return False
    path = path or typed_log()
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text().splitlines() if path.exists() else []
    lines.append(json.dumps({"text": text, "after_seq": seq}))
    path.write_text("\n".join(lines[-TYPED_KEEP:]) + "\n")
    return True


class UtteranceError(Exception):
    """An instruction could not be confirmed by the running conversation app."""

    def __init__(self, message: str, status_code: int = 502) -> None:
        """Keep a user-facing explanation and the matching HTTP status."""
        super().__init__(message)
        self.status_code = status_code


async def send_utterance(url: str, text: str, timeout_s: float = 10.0) -> None:
    """Send one user turn, ignoring broadcasts while waiting for its RPC acknowledgement.

    Never retry automatically: a lost acknowledgement does not establish that the text was not delivered.
    """
    request = {"jsonrpc": "2.0", "id": 1, "method": "conversation.say", "params": {"text": text}}
    try:
        async with asyncio.timeout(timeout_s):
            async with websockets.connect(url, open_timeout=5, close_timeout=1) as connection:
                await connection.send(json.dumps(request))
                async for raw in connection:
                    reply = json.loads(raw)
                    if not isinstance(reply, dict) or reply.get("id") != request["id"]:
                        continue
                    if "error" in reply:
                        error = reply["error"]
                        detail = error.get("message", "request rejected") if isinstance(error, dict) else str(error)
                        raise UtteranceError(f"Conversation app rejected the instruction: {detail}")
                    result = reply.get("result")
                    if not isinstance(result, dict) or result.get("ok") is not True:
                        raise UtteranceError("Conversation app did not acknowledge the instruction")
                    return
                raise UtteranceError(
                    "Conversation connection closed before acknowledgement; check logs before retrying"
                )
    except TimeoutError as exc:
        raise UtteranceError("Instruction delivery timed out; check logs before retrying", 504) from exc
    except (OSError, WebSocketException) as exc:
        raise UtteranceError(
            "Cannot reach the conversation app; check it is running and check logs before retrying", 503
        ) from exc
    except ValueError as exc:
        raise UtteranceError("Conversation app returned an invalid response; check logs before retrying") from exc


async def send_with_reconnect(url: str, text: str) -> None:
    """Send one user turn; if the app's backend session has just dropped, wait for its reconnect and send once more.

    Safe to repeat only for "no active session": the app refuses before delivering anything.
    """
    try:
        await send_utterance(url, text)
    except UtteranceError as exc:
        if NO_SESSION not in str(exc):
            raise
        LOG.info("conversation app has no active session; retrying once in %.0f s", RECONNECT_WAIT_S)
        await asyncio.sleep(RECONNECT_WAIT_S)
        await send_utterance(url, text)
