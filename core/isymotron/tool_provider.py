"""Replaceable execution provider: bounded code, host-owned plans and observations."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .canon import digest
from .tool_contract import ToolError, ToolPackage, require, validate


@dataclass(frozen=True)
class ToolResult:
    result: object
    artifacts: dict[str, bytes]


class LinuxPythonProvider:
    provider_id = 'linux-python/v1'
    verifier_version = 'ToolVerifier/v1'

    def __init__(self, binary: str | None = None):
        self.binary = binary or shutil.which('bwrap') or ''

    def identity(self) -> dict:
        require(sys.platform.startswith('linux') and self.binary and Path(self.binary).is_file()
                and Path('/usr/bin/python3').is_file(), 'Linux, bubblewrap and system Python are required', 'PROVIDER_UNAVAILABLE')
        return {'id': self.provider_id, 'verifier': self.verifier_version,
                'implementation': digest([Path(__file__).read_text(), Path(__file__).with_name('tool_worker.py').read_text()]),
                'bwrap': hashlib.sha256(Path(self.binary).read_bytes()).hexdigest(),
                'kernel': platform.release(), 'machine': platform.machine()}

    def compile(self, package: ToolPackage) -> dict:
        require(package.contract['provider'] == self.provider_id, 'unsupported provider', 'PROVIDER_UNAVAILABLE')
        return {'contract': 'SecurityPlan/v1', 'provider': self.identity(), 'package_digest': package.package_digest,
                'controls': package.security, 'effects': package.contract['effects'],
                'mounts': {'runtime': 'readonly', 'tool': 'readonly', 'inputs': 'readonly', 'work': 'staging'},
                'network': 'isolated+seccomp', 'processes': 'seccomp', 'environment': 'empty'}

    def run(self, package: ToolPackage, inputs: object, files: dict[str, bytes]) -> ToolResult:
        self.compile(package)
        validate(package.contract['input_schema'], inputs)
        effects, policy = package.contract['effects'], package.security
        require(set(files) == set(effects['read']) and all(type(v) is bytes for v in files.values()), 'input files differ from contract', 'SCHEMA_MISMATCH')
        request = json.dumps({'entrypoint': package.contract['entrypoint'], 'inputs': inputs, 'security': policy}, allow_nan=False).encode()
        require(len(request) + sum(map(len, files.values())) <= policy['max_input_bytes'], 'input budget exceeded', 'LIMIT_EXCEEDED')
        with tempfile.TemporaryDirectory(prefix='isymotron-tool-') as temp:
            root = Path(temp)
            source, incoming, work = (root / n for n in ('tool', 'inputs', 'work'))
            package.write(source); incoming.mkdir(); work.mkdir()
            for name, data in files.items():
                p = incoming / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(data)
            bootstrap = root / 'worker.py'
            bootstrap.write_bytes(Path(__file__).with_name('tool_worker.py').read_bytes())
            command = [self.binary, '--unshare-all', '--die-with-parent', '--new-session', '--cap-drop', 'ALL',
                       '--clearenv', '--ro-bind', '/usr', '/usr']
            for path in ('/lib', '/lib64'):
                if Path(path).exists(): command += ['--ro-bind', path, path]
            command += ['--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp',
                        '--ro-bind', str(source), '/tool', '--ro-bind', str(incoming), '/inputs',
                        '--bind', str(work), '/work', '--ro-bind', str(bootstrap), '/worker.py',
                        '--chdir', '/work', '--remount-ro', '/', '--', '/usr/bin/python3', '-I', '-S', '-B', '/worker.py']
            with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
                proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr,
                                        start_new_session=True, env={'PATH': '/usr/bin:/bin'})
                try:
                    proc.communicate(request, timeout=policy['timeout_s'] + 2)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL); proc.wait()
                    raise ToolError('LIMIT_EXCEEDED', 'tool timed out') from None
                stdout.seek(0); output = stdout.read(policy['max_output_bytes'] + 1)
                require(proc.returncode == 0, f'worker stopped ({proc.returncode})', 'EXECUTION_FAILED')
                require(len(output) <= policy['max_output_bytes'], 'output budget exceeded', 'LIMIT_EXCEEDED')
            try: result = json.loads(output)
            except (ValueError, UnicodeError) as exc: raise ToolError('INVALID_OUTPUT', 'worker must return one JSON result') from exc
            validate(package.contract['output_schema'], result)
            artifacts = {}
            total = len(output)
            for path in work.rglob('*'):
                require(not path.is_symlink(), 'artifact symlink', 'INVALID_OUTPUT')
                if path.is_dir(): continue
                name = path.relative_to(work).as_posix()
                require(name in effects['write'] and stat.S_ISREG(path.stat().st_mode) and path.stat().st_nlink == 1,
                        'undeclared or non-regular artifact', 'INVALID_OUTPUT')
                total += path.stat().st_size
                require(total <= policy['max_output_bytes'], 'artifact budget exceeded', 'LIMIT_EXCEEDED')
                artifacts[name] = path.read_bytes()
            require(set(artifacts) == set(effects['write']), 'missing artifact', 'INVALID_OUTPUT')
            return ToolResult(result, artifacts)

    def verify(self, package: ToolPackage) -> dict:
        plan = self.compile(package)
        # Host probes do not trust a guest saying "tests passed". Each probe
        # is host-owned code, actually executed through this same provider.
        self._boundary_probes(package)
        cases = []
        for case in package.cases:
            result = self.run(package, case['inputs'], {k: v.encode() for k, v in case['files'].items()})
            require(result.result == case['expected'], 'contributed case mismatch', 'VERIFICATION_FAILED')
            cases.append({'name': case['name'], 'passed': True})
        report = {'contract': 'ToolVerification/v1', 'verdict': 'PASS_FOR_SCOPE',
                  'package_digest': package.package_digest, 'plan_digest': digest(plan),
                  'provider': plan['provider'], 'checks': {'host_boundary': True, 'cases': cases}}
        return {**report, 'seal': digest(report)}

    def _boundary_probes(self, package: ToolPackage) -> None:
        schema = {'type': 'object', 'properties': {}, 'required': [], 'additionalProperties': False}
        for operation in ["open('/outside-control-probe','w').write('x')",
                          "import socket; socket.socket()", "import os; os.fork()"]:
            files = dict(package.files)
            contract = package.contract
            contract.update(entrypoint='probe.py', input_schema=schema, output_schema=schema, effects={'read': [], 'write': []})
            files['tool.json'] = json.dumps(contract).encode()
            files['cases.json'] = json.dumps([{'name': 'host probe', 'inputs': {}, 'files': {}, 'expected': {}}]).encode()
            files['probe.py'] = ('def run(inputs):\n ' + operation + '\n return {}\n').encode()
            try: self.run(ToolPackage.from_files(files), {}, {})
            except ToolError as error:
                require(error.code == 'EXECUTION_FAILED', 'provider controls unavailable', 'PROVIDER_UNAVAILABLE')
            else: raise ToolError('VERIFICATION_FAILED', 'host boundary probe was not blocked')
