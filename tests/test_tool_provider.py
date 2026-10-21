import json
import sys

import pytest

from isymotron.tool_contract import ToolError, ToolPackage
from isymotron.tool_provider import LinuxPythonProvider
from test_tool_contract import package_files

pytestmark = pytest.mark.skipif(not sys.platform.startswith('linux'), reason='Linux provider only')


def tool(code):
    return ToolPackage.from_files(package_files(code))


def test_runs_real_custom_code_and_verifies_cases():
    p = LinuxPythonProvider()
    result = p.run(tool("def run(inputs):\n return {'count': len(inputs['text'])}\n"), {'text': 'abcd'}, {})
    assert result.result == {'count': 4}
    report = p.verify(tool("def run(inputs):\n return {'count': len(inputs['text'])}\n"))
    assert report['verdict'] == 'PASS_FOR_SCOPE'
    assert report['checks']['host_boundary'] is True


@pytest.mark.parametrize('body', [
    "return {'count': 1, 'secret': 'bad'}",
    "import socket; socket.socket(); return {'count': 3}",
    "import subprocess; subprocess.run(['/usr/bin/true']); return {'count': 3}",
    "open('/outside.txt','w').write('escape'); return {'count': 3}",
    "while True: pass",
    "print('x'*1000000); return {'count': 3}",
    "open('undeclared.txt','w').write('bad'); return {'count': 3}",
])
def test_code_exceeding_contract_is_not_verified(body):
    with pytest.raises(ToolError):
        LinuxPythonProvider().verify(tool('def run(inputs):\n ' + body + '\n'))


def test_outside_host_read_is_unavailable(tmp_path):
    secret = tmp_path / 'private-canary.txt'; secret.write_text('not-for-the-worker')
    p = tool(f"def run(inputs):\n return {{'count':len(open({str(secret)!r}).read())}}\n")
    with pytest.raises(ToolError): LinuxPythonProvider().run(p, {'text': 'abc'}, {})


def test_declared_artifact_is_returned_but_symlink_is_not():
    files = package_files("def run(inputs):\n open('report.txt','w').write(inputs['text'])\n return {'count':len(inputs['text'])}\n")
    manifest = json.loads(files['tool.json']); manifest['effects']['write'] = ['report.txt']; files['tool.json'] = json.dumps(manifest)
    result = LinuxPythonProvider().run(ToolPackage.from_files(files), {'text': 'abc'}, {})
    assert result.artifacts == {'report.txt': b'abc'}
    files['main.py'] = "def run(inputs):\n import os\n os.symlink('/etc/passwd','report.txt')\n return {'count':3}\n"
    with pytest.raises(ToolError): LinuxPythonProvider().run(ToolPackage.from_files(files), {'text': 'abc'}, {})


def test_missing_provider_never_falls_back_to_plain_python():
    with pytest.raises(ToolError, match='PROVIDER_UNAVAILABLE'):
        LinuxPythonProvider(binary='/missing/bwrap').run(tool("raise RuntimeError('must not execute')"), {'text': 'abc'}, {})
