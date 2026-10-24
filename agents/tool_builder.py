"""Nemotron proposes code and its contract; this role never approves or runs it."""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from isymotron.tool_contract import ToolError, ToolPackage, require
from .provider import ProviderError

SYSTEM = """You build a tool package for IsyMotron, not an execution request.
Return exactly one JSON object: {"files":{"tool.json":{...},"security.json":{...},"cases.json":[...],"main.py":"Python source"}}.
No Markdown. No approval, verification report or executable installer.
The Python entrypoint defines run(inputs) and returns one JSON value. Use only Python standard library. Never print.
tool.json and security.json must be JSON objects and cases.json a JSON array, not JSON embedded in strings. The host serializes these three metadata files. Python source files are strings; escape their newlines as JSON \\n. Use JSON syntax, not Python dict syntax.
tool.json fields: contract='ToolContract/v1', tool_id (lowercase kebab-case), version, summary, entrypoint='main.py', provider='linux-python/v1', input_schema, output_schema, effects={read:[relative input names],write:[relative artifact names]}.
Schemas support type, enum; object properties/required/additionalProperties=false; array items/maxItems; string minLength/maxLength; numeric minimum/maximum. Every object schema needs properties (use {} for an empty object) and additionalProperties=false. Inputs must be an object. No other keywords.
security.json fields: contract='ToolSecurity/v1', network=false, external_processes=false, timeout_s=3, memory_mb=256, max_input_bytes=1048576, max_output_bytes=65536.
cases.json is a nonempty array of {name,inputs,files,expected}. files maps every declared read name to fixture text. Expected must match the output schema.
Read declared inputs from /inputs/<name>. Write only declared artifacts in the current directory. These files are precreated; directories are readonly. No scratch files, atomic rename, unlink or tempfile usage. Filesystem roots, network, processes, credentials and host permissions are unavailable. The host compiles controls and checks tests independently. A request outside this provider must be refused rather than disguised as code."""

EXAMPLE_FILES = {
    'tool.json': json.dumps({
        'contract': 'ToolContract/v1', 'tool_id': 'text-length', 'version': '1',
        'summary': 'Count characters', 'entrypoint': 'main.py', 'provider': 'linux-python/v1',
        'input_schema': {'type': 'object', 'properties': {'text': {'type': 'string'}},
                         'required': ['text'], 'additionalProperties': False},
        'output_schema': {'type': 'integer'}, 'effects': {'read': [], 'write': []},
    }),
    'security.json': json.dumps({
        'contract': 'ToolSecurity/v1', 'network': False, 'external_processes': False,
        'timeout_s': 3, 'memory_mb': 256, 'max_input_bytes': 1048576, 'max_output_bytes': 65536,
    }),
    'cases.json': json.dumps([{'name': 'three letters', 'inputs': {'text': 'abc'},
                               'files': {}, 'expected': 3}]),
    'main.py': 'def run(inputs):\n    return len(inputs["text"])\n',
}


class ToolBuilder:
    def __init__(self, provider): self.provider = provider

    def propose(self, intent: str, destination: str | Path) -> ToolPackage:
        require(isinstance(intent, str) and 0 < len(intent) <= 12000, 'invalid tool request')
        destination = Path(destination)
        require(not destination.exists(), 'proposal destination already exists')
        options = {'max_tokens': 8192, 'temperature': .2, 'json_object': True}
        # Lightning can exhaust the response budget while reasoning. Request
        # a direct answer for package generation; other models and providers
        # retain their existing request protocol.
        if (getattr(self.provider, 'name', None) == 'nvidia'
                and getattr(self.provider, 'model', None) == 'nvidia/nemotron-3.5-lightning-30b-a3b'):
            options['enable_thinking'] = False
        try:
            completion = self.provider.complete([
                {'role': 'system', 'content': SYSTEM},
                {'role': 'user', 'content': 'Build text-length: count characters in inputs.text.'},
                {'role': 'assistant', 'content': json.dumps({'files': {
                    name: json.loads(value) if name in ('tool.json', 'security.json', 'cases.json') else value
                    for name, value in EXAMPLE_FILES.items()
                }})},
                {'role': 'user', 'content': intent},
            ], **options)
        except ProviderError as error:
            raise ToolError('PROPOSAL_FAILED', 'model completion failed; retry after checking provider availability') from error
        require(not completion.truncated, 'model response was truncated', 'INVALID_PROPOSAL')
        try:
            require(len(completion.text.encode()) <= 2097152, 'proposal too large', 'INVALID_PROPOSAL')
            data = json.loads(completion.text)
            require(isinstance(data, dict) and set(data) == {'files'} and isinstance(data['files'], dict),
                    'expected only package files', 'INVALID_PROPOSAL')
            files = {}
            for name, value in data['files'].items():
                if isinstance(value, str):
                    files[name] = value  # Existing string-only proposals remain supported.
                elif ((name in ('tool.json', 'security.json') and isinstance(value, dict))
                      or (name == 'cases.json' and isinstance(value, list))):
                    files[name] = json.dumps(value, allow_nan=False)
                else:
                    raise ToolError('INVALID_PROPOSAL', 'source files must be strings; metadata must have its declared JSON type')
            package = ToolPackage.from_files(files)
        except json.JSONDecodeError as exc:
            raise ToolError('INVALID_PROPOSAL', f'model response is not JSON at line {exc.lineno}, column {exc.colno}') from exc
        except ToolError as exc:
            raise ToolError('INVALID_PROPOSAL', f'model package failed validation: {exc.detail}') from exc
        except (ValueError, TypeError, RecursionError) as exc:
            raise ToolError('INVALID_PROPOSAL', 'model did not produce a supported package') from exc
        destination.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(dir=destination.parent, prefix='.tool-proposal-'))
        try:
            package.write(staging)
            staging.rename(destination)
        finally:
            if staging.exists(): shutil.rmtree(staging)
        return package
