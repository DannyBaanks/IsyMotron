import json
import sys
import time

import pytest

from isymotron.tool_contract import ToolError
from isymotron.tool_registry import ToolRegistry
from test_tool_contract import package_files, write_package

pytestmark = pytest.mark.skipif(not sys.platform.startswith('linux'), reason='real Linux worker')


def staged(tmp_path):
    registry = ToolRegistry(tmp_path / 'registry')
    registry.stage(write_package(tmp_path / 'package'))
    return registry


def approved(tmp_path):
    registry = staged(tmp_path)
    registry.verify('text-count')
    registry.approve('text-count', subject='alice', host_id='pc', read_roots={}, write_roots={})
    return registry


def test_initial_approval_is_required_and_can_be_reused(tmp_path):
    registry = staged(tmp_path)
    with pytest.raises(ToolError): registry.run('text-count', {'text': 'a'}, subject='alice', host_id='pc')
    registry.verify('text-count')
    assert registry.list()[0]['state'] == 'AWAITING_APPROVAL'
    with pytest.raises(ToolError): registry.run('text-count', {'text': 'a'}, subject='alice', host_id='pc')
    registry.approve('text-count', subject='alice', host_id='pc', read_roots={}, write_roots={})
    for text, expected in [('abc', 3), ('abcd', 4)]:
        result = registry.run('text-count', {'text': text}, subject='alice', host_id='pc')
        assert result['result'] == {'count': expected}
        assert result['receipt']['decision'] == 'ALLOW'
        assert registry.verify_receipt(result['receipt'])
    assert len(registry.catalogue('alice', 'pc')) == 1
    assert registry.catalogue('mallory', 'pc') == []


def test_subject_host_expiry_and_revocation_are_checked_each_call(tmp_path):
    registry = approved(tmp_path)
    for subject, host in [('bob', 'pc'), ('alice', 'other')]:
        with pytest.raises(ToolError): registry.run('text-count', {'text': 'abc'}, subject=subject, host_id=host)
    registry.revoke('text-count')
    assert registry.catalogue('alice', 'pc') == []
    with pytest.raises(ToolError): registry.run('text-count', {'text': 'abc'}, subject='alice', host_id='pc')
    registry.verify('text-count')
    registry.approve('text-count', subject='alice', host_id='pc', read_roots={}, write_roots={}, ttl_s=.01)
    time.sleep(.02)
    with pytest.raises(ToolError): registry.run('text-count', {'text': 'abc'}, subject='alice', host_id='pc')


def test_modifying_verified_snapshot_or_approval_cannot_execute(tmp_path):
    registry = approved(tmp_path)
    code = next((tmp_path / 'registry' / 'packages').rglob('main.py'))
    code.write_text("def run(inputs):\n return {'count':999}\n")
    with pytest.raises(ToolError): registry.run('text-count', {'text': 'abc'}, subject='alice', host_id='pc')
    assert registry.list()[0]['state'] == 'STALE'


def test_second_code_package_extends_catalogue_without_host_change(tmp_path):
    registry = approved(tmp_path)
    files = package_files("def run(inputs):\n return {'count':len(inputs['text'].split())}\n")
    manifest = json.loads(files['tool.json']); manifest['tool_id'] = 'word-count'; files['tool.json'] = json.dumps(manifest)
    cases = json.loads(files['cases.json']); cases[0]['expected'] = {'count': 1}; files['cases.json'] = json.dumps(cases)
    registry.stage(write_package(tmp_path / 'other-package', files)); registry.verify('word-count')
    registry.approve('word-count', subject='alice', host_id='pc', read_roots={}, write_roots={})
    assert len(registry.catalogue('alice', 'pc')) == 2
    assert registry.run('word-count', {'text': 'hola mundo'}, subject='alice', host_id='pc')['result'] == {'count': 2}


def test_only_approved_input_snapshots_and_destinations_are_used(tmp_path):
    files = package_files("def run(inputs):\n text=open('/inputs/in.txt').read()\n open('report.txt','w').write(text.upper())\n return {'count':len(text)}\n")
    manifest = json.loads(files['tool.json']); manifest['effects'] = {'read':['in.txt'], 'write':['report.txt']}; files['tool.json'] = json.dumps(manifest)
    cases = json.loads(files['cases.json']); cases[0]['files'] = {'in.txt':'abc'}; files['cases.json'] = json.dumps(cases)
    incoming, outgoing = tmp_path/'input', tmp_path/'output'; incoming.mkdir(); outgoing.mkdir()
    (incoming/'in.txt').write_text('hello')
    registry=ToolRegistry(tmp_path/'registry'); registry.stage(write_package(tmp_path/'p', files)); registry.verify('text-count')
    registry.approve('text-count',subject='alice',host_id='pc',read_roots={'in':str(incoming)},write_roots={'out':str(outgoing)})
    result=registry.run('text-count',{'text':'unused'},subject='alice',host_id='pc',files={'in.txt':'hostfs://in/in.txt'},output='hostfs://out')
    assert result['result']=={'count':5}
    assert (outgoing/'report.txt').read_text()=='HELLO'
    for uri in ['hostfs://in/../outside.txt', 'hostfs://unknown/in.txt']:
        with pytest.raises(ToolError): registry.run('text-count',{'text':'a'},subject='alice',host_id='pc',files={'in.txt':uri},output='hostfs://out')
    (incoming/'link.txt').symlink_to(tmp_path/'outside.txt')
    with pytest.raises(ToolError): registry.run('text-count',{'text':'a'},subject='alice',host_id='pc',files={'in.txt':'hostfs://in/link.txt'},output='hostfs://out')


def test_dynamic_host_obeys_leases_and_existing_planner(tmp_path):
    from isymotron.tool_host import ToolHost
    from isymotron.contracts import ExecutionRequest
    from isymotron.verdicts import Decision
    from agents.planner import Planner
    registry = approved(tmp_path)
    host = ToolHost(registry, subject='alice', host_id='pc')
    assert 'tools.text-count' in Planner.catalogue([host.describe()])
    lease, decision = host.request_lease('alice', 'tools.text-count', 1)
    assert decision.decision == Decision.ALLOW
    req = ExecutionRequest.make('pc', 'alice', 'tools.text-count', {'inputs':{'text':'abc'}}, lease.lease_id)
    receipt = host.execute_capability(req)
    assert receipt.decision.decision == Decision.ALLOW
    assert receipt.result['result'] == {'count':3}
    assert receipt.verify()
    registry.revoke('text-count')
    assert 'tools.text-count' not in Planner.catalogue([host.describe()])
    assert host.execute_capability(req).decision.decision == Decision.DENY


def test_old_lease_does_not_authorize_a_new_package(tmp_path):
    from isymotron.tool_host import ToolHost
    from isymotron.contracts import ExecutionRequest
    from isymotron.verdicts import Decision
    registry = approved(tmp_path)
    host = ToolHost(registry, subject='alice', host_id='pc')
    lease, _ = host.request_lease('alice', 'tools.text-count', 60)
    files = package_files("def run(inputs):\n return {'count':len(inputs['text'])+1}\n")
    cases=json.loads(files['cases.json']);cases[0]['expected']={'count':4};files['cases.json']=json.dumps(cases)
    registry.stage(write_package(tmp_path/'changed',files));registry.verify('text-count')
    registry.approve('text-count',subject='alice',host_id='pc',read_roots={},write_roots={})
    req=ExecutionRequest.make('pc','alice','tools.text-count',{'inputs':{'text':'abc'}},lease.lease_id)
    assert host.execute_capability(req).decision.decision == Decision.DENY


def test_failed_call_records_a_verifiable_refusal(tmp_path):
    registry = staged(tmp_path)
    with pytest.raises(ToolError) as error:
        registry.run('text-count', {'text':'abc'}, subject='alice', host_id='pc')
    assert registry.verify_receipt(error.value.receipt)
    assert error.value.receipt['decision']=='DENY'


def test_console_and_mobile_runner_use_the_same_dynamic_tools(tmp_path, monkeypatch):
    from agents.provider import ScriptedProvider
    from console.server import ConsoleState
    from relay.loopback import LoopbackRelay
    from tools.link_task_runner import run_task
    registry=approved(tmp_path)
    registry.approve('text-count',subject='console:local',host_id='tools-local',read_roots={},write_roots={})
    monkeypatch.setenv('ISYMOTRON_TOOLS_DIR',str(tmp_path/'registry'))
    relay=LoopbackRelay();state=ConsoleState(relay,None,str(tmp_path/'grants.json'))
    assert state.snapshot()['hosts'][0]['capabilities'][0]['id']=='tools.text-count'
    registry.approve('text-count',subject='link:mobile:phone',host_id='tools-local',read_roots={},write_roots={})
    reply=json.dumps({'understood':'count','steps':[{'host':'tools-local','capability':'tools.text-count','params':{'inputs':{'text':'abc'}}}],'refused':None})
    result=run_task(LoopbackRelay(),ScriptedProvider([reply]),{'title':'count','body':'abc','from':'phone'})
    assert result['status']=='done'
