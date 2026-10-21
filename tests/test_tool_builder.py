import json

import pytest

from agents.provider import ScriptedProvider
from agents.tool_builder import ToolBuilder
from isymotron.tool_contract import ToolError, ToolPackage
from test_tool_contract import package_files


def test_model_constructs_only_an_inert_validated_package(tmp_path):
    provider = ScriptedProvider([json.dumps({'files': package_files()})])
    dest = tmp_path/'proposal'
    package = ToolBuilder(provider).propose('Count characters', dest)
    assert ToolPackage.load(dest).package_digest == package.package_digest
    assert not (tmp_path/'registry').exists()


@pytest.mark.parametrize('reply', ['not JSON', '{"files":{"../escape":"code"}}', '{"files":{},"approved":true}'])
def test_bad_model_response_does_not_publish_partial_package(tmp_path, reply):
    dest=tmp_path/'proposal'
    with pytest.raises(ToolError): ToolBuilder(ScriptedProvider([reply])).propose('Build a tool', dest)
    assert not dest.exists()
