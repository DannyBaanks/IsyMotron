"""Code-bearing tools: strict data contracts, never permissions from a model."""
from __future__ import annotations

import json
import math
import re
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Mapping

from .canon import digest


class ToolError(ValueError):
    def __init__(self, code: str, detail: str = ''):
        self.code, self.detail = code, detail
        super().__init__(f'{code}: {detail}' if detail else code)


def require(condition: Any, detail: str, code: str = 'INVALID_CONTRACT') -> None:
    if not condition:
        raise ToolError(code, detail)


def relative_name(value: Any) -> str:
    require(isinstance(value, str) and 0 < len(value) <= 160, 'invalid package/resource name')
    p = PurePosixPath(value)
    require(not p.is_absolute() and all(x not in ('', '.', '..') for x in value.split('/'))
            and '\\' not in value and ':' not in value and '\x00' not in value,
            'resource must be a relative path without traversal')
    return value


def _keys(data: Any, keys: set[str], label: str) -> None:
    require(isinstance(data, dict) and set(data) == keys, f'{label} fields must be {sorted(keys)}')


def check_schema(schema: Any, depth: int = 0) -> None:
    require(isinstance(schema, dict) and depth <= 8, 'invalid or deeply nested schema')
    kind = schema.get('type')
    allowed = {'type', 'enum'}
    if kind == 'object': allowed |= {'properties', 'required', 'additionalProperties'}
    elif kind == 'array': allowed |= {'items', 'maxItems'}
    elif kind == 'string': allowed |= {'minLength', 'maxLength'}
    elif kind in ('integer', 'number'): allowed |= {'minimum', 'maximum'}
    require(kind in ('object', 'array', 'string', 'integer', 'number', 'boolean', 'null')
            and set(schema) <= allowed, 'unsupported schema type or keyword')
    if kind == 'object':
        props, needed = schema.get('properties'), schema.get('required', [])
        require(isinstance(props, dict) and len(props) <= 64 and schema.get('additionalProperties') is False,
                'objects need properties and additionalProperties=false')
        require(isinstance(needed, list) and all(isinstance(k, str) and k in props for k in needed), 'invalid required fields')
        for value in props.values(): check_schema(value, depth + 1)
    if kind == 'array': check_schema(schema.get('items'), depth + 1)
    for key in ('minLength', 'maxLength', 'maxItems'):
        if key in schema: require(type(schema[key]) is int and 0 <= schema[key] <= 32768, 'invalid schema bound')
    for key in ('minimum', 'maximum'):
        if key in schema: require(type(schema[key]) in (int, float) and math.isfinite(schema[key]), 'invalid numeric bound')
    if 'enum' in schema:
        require(isinstance(schema['enum'], list) and 0 < len(schema['enum']) <= 64, 'invalid enum')
        for value in schema['enum']: validate({k: v for k, v in schema.items() if k != 'enum'}, value)


def validate(schema: Mapping[str, Any], value: Any) -> None:
    kind = schema['type']
    types = {'object': dict, 'array': list, 'string': str, 'integer': int, 'boolean': bool, 'null': type(None)}
    ok = type(value) in (int, float) and math.isfinite(value) if kind == 'number' else type(value) is types.get(kind)
    require(ok, f'expected {kind}', 'SCHEMA_MISMATCH')
    if 'enum' in schema: require(any(type(value) is type(x) and value == x for x in schema['enum']), 'value outside enum', 'SCHEMA_MISMATCH')
    if kind == 'object':
        props = schema['properties']
        require(set(value) <= set(props) and set(schema.get('required', [])) <= set(value), 'unknown or missing input fields', 'SCHEMA_MISMATCH')
        for key, item in value.items(): validate(props[key], item)
    elif kind == 'array':
        require(len(value) <= schema.get('maxItems', 1024), 'too many items', 'SCHEMA_MISMATCH')
        for item in value: validate(schema['items'], item)
    elif kind == 'string':
        require(schema.get('minLength', 0) <= len(value) <= schema.get('maxLength', 32768), 'string length', 'SCHEMA_MISMATCH')
    elif kind in ('integer', 'number'):
        require(schema.get('minimum', -math.inf) <= value <= schema.get('maximum', math.inf), 'numeric bound', 'SCHEMA_MISMATCH')


@dataclass(frozen=True)
class ToolPackage:
    files: Mapping[str, bytes]
    package_digest: str

    @property
    def contract(self) -> dict: return json.loads(self.files['tool.json'])
    @property
    def security(self) -> dict: return json.loads(self.files['security.json'])
    @property
    def cases(self) -> list[dict]: return json.loads(self.files['cases.json'])
    @property
    def tool_id(self) -> str: return self.contract['tool_id']

    @classmethod
    def load(cls, path: str | Path) -> 'ToolPackage':
        root = Path(path)
        require(root.is_dir() and not root.is_symlink(), 'package must be a directory')
        files = {}
        for p in sorted(root.rglob('*')):
            require(not p.is_symlink(), 'symlinks are not package files')
            if p.is_dir(): continue
            require(stat.S_ISREG(p.stat().st_mode) and p.stat().st_nlink == 1, 'only regular unlinked files')
            require(p.stat().st_size <= 524288, 'package file too large')
            files[relative_name(p.relative_to(root).as_posix())] = p.read_bytes()
            require(len(files) <= 64 and sum(map(len, files.values())) <= 2097152, 'package too large')
        return cls.from_files(files)

    @classmethod
    def from_files(cls, files: Mapping[str, str | bytes]) -> 'ToolPackage':
        copied = {relative_name(k): v.encode() if isinstance(v, str) else bytes(v) for k, v in files.items()}
        require({'tool.json', 'security.json', 'cases.json'} <= copied.keys(), 'missing package files')
        require(len(copied) <= 64 and sum(map(len, copied.values())) <= 2097152
                and all(len(v) <= 524288 for v in copied.values()), 'package too large')
        try:
            contract, security, cases = (json.loads(copied[n]) for n in ('tool.json', 'security.json', 'cases.json'))
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise ToolError('INVALID_CONTRACT', 'package metadata must be JSON') from exc
        _keys(contract, {'contract', 'tool_id', 'version', 'summary', 'entrypoint', 'provider', 'input_schema', 'output_schema', 'effects'}, 'tool')
        require(contract['contract'] == 'ToolContract/v1', 'unsupported contract')
        require(isinstance(contract['tool_id'], str) and re.fullmatch(r'[a-z][a-z0-9-]{1,63}', contract['tool_id']), 'invalid tool_id')
        require(all(isinstance(contract[k], str) and 0 < len(contract[k]) <= 256 for k in ('version', 'summary', 'provider')), 'invalid identity')
        require(relative_name(contract['entrypoint']) in copied and contract['entrypoint'].endswith('.py'), 'missing Python entrypoint')
        check_schema(contract['input_schema']); check_schema(contract['output_schema'])
        require(contract['input_schema']['type'] == 'object', 'tool inputs must be an object')
        _keys(contract['effects'], {'read', 'write'}, 'effects')
        for names in contract['effects'].values():
            require(isinstance(names, list) and len(names) <= 32 and all(isinstance(n, str) for n in names)
                    and len(names) == len(set(names)), 'invalid effects')
            for name in names: relative_name(name)
        _keys(security, {'contract', 'network', 'external_processes', 'timeout_s', 'memory_mb', 'max_input_bytes', 'max_output_bytes'}, 'security')
        require(security['contract'] == 'ToolSecurity/v1' and security['network'] is False and security['external_processes'] is False, 'unsupported security control')
        for key, lo, hi in [('timeout_s', 1, 30), ('memory_mb', 32, 1024), ('max_input_bytes', 1, 16777216), ('max_output_bytes', 1, 1048576)]:
            require(type(security[key]) is int and lo <= security[key] <= hi, f'invalid {key}')
        require(isinstance(cases, list) and 0 < len(cases) <= 16, 'need 1..16 contributed cases')
        for case in cases:
            _keys(case, {'name', 'inputs', 'files', 'expected'}, 'case')
            require(isinstance(case['name'], str) and isinstance(case['files'], dict), 'invalid case')
            require(set(case['files']) == set(contract['effects']['read']) and all(isinstance(v, str) for v in case['files'].values()), 'case files must match reads')
            validate(contract['input_schema'], case['inputs']); validate(contract['output_schema'], case['expected'])
        return cls(MappingProxyType(copied), digest({k: v.hex() for k, v in sorted(copied.items())}))

    def write(self, root: Path) -> None:
        root.mkdir(parents=True, exist_ok=True)
        for name, data in self.files.items():
            dest = root / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
