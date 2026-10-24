import json
import sys

import pytest

from isymotron.tool_contract import ToolError, ToolPackage
from isymotron.tool_provider import LinuxPythonProvider
from test_tool_contract import package_files
from tool_support import bwrap_works

pytestmark = pytest.mark.skipif(
    not sys.platform.startswith('linux') or not bwrap_works(),
    reason='Linux provider with bubblewrap user namespaces',
)


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


def test_guest_sees_only_runtime_not_all_host_commands_or_environment(monkeypatch):
    monkeypatch.setenv('TOOL_HOST_SECRET','never-inherit-this')
    p=tool("def run(inputs):\n import os\n return {'count':int(os.path.exists('/usr/bin/cat'))+int('TOOL_HOST_SECRET' in os.environ)}\n")
    assert LinuxPythonProvider().run(p,{'text':'a'},{}).result=={'count':0}


def test_deep_guest_json_is_a_controlled_invalid_output():
    p = tool("def run(inputs):\n import os\n print('['*16000+'0'+']'*16000, flush=True)\n os._exit(0)\n")
    with pytest.raises(ToolError, match='INVALID_OUTPUT'):
        LinuxPythonProvider().run(p, {'text': 'abc'}, {})


def test_guest_cannot_allocate_undeclared_files_or_directories():
    code = '''def run(inputs):
 import os
 successful = 0
 for base in ('/work', '/tmp', '/dev'):
  for index in range(128):
   try:
    with open(base+'/extra-'+str(index), 'w') as stream: stream.write('x'*60000)
    successful += 1
   except OSError: pass
  try:
   os.mkdir(base+'/extra-dir')
   successful += 1
  except OSError: pass
 open('report.txt','w').write('abc')
 return {'count': successful}
'''
    files=package_files(code)
    manifest=json.loads(files['tool.json']);manifest['effects']['write']=['report.txt'];files['tool.json']=json.dumps(manifest)
    result=LinuxPythonProvider().run(ToolPackage.from_files(files),{'text':'abc'},{})
    assert result.result == {'count':0}
    assert result.artifacts == {'report.txt':b'abc'}


def test_preallocation_cannot_exceed_live_artifact_budget():
    code = '''def run(inputs):
 import ctypes
 with open('report.txt','w') as stream:
  stream.write('abc'); stream.flush()
  libc=ctypes.CDLL(None)
  libc.fallocate(stream.fileno(), 1, 0, 8*1024*1024)
 return {'count':3}
'''
    files=package_files(code)
    manifest=json.loads(files['tool.json']);manifest['effects']['write']=['report.txt'];files['tool.json']=json.dumps(manifest)
    with pytest.raises(ToolError):
        LinuxPythonProvider().run(ToolPackage.from_files(files),{'text':'abc'},{})
