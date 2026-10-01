"""M5: local agents request bounded leases; paired phones only approve or deny."""
import json
import sys
from pathlib import Path
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hosts"))

from isymotron.link import envelope, identity, pairing, receipts
from isymotron.link.server import LinkServer
from simulator.engines import ModernHost


def _post(url: str, payload: dict) -> tuple[int, dict]:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=10) as response:
        return response.status, json.loads(response.read() or b"{}")


def _get(url: str) -> tuple[int, dict]:
    with urlopen(url, timeout=10) as response:
        return response.status, json.loads(response.read() or b"{}")


def _sealed_call(phone_dir: Path, phone: dict, pc: dict, address: str, payload: dict) -> dict:
    env = envelope.seal(phone, identity.public_card(pc), payload)
    _, body = _post(f"http://{address}/link/v1/call", {"env": env})
    _, opened = envelope.open_envelope(
        phone, identity.load_peers(phone_dir), body["renv"], {}
    )
    return opened


def _paired(tmp_path: Path, host: ModernHost) -> tuple[Path, dict, LinkServer]:
    pc_dir = tmp_path / "pc"
    phone_dir = tmp_path / "phone"
    pc = identity.load_identity(pc_dir, name="isytron-pc")
    phone = identity.load_identity(phone_dir, name="isytron-phone")
    pairing.trust_peer(identity.public_card(phone), pc_dir)
    pairing.trust_peer(identity.public_card(pc), phone_dir)
    server = LinkServer(pc_dir, tcp_port=0, udp_port=0, permission_host=host).start()
    return phone_dir, phone, server


def test_paired_phone_can_approve_a_locally_queued_narrow_lease(tmp_path):
    host = ModernHost(
        {},
        granted=["filesystem.read"],
        grant_scopes={"filesystem.read": {"roots": ["C:/Photos", "C:/Shared"]}},
        max_lease_ttl_s=30,
    )
    phone_dir, phone, server = _paired(tmp_path, host)
    try:
        status, created = _post(
            f"http://{server.tcp_address}/link/v1/local/permissions",
            {
                "subject": "agent:planner",
                "capability": "filesystem.read",
                "scope": {"roots": ["C:/Photos", "C:/Secrets"]},
                "ttl_s": 90,
                "reason": "Read the requested photo",
            },
        )
        assert status == 201
        request_id = created["request"]["request_id"]
        assert created["request"]["status"] == "pending"

        listed = _sealed_call(
            phone_dir, phone, server.state.identity,
            server.tcp_address, {"op": "permissions"},
        )
        assert listed["requests"] == [
            {
                "request_id": request_id,
                "subject": "agent:planner",
                "capability": "filesystem.read",
                "scope": {"roots": ["C:/Photos", "C:/Secrets"]},
                "ttl_s": 90,
                "reason": "Read the requested photo",
                "status": "pending",
            }
        ]

        decided = _sealed_call(
            phone_dir, phone, server.state.identity, server.tcp_address,
            {"op": "permission_decide", "request_id": request_id, "decision": "approve"},
        )
        assert decided["status"] == "approved"
        local_status, local = _get(
            f"http://{server.tcp_address}/link/v1/local/permissions/{request_id}"
        )
        assert local_status == 200
        lease = local["request"]["lease"]
        assert lease["scope"] == {"roots": ["C:/Photos"]}
        assert lease["expires_at"] - lease["issued_at"] <= 30
        assert host.validate_lease(lease["lease_id"])
        assert receipts.read_receipts(server.state.directory, "link_permission_decided") == [
            {
                "kind": "link_permission_decided",
                "ts": receipts.read_receipts(server.state.directory)[-1]["ts"],
                "request_id": request_id,
                "subject": "agent:planner",
                "capability": "filesystem.read",
                "decision": "approved",
                "decision_reason": "",
                "lease_id": lease["lease_id"],
                "by": phone["office_id"],
            }
        ]
    finally:
        server.stop()


def test_phone_denial_never_mints_a_lease_and_is_recorded(tmp_path):
    host = ModernHost({}, granted=["system.info"], grant_scopes={"system.info": {}})
    phone_dir, phone, server = _paired(tmp_path, host)
    try:
        _, created = _post(
            f"http://{server.tcp_address}/link/v1/local/permissions",
            {"subject": "agent:planner", "capability": "system.info", "scope": {}, "ttl_s": 60},
        )
        request_id = created["request"]["request_id"]
        result = _sealed_call(
            phone_dir, phone, server.state.identity, server.tcp_address,
            {"op": "permission_decide", "request_id": request_id, "decision": "deny"},
        )
        assert result["status"] == "denied"
        _, local = _get(
            f"http://{server.tcp_address}/link/v1/local/permissions/{request_id}"
        )
        assert local["request"]["status"] == "denied"
        assert "lease" not in local["request"]
        assert host._leases == {}
        receipt = receipts.read_receipts(server.state.directory, "link_permission_decided")[-1]
        assert receipt["decision"] == "denied"
        assert receipt["by"] == phone["office_id"]
    finally:
        server.stop()


def test_phone_approval_cannot_override_local_host_grants(tmp_path):
    host = ModernHost({}, granted=[], grant_scopes={})
    phone_dir, phone, server = _paired(tmp_path, host)
    try:
        _, created = _post(
            f"http://{server.tcp_address}/link/v1/local/permissions",
            {"subject": "agent:planner", "capability": "system.info", "scope": {}, "ttl_s": 60},
        )
        request_id = created["request"]["request_id"]
        result = _sealed_call(
            phone_dir, phone, server.state.identity, server.tcp_address,
            {"op": "permission_decide", "request_id": request_id, "decision": "approve"},
        )
        assert result["status"] == "denied"
        assert result["decision_reason"] == "CAPABILITY_NOT_GRANTED"
        _, local = _get(
            f"http://{server.tcp_address}/link/v1/local/permissions/{request_id}"
        )
        assert local["request"]["status"] == "denied"
        assert "lease" not in local["request"]
        assert host._leases == {}
        receipt = receipts.read_receipts(server.state.directory, "link_permission_decided")[-1]
        assert receipt["decision_reason"] == "CAPABILITY_NOT_GRANTED"
        assert receipt["by"] == phone["office_id"]
    finally:
        server.stop()


def test_unpaired_office_cannot_list_or_decide_permissions(tmp_path):
    host = ModernHost({}, granted=["system.info"], grant_scopes={"system.info": {}})
    _, _, server = _paired(tmp_path, host)
    outsider_dir = tmp_path / "outsider"
    outsider = identity.load_identity(outsider_dir, name="intruder")
    try:
        env = envelope.seal(
            outsider,
            identity.public_card(server.state.identity),
            {"op": "permissions"},
        )
        try:
            _post(f"http://{server.tcp_address}/link/v1/call", {"env": env})
        except Exception as exc:
            assert getattr(exc, "code", None) == 403 or getattr(exc, "status", None) == 403
            assert getattr(exc, "code", None) is not None or getattr(exc, "status", None) == 403
        else:
            raise AssertionError("unpaired office read the permission queue")
    finally:
        server.stop()
