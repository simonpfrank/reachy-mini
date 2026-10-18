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


async def test_no_active_session_is_retried_once_after_the_reconnect(monkeypatch):
    peers = iter([
        RpcConnection(['{"id":1,"error":{"message":"no active session"}}']),
        RpcConnection(['{"id":1,"result":{"ok":true}}']),
    ])
    monkeypatch.setattr(utterances.websockets, "connect", lambda *args, **kwargs: next(peers))
    waits: list[float] = []

    async def wait(seconds: float) -> None:
        waits.append(seconds)

    monkeypatch.setattr(utterances.asyncio, "sleep", wait)
    await utterances.send_with_reconnect("ws://robot/rpc", "Hello")
    assert waits == [utterances.RECONNECT_WAIT_S]


@pytest.mark.parametrize(("message", "attempts"), [("no active session", 2), ("say requires text", 1)])
async def test_only_one_retry_and_only_for_no_active_session(monkeypatch, message, attempts):
    connects: list[int] = []

    def rejecting(*args, **kwargs):
        connects.append(1)
        return RpcConnection([json.dumps({"id": 1, "error": {"message": message}})])

    async def wait(_seconds: float) -> None:
        pass

    monkeypatch.setattr(utterances.websockets, "connect", rejecting)
    monkeypatch.setattr(utterances.asyncio, "sleep", wait)
    with pytest.raises(utterances.UtteranceError, match=message):
        await utterances.send_with_reconnect("ws://robot/rpc", "Hello")
    assert len(connects) == attempts


async def test_typed_text_is_recorded_with_the_conversation_position(monkeypatch, tmp_path):
    peer = RpcConnection([
        '{"jsonrpc":"2.0","method":"conversation.turn","params":{"state":"listening"}}',
        '{"jsonrpc":"2.0","id":1,"result":{"events":[{"method":"conversation.transcript","params":{"seq":7}},'
        '{"method":"conversation.latency","params":{"seq":9}}]}}',
    ])
    connect(monkeypatch, peer)
    log = tmp_path / "typed_messages.jsonl"
    assert await utterances.record_typed("ws://robot/rpc", "yes", log) is True
    assert peer.requests[0]["method"] == "conversation.history"
    assert [json.loads(line) for line in log.read_text().splitlines()] == [{"text": "yes", "after_seq": 9}]


async def test_typed_log_keeps_only_recent_messages(monkeypatch, tmp_path):
    log = tmp_path / "typed_messages.jsonl"
    log.write_text("".join(json.dumps({"text": f"m{n}", "after_seq": n}) + "\n" for n in range(60)))
    connect(monkeypatch, RpcConnection(['{"id":1,"result":{"events":[]}}']))
    await utterances.record_typed("ws://robot/rpc", "new", log)
    lines = log.read_text().splitlines()
    assert len(lines) == utterances.TYPED_KEEP and json.loads(lines[-1]) == {"text": "new", "after_seq": 0}


async def test_unreadable_position_records_nothing(monkeypatch, tmp_path):
    def refused(*args, **kwargs):
        raise ConnectionRefusedError

    monkeypatch.setattr(utterances.websockets, "connect", refused)
    log = tmp_path / "typed_messages.jsonl"
    assert await utterances.record_typed("ws://robot/rpc", "yes", log) is False
    assert not log.exists()


@pytest.mark.parametrize("messages", [[], ["not JSON"], ['{"id":1,"result":{"ok":false}}']])
async def test_closed_or_invalid_response_never_claims_success(monkeypatch, messages):
    peer = RpcConnection(messages)
    connect(monkeypatch, peer)
    with pytest.raises(utterances.UtteranceError):
        await utterances.send_utterance("ws://robot/rpc", "Hello")
    assert len(peer.requests) == 1
