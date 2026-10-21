import json
from pathlib import Path

import pytest

from isymotron import tool_contract as tc


def package_files(code="def run(inputs):\n    return {'count': len(inputs['text'])}\n"):
    return {
        'tool.json': json.dumps({
            'contract': 'ToolContract/v1', 'tool_id': 'text-count', 'version': '1',
            'summary': 'Count characters', 'entrypoint': 'main.py', 'provider': 'linux-python/v1',
            'input_schema': {'type': 'object', 'properties': {'text': {'type': 'string'}}, 'required': ['text'], 'additionalProperties': False},
            'output_schema': {'type': 'object', 'properties': {'count': {'type': 'integer'}}, 'required': ['count'], 'additionalProperties': False},
            'effects': {'read': [], 'write': []},
        }),
        'security.json': json.dumps({'contract': 'ToolSecurity/v1', 'network': False, 'external_processes': False,
                                    'timeout_s': 3, 'memory_mb': 256, 'max_input_bytes': 1048576, 'max_output_bytes': 65536}),
        'cases.json': json.dumps([{'name': 'three characters', 'inputs': {'text': 'abc'}, 'files': {}, 'expected': {'count': 3}}]),
        'main.py': code,
    }


def write_package(root: Path, files=None):
    root.mkdir(parents=True, exist_ok=True)
    for name, content in (files or package_files()).items():
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    return root


def test_package_digest_binds_code_policy_and_cases(tmp_path):
    p = write_package(tmp_path / 'p')
    before = tc.ToolPackage.load(p)
    for name in ['main.py', 'security.json', 'cases.json']:
        original = (p / name).read_text()
        (p / name).write_text(original + '\n')
        assert tc.ToolPackage.load(p).package_digest != before.package_digest
        (p / name).write_text(original)


@pytest.mark.parametrize('field,value', [('timeout_s', True), ('memory_mb', -1), ('network', True), ('invented_control', False)])
def test_unsupported_or_malformed_controls_are_rejected(tmp_path, field, value):
    files = package_files()
    security = json.loads(files['security.json']); security[field] = value
    files['security.json'] = json.dumps(security)
    with pytest.raises(tc.ToolError):
        tc.ToolPackage.load(write_package(tmp_path / 'p', files))


def test_path_escape_and_symlink_refused_before_code_runs(tmp_path):
    files = package_files()
    manifest = json.loads(files['tool.json']); manifest['entrypoint'] = '../outside.py'
    files['tool.json'] = json.dumps(manifest)
    with pytest.raises(tc.ToolError):
        tc.ToolPackage.load(write_package(tmp_path / 'p', files))
    p = write_package(tmp_path / 'q')
    (p / 'link').symlink_to('/etc/passwd')
    with pytest.raises(tc.ToolError):
        tc.ToolPackage.load(p)


def test_schema_refuses_extra_parameters_wrong_types_and_unknown_keywords(tmp_path):
    schema = json.loads(package_files()['tool.json'])['input_schema']
    tc.validate(schema, {'text': 'abc'})
    for value in [{'text': 7}, {'text': 'a', 'shell': 'sh'}, {}]:
        with pytest.raises(tc.ToolError): tc.validate(schema, value)
    files = package_files()
    manifest = json.loads(files['tool.json']); manifest['input_schema']['$ref'] = 'remote.json'
    files['tool.json'] = json.dumps(manifest)
    with pytest.raises(tc.ToolError): tc.ToolPackage.load(write_package(tmp_path / 'p', files))


def test_boolean_is_not_an_integer():
    with pytest.raises(tc.ToolError): tc.validate({'type': 'integer'}, True)


@pytest.mark.parametrize('mutation', ['non_string_effect', 'scalar_input', 'deep_metadata'])
def test_malformed_metadata_fails_with_a_contract_error(mutation):
    files = package_files()
    manifest = json.loads(files['tool.json'])
    if mutation == 'non_string_effect':
        manifest['effects']['read'] = [{}]
    elif mutation == 'scalar_input':
        manifest['input_schema'] = {'type': 'string'}
        cases = json.loads(files['cases.json']); cases[0]['inputs'] = 'abc'
        files['cases.json'] = json.dumps(cases)
    else:
        files['cases.json'] = '[' * 16000 + '0' + ']' * 16000
    files['tool.json'] = json.dumps(manifest)
    with pytest.raises(tc.ToolError):
        tc.ToolPackage.from_files(files)
