"""Check typed input follows the app RPC contract and is never retried ambiguously."""

import asyncio
import json

import pytest

from reachy_hub import utterances


class RpcConnection:
    """An RPC peer that can broadcast before acknowledging, reject, or stop replying."""

    def __init__(self, messages, hold=False):
        self.messages = messages
        self.hold = hold
        self.requests = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def send(self, raw):
        self.requests.append(json.loads(raw))

    def __aiter__(self):
        return self.receive()

    async def receive(self):
        for message in self.messages:
            yield message
        if self.hold:
            await asyncio.Event().wait()


def connect(monkeypatch, peer):
    monkeypatch.setattr(utterances.websockets, "connect", lambda *args, **kwargs: peer)


async def test_sends_user_turn_and_ignores_broadcasts_and_other_reply_ids(monkeypatch):
    peer = RpcConnection([
        '{"jsonrpc":"2.0","method":"conversation.turn","params":{"state":"listening"}}',
        '{"jsonrpc":"2.0","id":99,"result":{"ok":true}}',
        '{"jsonrpc":"2.0","id":1,"result":{"ok":true}}',
    ])
    connect(monkeypatch, peer)
    await utterances.send_utterance("ws://robot/rpc", "Stop following my voice")
    assert peer.requests == [{
        "jsonrpc": "2.0", "id": 1, "method": "conversation.say",
        "params": {"text": "Stop following my voice"},
    }]


async def test_rejection_is_reported_without_retry(monkeypatch):
    peer = RpcConnection(['{"id":1,"error":{"message":"no active session"}}'])
    connect(monkeypatch, peer)
    with pytest.raises(utterances.UtteranceError, match="no active session"):
        await utterances.send_utterance("ws://robot/rpc", "Hello")
    assert len(peer.requests) == 1


async def test_missing_ack_times_out_without_retrying_or_claiming_delivery(monkeypatch):
    peer = RpcConnection([], hold=True)
    connect(monkeypatch, peer)
    with pytest.raises(utterances.UtteranceError, match="check logs before retrying") as error:
        await utterances.send_utterance("ws://robot/rpc", "Hello", timeout_s=0.02)
    assert error.value.status_code == 504
    assert len(peer.requests) == 1


async def test_connection_failure_reports_unavailable(monkeypatch):
    def refused(*args, **kwargs):
        raise ConnectionRefusedError

    monkeypatch.setattr(utterances.websockets, "connect", refused)
    with pytest.raises(utterances.UtteranceError) as error:
        await utterances.send_utterance("ws://robot/rpc", "Hello")
    assert error.value.status_code == 503


@pytest.mark.parametrize("messages", [[], ["not JSON"], ['{"id":1,"result":{"ok":false}}']])
async def test_closed_or_invalid_response_never_claims_success(monkeypatch, messages):
    peer = RpcConnection(messages)
    connect(monkeypatch, peer)
    with pytest.raises(utterances.UtteranceError):
        await utterances.send_utterance("ws://robot/rpc", "Hello")
    assert len(peer.requests) == 1
