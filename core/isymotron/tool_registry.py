"""Local authority for extensible tools. Installation and approval are distinct."""
from __future__ import annotations

import contextlib
import hashlib
import hmac
import json
import os
import secrets
import stat
import tempfile
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from .canon import canonical, digest
from .tool_contract import ToolError, ToolPackage, relative_name, require
from .tool_provider import LinuxPythonProvider


class ToolRegistry:
    def __init__(self, root: str | Path, providers=None):
        self.root = Path(root).absolute()
        require(not self.root.is_symlink(), 'registry must not be a symlink')
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.providers = providers if providers is not None else {'linux-python/v1': LinuxPythonProvider()}
        for name in ('packages', 'records'):
            folder = self.root / name
            require(not folder.is_symlink(), 'invalid registry directory')
            folder.mkdir(exist_ok=True, mode=0o700)
        key = self.root / '.authority-key'
        require(not key.is_symlink(), 'invalid authority key')
        try:
            fd = os.open(key, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError: pass
        else:
            with os.fdopen(fd, 'wb') as out: out.write(secrets.token_bytes(32))
        self._key = key.read_bytes()
        require(len(self._key) == 32, 'invalid authority key')

    @contextlib.contextmanager
    def _lock(self):
        with (self.root / '.lock').open('a') as lock:
            if os.name == 'posix':
                import fcntl
                fcntl.flock(lock, fcntl.LOCK_EX)
            try: yield
            finally:
                if os.name == 'posix': fcntl.flock(lock, fcntl.LOCK_UN)

    def _seal(self, value: dict) -> str:
        return 'hmac-sha256:' + hmac.new(self._key, canonical(value).encode(), hashlib.sha256).hexdigest()

    def _path(self, tool_id: str) -> Path:
        require(isinstance(tool_id, str) and relative_name(tool_id) == tool_id and '/' not in tool_id, 'invalid tool id')
        return self.root / 'records' / (tool_id + '.json')

    def _load(self, tool_id: str) -> dict:
        path = self._path(tool_id)
        require(path.is_file() and not path.is_symlink(), 'unknown tool', 'NOT_FOUND')
        try:
            data = json.loads(path.read_text())
            seal = data.pop('authority_seal')
            require(hmac.compare_digest(seal, self._seal(data)), 'registry record integrity failed', 'STALE')
            require(data['tool_id'] == tool_id, 'wrong tool record', 'STALE')
            return data
        except (ValueError, KeyError, TypeError) as error:
            if isinstance(error, ToolError): raise
            raise ToolError('STALE', 'invalid registry record') from error

    def _save(self, record: dict) -> None:
        data = {**record, 'authority_seal': self._seal(record)}
        fd, name = tempfile.mkstemp(dir=self.root / 'records', prefix='.record-')
        try:
            with os.fdopen(fd, 'w') as out: out.write(canonical(data))
            os.replace(name, self._path(record['tool_id']))
        finally:
            Path(name).unlink(missing_ok=True)

    def _package(self, record: dict) -> ToolPackage:
        identifier = record['package_digest']
        require(identifier.startswith('sha256:') and len(identifier) == 71, 'invalid package digest', 'STALE')
        try: package = ToolPackage.load(self.root / 'packages' / identifier[7:])
        except (ToolError, OSError) as exc: raise ToolError('STALE', 'package snapshot changed') from exc
        require(package.package_digest == identifier, 'package snapshot changed', 'STALE')
        return package

    def _provider(self, package: ToolPackage):
        provider = self.providers.get(package.contract['provider'])
        require(provider is not None, 'provider is not installed', 'PROVIDER_UNAVAILABLE')
        return provider

    def stage(self, package_path: str | Path) -> dict:
        package = ToolPackage.load(package_path)
        with self._lock():
            dest = self.root / 'packages' / package.package_digest[7:]
            if not dest.exists():
                staging = Path(tempfile.mkdtemp(dir=self.root / 'packages', prefix='.stage-'))
                try: package.write(staging); staging.rename(dest)
                finally:
                    if staging.exists():
                        import shutil
                        shutil.rmtree(staging)
            else: require(ToolPackage.load(dest).package_digest == package.package_digest, 'stored snapshot changed', 'STALE')
            record = {'tool_id': package.tool_id, 'package_digest': package.package_digest,
                      'state': 'DRAFT', 'verification': None, 'approval': None}
            self._save(record)
        return {'tool_id': package.tool_id, 'package_digest': package.package_digest, 'state': 'DRAFT'}

    def verify(self, tool_id: str) -> dict:
        with self._lock():
            record = self._load(tool_id); record.update(state='DRAFT', approval=None, verification=None); self._save(record)
            package = self._package(record)
        try:
            report = self._provider(package).verify(package)
        except ToolError as error:
            with self._lock():
                current = self._load(tool_id)
                if current['package_digest'] == record['package_digest']:
                    current.update(state='REJECTED', error={'code': error.code, 'detail': error.detail}); self._save(current)
            raise
        with self._lock():
            current = self._load(tool_id)
            require(current['package_digest'] == package.package_digest, 'package changed during verification', 'STALE')
            current.update(state='AWAITING_APPROVAL', verification=report, approval=None)
            self._save(current)
        return report

    def _verified(self, record: dict, package: ToolPackage) -> dict:
        report = record.get('verification') or {}
        plan = self._provider(package).compile(package)
        require(report.get('verdict') == 'PASS_FOR_SCOPE' and report.get('package_digest') == package.package_digest
                and report.get('plan_digest') == digest(plan), 'verification missing or outdated', 'STALE')
        return plan

    def approve(self, tool_id: str, *, subject: str, host_id: str, read_roots: dict, write_roots: dict, ttl_s: float = 3600) -> dict:
        require(isinstance(subject, str) and subject and isinstance(host_id, str) and host_id, 'subject and host required')
        require(type(ttl_s) in (int, float) and 0 < ttl_s <= 86400, 'approval expires within 24 hours')
        roots = {}
        for key, values in [('read_roots', read_roots), ('write_roots', write_roots)]:
            require(isinstance(values, dict), 'roots must be a mapping')
            roots[key] = {}
            for name, value in values.items():
                relative_name(name); require('/' not in name, 'invalid resource id')
                root = Path(value).absolute()
                require(root.is_dir() and not root.is_symlink() and root.resolve() == root, 'root must be an existing physical directory without symlinks')
                roots[key][name] = str(root)
        with self._lock():
            record = self._load(tool_id)
            require(record['state'] in ('AWAITING_APPROVAL', 'ACTIVE'), 'verify before approving', 'NEEDS_VERIFICATION')
            package = self._package(record); plan = self._verified(record, package)
            require(not package.contract['effects']['read'] or read_roots, 'read effects require a root')
            require(not package.contract['effects']['write'] or write_roots, 'write effects require a root')
            approval = {'subject': subject, 'host_id': host_id, 'expires_at': time.time() + ttl_s,
                        'package_digest': package.package_digest, 'plan_digest': digest(plan), **roots}
            record.update(state='ACTIVE', approval=approval); self._save(record)
        return {'tool_id': tool_id, 'state': 'ACTIVE', 'expires_at': approval['expires_at']}

    def revoke(self, tool_id: str) -> None:
        with self._lock():
            record = self._load(tool_id); record.update(state='REVOKED', approval=None); self._save(record)

    def _active(self, record: dict, subject: str, host_id: str):
        require(record['state'] == 'ACTIVE', 'tool is not approved', record['state'])
        package = self._package(record); plan = self._verified(record, package)
        approval = record.get('approval') or {}
        require(approval.get('subject') == subject and approval.get('host_id') == host_id
                and approval.get('expires_at', 0) > time.time(), 'approval does not authorize this call', 'NOT_AUTHORIZED')
        require(approval['package_digest'] == package.package_digest and approval['plan_digest'] == digest(plan), 'approval is outdated', 'STALE')
        return package, approval

    def list(self) -> list[dict]:
        result = []
        with self._lock():
            for path in sorted((self.root / 'records').glob('*.json')):
                try:
                    record = self._load(path.stem)
                    package = self._package(record)
                    if record['state'] == 'ACTIVE': self._active(record, record['approval']['subject'], record['approval']['host_id'])
                    result.append({'tool_id': package.tool_id, 'summary': package.contract['summary'],
                                   'package_digest': package.package_digest, 'state': record['state']})
                except ToolError as error:
                    result.append({'tool_id': path.stem, 'state': 'STALE', 'reason': error.code})
        return result

    def catalogue(self, subject: str, host_id: str) -> list[dict]:
        result = []
        with self._lock():
            for path in sorted((self.root / 'records').glob('*.json')):
                try:
                    record = self._load(path.stem); package, approval = self._active(record, subject, host_id)
                except ToolError: continue
                result.append({'tool_id': package.tool_id, 'summary': package.contract['summary'],
                               'input_schema': package.contract['input_schema'], 'output_schema': package.contract['output_schema'],
                               'effects': package.contract['effects'], 'package_digest': package.package_digest,
                               'read_resources': [f'hostfs://{name}' for name in approval['read_roots']],
                               'write_resources': [f'hostfs://{name}' for name in approval['write_roots']]})
        return result

    @contextlib.contextmanager
    def _directory(self, root: str, parts: list[str], *, create: bool = False):
        # Walk the approved absolute root too: O_NOFOLLOW on only its final
        # component would still follow an ancestor replaced after approval.
        fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            root_parts = Path(root).parts[1:]
            for index, part in enumerate([*root_parts, *parts]):
                relative_name(part)
                if create and index >= len(root_parts):
                    try: os.mkdir(part, mode=0o700, dir_fd=fd)
                    except FileExistsError: pass
                new = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd); fd = new
            yield fd
        finally: os.close(fd)

    def _resource(self, uri: str, roots: dict) -> tuple[str, list[str]]:
        require(isinstance(uri, str), 'logical resource required', 'OUT_OF_SCOPE')
        parsed = urlsplit(uri)
        require(parsed.scheme == 'hostfs' and parsed.netloc in roots and not parsed.query and not parsed.fragment, 'resource not granted', 'OUT_OF_SCOPE')
        name = parsed.path.lstrip('/')
        if name: relative_name(name)
        return roots[parsed.netloc], name.split('/') if name else []

    def run(self, tool_id: str, inputs: object, *, subject: str, host_id: str, files: dict | None = None, output: str | None = None) -> dict:
        try:
            return self._run(tool_id, inputs, subject=subject, host_id=host_id, files=files, output=output)
        except ToolError as error:
            receipt = {'contract': 'ToolReceipt/v1', 'receipt_id': 'tool_' + uuid.uuid4().hex,
                       'tool_id': tool_id, 'subject': subject, 'host_id': host_id,
                       'decision': 'DENY', 'status': 'FAILED', 'reason': error.code, 'wall': time.time()}
            receipt['seal'] = self._seal(receipt)
            with self._lock():
                with (self.root / 'receipts.jsonl').open('a') as stream: stream.write(canonical(receipt) + '\n')
            error.receipt = receipt
            raise

    def _run(self, tool_id: str, inputs: object, *, subject: str, host_id: str, files: dict | None = None, output: str | None = None) -> dict:
        files = files or {}
        with self._lock():
            record = self._load(tool_id); package, approval = self._active(record, subject, host_id)
        require(set(files) == set(package.contract['effects']['read']), 'file bindings differ from contract', 'OUT_OF_SCOPE')
        snapshots = {}
        try:
            total = 0
            for name, uri in files.items():
                root, parts = self._resource(uri, approval['read_roots'])
                require(parts, 'input must name a file', 'OUT_OF_SCOPE')
                with self._directory(root, parts[:-1]) as fd:
                    incoming = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
                    with os.fdopen(incoming, 'rb') as stream:
                        require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), 'input must be a regular file', 'OUT_OF_SCOPE')
                        data = stream.read(package.security['max_input_bytes'] + 1)
                        total += len(data)
                        require(total <= package.security['max_input_bytes'], 'input budget exceeded', 'LIMIT_EXCEEDED')
                        snapshots[name] = data
            destination = self._resource(output, approval['write_roots']) if package.contract['effects']['write'] else None
            result = self._provider(package).run(package, inputs, snapshots)
            with self._lock():
                current = self._load(tool_id); self._active(current, subject, host_id)
                require(current['approval'] == approval, 'approval changed during execution', 'STALE')
                if destination:
                    root, parts = destination
                    for name, data in result.artifacts.items():
                        path = name.split('/')
                        with self._directory(root, parts + path[:-1], create=True) as fd:
                            temp = '.tool-' + uuid.uuid4().hex
                            try:
                                out = os.open(temp, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600, dir_fd=fd)
                                with os.fdopen(out, 'wb') as stream: stream.write(data)
                                os.replace(temp, path[-1], src_dir_fd=fd, dst_dir_fd=fd)
                            finally:
                                try: os.unlink(temp, dir_fd=fd)
                                except FileNotFoundError: pass
                receipt = {'contract': 'ToolReceipt/v1', 'receipt_id': 'tool_' + uuid.uuid4().hex,
                           'tool_id': tool_id, 'package_digest': package.package_digest,
                           'plan_digest': record['verification']['plan_digest'], 'subject': subject, 'host_id': host_id,
                           'decision': 'ALLOW', 'status': 'DONE', 'wall': time.time(),
                           'input_digest': digest({'inputs': inputs, 'files': {n: hashlib.sha256(b).hexdigest() for n, b in snapshots.items()}}),
                           'result_digest': digest(result.result),
                           'artifacts': {n: hashlib.sha256(b).hexdigest() for n, b in result.artifacts.items()}}
                receipt['seal'] = self._seal(receipt)
                with (self.root / 'receipts.jsonl').open('a') as stream: stream.write(canonical(receipt) + '\n')
            return {'result': result.result, 'artifacts': list(result.artifacts), 'receipt': receipt}
        except OSError as error:
            raise ToolError('OUT_OF_SCOPE', 'resource unavailable or not a regular authorized path') from error

    def verify_receipt(self, receipt: dict) -> bool:
        payload = {k: v for k, v in receipt.items() if k != 'seal'}
        return hmac.compare_digest(str(receipt.get('seal', '')), self._seal(payload))
