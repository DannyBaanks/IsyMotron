"""Nemotron proposes code and its contract; this role never approves or runs it."""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from isymotron.tool_contract import ToolError, ToolPackage, require

SYSTEM = """You build a tool package for IsyMotron, not an execution request.
Return exactly one JSON object: {"files":{"tool.json":"JSON string","security.json":"JSON string","cases.json":"JSON string","main.py":"Python source"}}.
No Markdown. No approval, verification report or executable installer.
The Python entrypoint defines run(inputs) and returns one JSON value. Use only Python standard library. Never print.
tool.json fields: contract='ToolContract/v1', tool_id (lowercase kebab-case), version, summary, entrypoint='main.py', provider='linux-python/v1', input_schema, output_schema, effects={read:[relative input names],write:[relative artifact names]}.
Schemas support type, enum; object properties/required/additionalProperties=false; array items/maxItems; string minLength/maxLength; numeric minimum/maximum. Inputs must be an object. No other keywords.
security.json fields: contract='ToolSecurity/v1', network=false, external_processes=false, timeout_s=3, memory_mb=256, max_input_bytes=1048576, max_output_bytes=65536.
cases.json is a nonempty array of {name,inputs,files,expected}. files maps every declared read name to fixture text. Expected must match the output schema.
Read declared inputs from /inputs/<name>. Write only declared artifacts in the current directory. Filesystem roots, network, processes, credentials and host permissions are unavailable. The host compiles controls and checks tests independently. A request outside this provider must be refused rather than disguised as code."""


class ToolBuilder:
    def __init__(self, provider): self.provider = provider

    def propose(self, intent: str, destination: str | Path) -> ToolPackage:
        require(isinstance(intent, str) and 0 < len(intent) <= 12000, 'invalid tool request')
        destination = Path(destination)
        require(not destination.exists(), 'proposal destination already exists')
        completion = self.provider.complete([{'role':'system','content':SYSTEM}, {'role':'user','content':intent}], max_tokens=8192, temperature=.2)
        require(not completion.truncated, 'model response was truncated', 'INVALID_PROPOSAL')
        try:
            require(len(completion.text.encode()) <= 2097152, 'proposal too large', 'INVALID_PROPOSAL')
            data = json.loads(completion.text)
            require(isinstance(data, dict) and set(data) == {'files'} and isinstance(data['files'], dict)
                    and all(isinstance(v, str) for v in data['files'].values()), 'expected only package files', 'INVALID_PROPOSAL')
            package = ToolPackage.from_files(data['files'])
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
