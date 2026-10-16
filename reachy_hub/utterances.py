"""Submit typed user turns through the conversation app's existing JSON-RPC surface."""

import asyncio
import json

import websockets
from websockets.exceptions import WebSocketException


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
