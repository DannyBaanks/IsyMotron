import json
import subprocess
import sys
from pathlib import Path

import pytest

from test_tool_contract import write_package

ROOT=Path(__file__).resolve().parents[1]


@pytest.mark.skipif(not sys.platform.startswith('linux'),reason='real Linux worker')
def test_cli_initial_approval_execution_and_revoke(tmp_path):
    package=write_package(tmp_path/'package')
    prefix=[sys.executable,str(ROOT/'tools/isymotron_cli.py'),'tool','--registry',str(tmp_path/'registry')]
    def call(*args,code=0):
        result=subprocess.run([*prefix,*args],capture_output=True,text=True)
        assert result.returncode==code,result.stdout+result.stderr
        return json.loads(result.stdout)
    assert call('stage',str(package))['state']=='DRAFT'
    call('verify','text-count')
    call('run','text-count','--inputs','{"text":"abc"}',code=2)
    call('approve','text-count','--yes')
    assert call('run','text-count','--inputs','{"text":"abcd"}')['result']=={'count':4}
    call('revoke','text-count')
    assert call('list')[0]['state']=='REVOKED'
