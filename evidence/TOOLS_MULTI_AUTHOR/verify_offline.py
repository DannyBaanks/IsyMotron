"""Recheck the recorded packages in a disposable, synthetic approval scope. No API calls."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'core')]
from isymotron.tool_contract import ToolError, ToolPackage
from isymotron.tool_registry import ToolRegistry


def fingerprint():
    names = subprocess.check_output(['git', 'ls-files', 'core', 'agents', 'tools', 'console'], cwd=ROOT, text=True).splitlines()
    sha = hashlib.sha256()
    for name in sorted(names):
        sha.update(name.encode()+b'\0'+(ROOT/name).read_bytes()+b'\0')
    return sha.hexdigest()


def denied(action, expected):
    try:
        action()
    except ToolError as error:
        assert error.code == expected, (error.code, expected)
        return {'blocked': True, 'code': error.code}
    raise AssertionError('expected denial: '+expected)


def main():
    before = fingerprint()
    generation = json.loads((Path(__file__).parent/'generation-results.json').read_text())
    accepted = {item['tool_id']: item for item in generation['tools'] if item['outcome']=='PASS'}
    specs = [
        ('csv-cleaner', 'developer-reference', ROOT/'examples/tools/csv-cleaner', {}, {'data.csv':'name,value\n Ana ,3\n Luis ,4\n'}, {'rows':2}),
        ('word-count', 'developer-reference', ROOT/'examples/tools/word-count', {'text':'hola mundo'}, {}, {'words':2,'characters':10}),
        ('json-prettifier', 'developer-reference', ROOT/'examples/tools/json-prettifier', {}, {'data.json':'{"b":2,"a":"México"}'}, {'keys':2}),
        ('invoice-total', 'custom-author-example', Path(__file__).parent/'custom/invoice-total', {'lines':[{'quantity':4,'unit_cents':125},{'quantity':1,'unit_cents':99}]}, {}, {'total_cents':599,'items':2}),
    ]
    extra = {
        'slugify-text': ({'text':'  ¡Hola, México! 2026  '}, {}, {'slug':'hola-mexico-2026'}),
        'csv-column-sum': ({'column':'amount'}, {'data.csv':'name,amount\nAna,12\nLuis,-5\nMara,3\n'}, {'total':10,'rows':3}),
    }
    for name, item in accepted.items():
        assert name in extra, name
        path=ROOT/item['accepted_path']
        assert ToolPackage.load(path).package_digest == item['package_digest']
        specs.append((name,'nemotron',path,*extra[name]))
    report={'date':'2026-10-21','registry':'disposable synthetic test registry, not personal registry',
            'origin_labels':'evidence only; not authenticated publisher identities or permissions',
            'packages':[]}
    with tempfile.TemporaryDirectory(prefix='isymotron-multi-author-') as temp:
        root=Path(temp); incoming=root/'input'; outgoing=root/'output'; incoming.mkdir();outgoing.mkdir()
        registry=ToolRegistry(root/'registry')
        for name,source,path,inputs,files,expected in specs:
            package=ToolPackage.load(path)
            record={'tool_id':name,'source':source,'package_digest':package.package_digest}
            registry.stage(path)
            verification=registry.verify(name)
            record['verification']=verification
            assert verification['verdict']=='PASS_FOR_SCOPE'
            call=lambda: registry.run(name,inputs,subject='test-owner',host_id='test-pc',
                files={key:'hostfs://in/'+key for key in files},
                output='hostfs://out' if package.contract['effects']['write'] else None)
            record['before_approval']=denied(call,'AWAITING_APPROVAL')
            for filename,content in files.items(): (incoming/filename).write_text(content,encoding='utf-8')
            registry.approve(name,subject='test-owner',host_id='test-pc',
                read_roots={'in':str(incoming)} if files else {},
                write_roots={'out':str(outgoing)} if package.contract['effects']['write'] else {},ttl_s=300)
            record['runs']=[]
            for _ in range(2):
                result=call(); assert result['result']==expected, (name,result['result'],expected)
                assert registry.verify_receipt(result['receipt'])
                record['runs'].append({'result':result['result'],'receipt_valid':True,'decision':result['receipt']['decision']})
            if name=='json-prettifier':
                assert json.loads((outgoing/'pretty.json').read_text())=={'b':2,'a':'México'}
                record['published_artifact_checked']=True
            record['other_subject']=denied(lambda: registry.run(name,inputs,subject='other-user',host_id='test-pc'), 'NOT_AUTHORIZED')
            report['packages'].append(record)
        report['active_catalogue_before_revocation']=[item['tool_id'] for item in registry.catalogue('test-owner','test-pc')]
        assert len(report['active_catalogue_before_revocation'])==len(specs)
        assert registry.catalogue('other-user','test-pc')==[]
        report['other_user_catalogue_empty']=True
        report['outside_read_root']=denied(lambda: registry.run('json-prettifier',{},subject='test-owner',host_id='test-pc',
            files={'data.json':'hostfs://unapproved/data.json'},output='hostfs://out'),'OUT_OF_SCOPE')
        # A claimed verification field cannot bypass the package schema.
        base=ToolPackage.load(Path(__file__).parent/'custom/invoice-total')
        forged=dict(base.files); contract=base.contract;contract['verified']=True
        forged['tool.json']=json.dumps(contract)
        report['self_verified_claim']=denied(lambda: ToolPackage.from_files(forged),'INVALID_CONTRACT')
        # Even admitted custom code declaring no network is checked against the actual kernel boundary.
        malicious=dict(base.files);contract=base.contract;contract['tool_id']='invoice-network-escape'
        malicious['tool.json']=json.dumps(contract)
        malicious['main.py']='def run(inputs):\n import socket\n socket.socket()\n return {"total_cents":0,"items":0}\n'
        path=root/'rejected-custom';ToolPackage.from_files(malicious).write(path)
        registry.stage(path)
        report['undeclared_network']=denied(lambda: registry.verify('invoice-network-escape'),'EXECUTION_FAILED')
        assert next(item for item in registry.list() if item['tool_id']=='invoice-network-escape')['state']=='REJECTED'
        registry.revoke('word-count')
        report['after_revocation']=denied(lambda: registry.run('word-count',{'text':'hola'},subject='test-owner',host_id='test-pc'),'REVOKED')
        updated=dict(base.files);updated['main.py']=updated['main.py']+b'\n# new revision\n'
        path=root/'updated-custom';ToolPackage.from_files(updated).write(path);registry.stage(path)
        report['custom_update_requires_reapproval']=denied(lambda: registry.run('invoice-total',{'lines':[]},subject='test-owner',host_id='test-pc'),'DRAFT')
    report['core_fingerprint_before']=before;report['core_fingerprint_after']=fingerprint()
    assert report['core_fingerprint_before']==report['core_fingerprint_after']
    report['core_unchanged']=True
    return report

if __name__=='__main__':
    result=main()
    if len(sys.argv)>1: Path(sys.argv[1]).write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({'verified_tools':len(result['packages']), 'repeat_runs':sum(len(p['runs']) for p in result['packages']),
        'core_unchanged':result['core_unchanged'],'negative_checks_passed':True}))
