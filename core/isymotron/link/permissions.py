"""Host-owned queue for short-lived permission (lease) requests from local agents."""
from __future__ import annotations

import json
import math
import threading
import time
import uuid
from pathlib import Path
from typing import Any

REQUEST_TTL_S = 15 * 60
MAX_PENDING = 100


class PermissionQueueError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.status = status


class PermissionQueue:
    """Persist local-agent requests; only the host can mint a lease."""

    def __init__(self, directory: Path, host: Any):
        self.directory = directory
        self.host = host
        self.path = directory / "permission_requests.jsonl"
        self._lock = threading.RLock()
        self._issued: dict[str, Any] = {}
        self._mark_lost_leases()

    def _mark_lost_leases(self) -> None:
        """A host restart drops in-memory leases; never report them as usable."""
        with self._lock:
            for item in self._latest().values():
                if item.get("status") != "approved":
                    continue
                updated = {
                    **item,
                    "status": "expired",
                    "decision_reason": "host_restarted",
                    "lease_id": None,
                }
                self._append(updated)
                from . import receipts

                receipts.append_receipt(
                    self.directory,
                    "link_permission_decided",
                    {"request_id": item["request_id"], "subject": item["subject"],
                     "capability": item["capability"], "decision": "expired",
                     "decision_reason": "host_restarted", "lease_id": None,
                     "by": "host:restart",
                     "tool_profile": getattr(self.host, "tool_profile", "unknown")},
                )

    def _latest(self) -> dict[str, dict]:
        latest: dict[str, dict] = {}
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return latest
        for line in lines:
            try:
                item = json.loads(line)
                if isinstance(item, dict) and isinstance(item.get("request_id"), str):
                    latest[item["request_id"]] = item
            except ValueError:
                continue
        return latest

    def _append(self, item: dict) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")

    @staticmethod
    def _public(item: dict, *, include_lease: bool = False, lease: dict | None = None) -> dict:
        result = {
            key: item[key]
            for key in ("request_id", "subject", "capability", "scope", "ttl_s", "reason", "status")
            if key in item
        }
        if item.get("decision_reason"):
            result["decision_reason"] = item["decision_reason"]
        if include_lease and lease is not None:
            result["lease"] = lease
        return result

    def submit(self, body: dict) -> dict:
        subject = body.get("subject")
        capability = body.get("capability")
        scope = body.get("scope", {})
        reason = body.get("reason", "")
        ttl = body.get("ttl_s", 120)
        if not isinstance(subject, str) or not subject.strip() or len(subject) > 120:
            raise PermissionQueueError("bad_request", "subject must be 1–120 characters")
        if not isinstance(capability, str) or not capability.strip() or len(capability) > 128:
            raise PermissionQueueError("bad_request", "capability must be 1–128 characters")
        if not isinstance(scope, dict):
            raise PermissionQueueError("bad_request", "scope must be an object")
        if not isinstance(reason, str) or len(reason) > 280:
            raise PermissionQueueError("bad_request", "reason must be at most 280 characters")
        if isinstance(ttl, bool) or not isinstance(ttl, (int, float)) or not math.isfinite(ttl) or ttl <= 0 or ttl > 86400:
            raise PermissionQueueError("bad_request", "ttl_s must be greater than 0 and at most 86400")
        # Ensure the stored scope is JSON data, not a caller-owned mutable object.
        try:
            scope = json.loads(json.dumps(scope, allow_nan=False))
        except (TypeError, ValueError):
            raise PermissionQueueError("bad_request", "scope must contain JSON values") from None

        with self._lock:
            latest = self._latest()
            pending = sum(item.get("status") == "pending" for item in latest.values())
            if pending >= MAX_PENDING:
                raise PermissionQueueError("busy", "too many pending permission requests", 429)
            item = {
                "request_id": f"permission-{uuid.uuid4().hex}",
                "subject": subject.strip(),
                "capability": capability.strip(),
                "scope": scope,
                "ttl_s": float(ttl),
                "reason": reason.strip(),
                "status": "pending",
                "created_at": time.time(),
                "expires_at": time.time() + REQUEST_TTL_S,
            }
            self._append(item)
            return self._public(item)

    def pending(self) -> list[dict]:
        now = time.time()
        with self._lock:
            items = self._latest()
            out = []
            for item in items.values():
                if item.get("status") != "pending":
                    continue
                if float(item.get("expires_at", 0)) <= now:
                    item = {**item, "status": "expired", "decision_reason": "request_timeout"}
                    self._append(item)
                    from . import receipts

                    receipts.append_receipt(
                        self.directory,
                        "link_permission_decided",
                        {"request_id": item["request_id"], "subject": item["subject"],
                         "capability": item["capability"], "decision": "expired", "by": "host:timeout",
                         "tool_profile": getattr(self.host, "tool_profile", "unknown")},
                    )
                    continue
                out.append(item)
            out.sort(key=lambda item: (float(item.get("created_at", 0)), item["request_id"]))
            return [self._public(item) for item in out]

    def local_status(self, request_id: str) -> dict | None:
        with self._lock:
            item = self._latest().get(request_id)
            if item is None:
                return None
            if item.get("status") == "pending" and float(item.get("expires_at", 0)) <= time.time():
                item = {**item, "status": "expired", "decision_reason": "request_timeout"}
                self._append(item)
                from . import receipts

                receipts.append_receipt(
                    self.directory,
                    "link_permission_decided",
                    {"request_id": item["request_id"], "subject": item["subject"],
                     "capability": item["capability"], "decision": "expired",
                     "decision_reason": "request_timeout", "lease_id": None,
                     "by": "host:timeout",
                     "tool_profile": getattr(self.host, "tool_profile", "unknown")},
                )
            lease = self._issued.get(request_id)
            if lease is not None and not self.host.validate_lease(lease.lease_id):
                self._issued.pop(request_id, None)
                lease = None
            return self._public(item, include_lease=True, lease=lease.to_dict() if lease else None)

    def decide(self, request_id: str, decision: str, office_id: str) -> dict:
        if decision not in ("approve", "deny"):
            raise PermissionQueueError("bad_decision", "decision must be approve or deny")
        with self._lock:
            item = self._latest().get(request_id)
            if item is None:
                raise PermissionQueueError("no_such_request", "permission request not found", 404)
            if item.get("status") != "pending":
                raise PermissionQueueError("already_decided", "permission request is no longer pending", 409)
            if float(item.get("expires_at", 0)) <= time.time():
                status, decision_reason, lease = "expired", "request_timeout", None
            elif decision == "deny":
                status, decision_reason, lease = "denied", "human_denied", None
            else:
                # Approvals mint through the new approval path (security/custom),
                # falling back to the classic grant lookup when the host
                # predates the profile model.
                mint = getattr(self.host, "mint_approved_lease", None)
                if mint is not None:
                    lease, policy = mint(
                        item["subject"], item["capability"], item["scope"], item["ttl_s"]
                    )
                else:
                    lease, policy = self.host.request_lease(
                        item["subject"], item["capability"], item["ttl_s"], item["scope"]
                    )
                if lease is None:
                    status = "denied"
                    decision_reason = policy.reason.value if policy.reason else "host_denied"
                else:
                    status, decision_reason = "approved", ""
                    self._issued[request_id] = lease
            updated = {
                **item,
                "status": status,
                "decision_reason": decision_reason,
                "decided_at": time.time(),
                "decided_by": office_id,
                "lease_id": lease.lease_id if lease is not None else None,
            }
            self._append(updated)
            from . import receipts

            receipts.append_receipt(
                self.directory,
                "link_permission_decided",
                {"request_id": request_id, "subject": item["subject"],
                 "capability": item["capability"], "decision": status,
                 "decision_reason": decision_reason, "lease_id": lease.lease_id if lease else None,
                 "by": office_id,
                 "tool_profile": getattr(self.host, "tool_profile", "unknown")},
            )
            return {"request_id": request_id, "status": status, "decision_reason": decision_reason}
