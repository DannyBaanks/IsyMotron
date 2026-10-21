import json
import sys
from pathlib import Path

import pytest

from isymotron.tool_contract import ToolPackage
from isymotron.tool_provider import LinuxPythonProvider

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(not sys.platform.startswith('linux'), reason='real Linux worker')


def test_developer_json_prettifier_publishes_only_its_declared_artifact():
    package = ToolPackage.load(ROOT/'examples/tools/json-prettifier')
    provider = LinuxPythonProvider()
    assert provider.verify(package)['verdict'] == 'PASS_FOR_SCOPE'
    result = provider.run(package, {}, {'data.json': b'{"z":1,"a":{"n":2}}'})
    assert result.result == {'keys': 2}
    assert set(result.artifacts) == {'pretty.json'}
    assert json.loads(result.artifacts['pretty.json']) == {'z': 1, 'a': {'n': 2}}
    assert result.artifacts['pretty.json'].startswith(b'{\n  "a":')
