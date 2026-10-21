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
            # The scripted response doesn't need a real model's reasoning budget.
            options.pop('reasoning_budget', None)
            return super().complete(messages, **options)
    provider = Capture([json.dumps({'files': package_files()})])
    provider.name = 'nvidia'
    provider.model = 'nvidia/nemotron-3.5-lightning-30b-a3b'
    ToolBuilder(provider).propose('Count characters', tmp_path/'proposal')
    assert provider.options['max_tokens'] == 8192
    assert provider.options['json_object'] is True
    assert provider.options['reasoning_budget'] == 1024
    messages = provider.calls[0]
    example = ToolPackage.from_files(json.loads(messages[2]['content'])['files'])
    assert example.tool_id == 'text-length'
