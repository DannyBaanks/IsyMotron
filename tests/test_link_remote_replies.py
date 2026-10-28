"""The CLI/console client must authenticate results from the HTTP transport."""

from contextlib import contextmanager
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core"))

from isymotron.link import envelope, identity, pairing, remote
from isymotron.link.server import LinkServer


@contextmanager
def _offices(tmp_path, alter_reply=None):
    caller_dir = tmp_path / "caller"
    caller = identity.load_identity(caller_dir, name="isytron-caller")
    identity.load_identity(tmp_path / "receiver", name="isytron-receiver")
    server = LinkServer(tmp_path / "receiver", tcp_port=0, udp_port=0)
    receiver = server.state.identity
    pairing.trust_peer(identity.public_card(caller), server.state.directory)
    pairing.trust_peer(
        identity.public_card(receiver, {"addresses": [server.tcp_address]}), caller_dir
    )
    if alter_reply is not None:
        original = server.http.RequestHandlerClass

        class AlteredReply(original):
            def _send(self, status, body):
                if self.path == "/link/v1/call" and status == 200:
                    body = alter_reply(body, caller, receiver)
                super()._send(status, body)

        server.http.RequestHandlerClass = AlteredReply
    server.start()
    try:
        yield caller_dir
    finally:
        server.stop()


def _unsigned(body, caller, receiver):
    return {key: value for key, value in body.items() if key != "renv"}


def _bad_signature(body, caller, receiver):
    body["renv"]["sig"] = "A" * len(body["renv"]["sig"])
    return body


def _wrong_request(body, caller, receiver):
    body["renv"] = envelope.seal(
        receiver,
        identity.public_card(caller),
        {"ok": True, "pong": True, "re": "a-different-request"},
    )
    return body


@pytest.mark.parametrize("alter", [_unsigned, _bad_signature, _wrong_request])
def test_client_rejects_unauthenticated_or_unbound_http_reply(tmp_path, alter):
    with _offices(tmp_path, alter) as directory:
        with pytest.raises(remote.LinkCallError, match="reply"):
            remote.sealed_call(directory, "receiver", {"op": "ping"})


def test_client_uses_authenticated_result_instead_of_unsigned_http_fields(tmp_path):
    def tamper_plaintext(body, caller, receiver):
        body["pong"] = False
        body["from"] = "a-different-office"
        return body

    with _offices(tmp_path, tamper_plaintext) as directory:
        result = remote.sealed_call(directory, "receiver", {"op": "ping"})
        peer = remote.resolve_peer(directory, "receiver")
        assert result["pong"] is True
        assert result["from"] == peer["office_id"]


def test_client_accepts_authenticated_reply_for_its_request(tmp_path):
    with _offices(tmp_path) as directory:
        result = remote.sealed_call(directory, "receiver", {"op": "ping"})
        assert result["ok"] is True
        assert result["pong"] is True
