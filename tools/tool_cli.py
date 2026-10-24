#!/usr/bin/env python3
"""Local extensible-tool lifecycle. Constructing a package never approves it."""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for part in (ROOT, ROOT/'core'):
    if str(part) not in sys.path: sys.path.insert(0,str(part))

from isymotron.tool_contract import ToolError, require
from isymotron.tool_registry import ToolRegistry


def mapping(values):
    result={}
    for value in values:
        key, sep, target=value.partition('=')
        require(sep and key and target and key not in result, 'use unique NAME=VALUE bindings')
        result[key]=target
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registry',default=os.environ.get('ISYMOTRON_TOOLS_DIR',str(Path.home()/'.isymotron'/'tools')))
    parser.add_argument('--subject',default='console:local')
    parser.add_argument('--host',default='tools-local')
    sub=parser.add_subparsers(dest='command',required=True)
    stage=sub.add_parser('stage');stage.add_argument('package')
    for name in ('verify','revoke'): sub.add_parser(name).add_argument('tool_id')
    approve=sub.add_parser('approve');approve.add_argument('tool_id');approve.add_argument('--yes',action='store_true')
    approve.add_argument('--read-root',action='append',default=[]);approve.add_argument('--write-root',action='append',default=[])
    approve.add_argument('--ttl',type=float,default=3600)
    sub.add_parser('list')
    run=sub.add_parser('run');run.add_argument('tool_id');run.add_argument('--inputs',required=True)
    run.add_argument('--file',action='append',default=[]);run.add_argument('--output')
    propose=sub.add_parser('propose');propose.add_argument('intent');propose.add_argument('--destination',required=True)
    sub.add_parser('demo')
    args=parser.parse_args(argv)
    try:
        if args.command=='propose':
            from agents.provider import Provider
            from agents.tool_builder import ToolBuilder
            provider=Provider();require(provider.configured(),'configure the existing provider first','PROVIDER_UNAVAILABLE')
            package=ToolBuilder(provider).propose(args.intent,args.destination)
            result={'tool_id':package.tool_id,'package_digest':package.package_digest,'state':'DRAFT','path':args.destination}
        elif args.command=='demo':
            result=demo()
        else:
            registry=ToolRegistry(args.registry)
            if args.command=='stage': result=registry.stage(args.package)
            elif args.command=='verify': result=registry.verify(args.tool_id)
            elif args.command=='list': result=registry.list()
            elif args.command=='approve':
                require(args.yes,'review contract and roots, then pass --yes to approve','APPROVAL_REQUIRED')
                result=registry.approve(args.tool_id,subject=args.subject,host_id=args.host,
                                        read_roots=mapping(args.read_root),write_roots=mapping(args.write_root),ttl_s=args.ttl)
            elif args.command=='revoke':
                registry.revoke(args.tool_id);result={'tool_id':args.tool_id,'state':'REVOKED'}
            else:
                value=Path(args.inputs[1:]).read_text() if args.inputs.startswith('@') else args.inputs
                result=registry.run(args.tool_id,json.loads(value),subject=args.subject,host_id=args.host,
                                    files=mapping(args.file),output=args.output)
        print(json.dumps(result,ensure_ascii=False,allow_nan=False))
        return 0
    except (ToolError,OSError,ValueError) as error:
        print(json.dumps({'error':getattr(error,'code','INVALID_REQUEST'),'detail':getattr(error,'detail','request failed'),
                          **({'receipt':error.receipt} if hasattr(error,'receipt') else {})}))
        return 2


def demo():
    """Only the two bundled fixtures, in a disposable local grant scope."""
    with tempfile.TemporaryDirectory(prefix='isymotron-tool-demo-') as temp:
        root=Path(temp);incoming=root/'input';outgoing=root/'output';incoming.mkdir();outgoing.mkdir()
        (incoming/'data.csv').write_text('name,value\n Ana ,3\n Luis ,4\n')
        registry=ToolRegistry(root/'registry');results={}
        for name,inputs,files,output in [('csv-cleaner',{}, {'data.csv':'hostfs://in/data.csv'},'hostfs://out'),
                                          ('word-count',{'text':'hola mundo'}, {},None)]:
            registry.stage(ROOT/'examples'/'tools'/name);registry.verify(name)
            registry.approve(name,subject='demo',host_id='demo-pc',read_roots={'in':str(incoming)},write_roots={'out':str(outgoing)})
            results[name]=registry.run(name,inputs,subject='demo',host_id='demo-pc',files=files,output=output)
        results['published_report']=json.loads((outgoing/'report.json').read_text())
        results['active_tools']=[item['tool_id'] for item in registry.catalogue('demo','demo-pc')]
        registry.revoke('word-count')
        try:registry.run('word-count',{'text':'no'},subject='demo',host_id='demo-pc')
        except ToolError as error:results['revocation_enforced']=error.code=='REVOKED'
        return results


if __name__=='__main__':raise SystemExit(main())
