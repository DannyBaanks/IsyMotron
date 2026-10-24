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


def test_provider_failure_is_structured_and_leaves_no_package(tmp_path):
    from agents.provider import ProviderError
    class Unavailable:
        def complete(self, *args, **kwargs):
            raise ProviderError('provider unavailable')
    dest=tmp_path/'proposal'
    with pytest.raises(ToolError, match='PROPOSAL_FAILED'):
        ToolBuilder(Unavailable()).propose('Count characters',dest)
    assert not dest.exists()


def test_truncated_package_is_never_published(tmp_path):
    dest = tmp_path/'proposal'
    reply = '<TRUNCATED>' + json.dumps({'files': package_files()})
    with pytest.raises(ToolError, match='truncated'):
        ToolBuilder(ScriptedProvider([reply])).propose('Count characters', dest)
    assert not dest.exists()


def test_lightning_has_room_for_answer_and_receives_a_valid_example(tmp_path):
    class Capture(ScriptedProvider):
        def complete(self, messages, **options):
            self.options = dict(options)
            # The scripted response doesn't send model-specific generation controls.
            options.pop('enable_thinking', None)
            return super().complete(messages, **options)
    provider = Capture([json.dumps({'files': package_files()})])
    provider.name = 'nvidia'
    provider.model = 'nvidia/nemotron-3.5-lightning-30b-a3b'
    ToolBuilder(provider).propose('Count characters', tmp_path/'proposal')
    assert provider.options['max_tokens'] == 8192
    assert provider.options['json_object'] is True
    assert provider.options['enable_thinking'] is False
    assert 'reasoning_budget' not in provider.options
    messages = provider.calls[0]
    example = ToolBuilder(ScriptedProvider([messages[2]['content']])).propose('Count characters', tmp_path/'example')
    assert example.tool_id == 'text-length'


def structured_files():
    files = package_files()
    for name in ('tool.json', 'security.json', 'cases.json'):
        files[name] = json.loads(files[name])
    return files


def test_structured_metadata_is_serialized_by_host_without_changing_source(tmp_path):
    files = structured_files()
    files['cases.json'][0]['inputs']['text'] = 'a"b\nc'
    files['cases.json'][0]['expected']['count'] = 5
    dest = tmp_path/'proposal'
    ToolBuilder(ScriptedProvider([json.dumps({'files': files})])).propose('Count characters', dest)
    saved = ToolPackage.load(dest)
    assert saved.cases[0]['inputs']['text'] == 'a"b\nc'
    assert saved.files['main.py'].decode() == files['main.py']
    assert json.loads((dest/'security.json').read_text())['network'] is False


def test_structured_metadata_cannot_bypass_contract_validation(tmp_path):
    files = structured_files()
    files['security.json']['network'] = True
    dest = tmp_path/'proposal'
    with pytest.raises(ToolError, match='unsupported security control'):
        ToolBuilder(ScriptedProvider([json.dumps({'files': files})])).propose('Build a tool', dest)
    assert not dest.exists()


@pytest.mark.parametrize('name,value', [('main.py', {}), ('tool.json', []), ('cases.json', {})])
def test_only_metadata_files_accept_their_declared_json_types(tmp_path, name, value):
    files = structured_files()
    files[name] = value
    dest = tmp_path/'proposal'
    with pytest.raises(ToolError):
        ToolBuilder(ScriptedProvider([json.dumps({'files': files})])).propose('Build a tool', dest)
    assert not dest.exists()


def test_invalid_json_reports_location_without_echoing_model_content(tmp_path):
    with pytest.raises(ToolError) as caught:
        ToolBuilder(ScriptedProvider(['{"PRIVATE_MODEL_TEXT": }'])).propose('Build', tmp_path/'proposal')
    assert caught.value.code == 'INVALID_PROPOSAL'
    assert 'line 1' in caught.value.detail
    assert 'PRIVATE_MODEL_TEXT' not in caught.value.detail
