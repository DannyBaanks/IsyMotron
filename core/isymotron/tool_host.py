"""Dynamic tools through the existing Host/lease/Planner surface."""
from __future__ import annotations

from .contracts import CapabilityManifest, HostDescription, HostIdentity
from .host import Host, ScopeViolation
from .verdicts import Decision, DenyReason
from .contracts import PolicyDecision
from .tool_contract import ToolError


class ToolHost(Host):
    def __init__(self, registry, *, subject='console:local', host_id='tools-local'):
        self.registry, self.subject = registry, subject
        super().__init__(HostIdentity(host_id, 'Extensible tools', 'linux', 'local', 'tools-linux/1'),
                         [], [], {}, tool_profile='custom', custom={'capabilities': []})

    def describe(self):
        entries = self.registry.catalogue(self.subject, self.identify().host_id)
        self._capabilities = [CapabilityManifest('tools.' + item['tool_id'], '1',
                              item['summary'] + ' Inputs: ' + str(item['input_schema'])
                              + ' File bindings: ' + str(item['effects']['read'])
                              + ' Read resources: ' + str(item['read_resources'])
                              + ' Write resources: ' + str(item['write_resources']),
                              scopes={'package_digest': item['package_digest']},
                              params=('inputs', 'files', 'output'), returns=('result', 'artifacts', 'receipt')) for item in entries]
        self._granted = [cap.id for cap in self._capabilities]
        self._custom = {'capabilities': list(self._granted)}
        self._grant_scopes = {'tools.' + item['tool_id']: {'tool_id': item['tool_id'], 'package_digest': item['package_digest']} for item in entries}
        return HostDescription(self.identify(), list(self._capabilities), list(self._granted), dict(self._grant_scopes))

    def request_lease(self, subject, capability, ttl_s, scope=None):
        self.describe()
        self._rebuild_enforcer()
        if subject != self.subject:
            return None, PolicyDecision(Decision.DENY, DenyReason.CAPABILITY_NOT_GRANTED, 'wrong tool subject')
        return super().request_lease(subject, capability, ttl_s, scope)

    def execute_capability(self, req, now=None):
        self.describe()
        self._rebuild_enforcer()
        return super().execute_capability(req, now)

    def run(self, req):
        try:
            result = self.registry.run(req.capability.removeprefix('tools.'), req.params['inputs'],
                                       subject=req.subject, host_id=req.host_id,
                                       files=req.params.get('files'), output=req.params.get('output'))
        except ToolError as error:
            raise ScopeViolation(DenyReason.OUT_OF_SCOPE, error.code) from error
        return result, [{'kind': 'tools.execute', 'tool': req.capability,
                         'package_digest': result['receipt']['package_digest']}]


def attach_configured_tools(relay, subject):
    """Explicit opt-in, shared by console and the Link task runner."""
    import os
    directory = os.environ.get('ISYMOTRON_TOOLS_DIR')
    if directory:
        from .tool_registry import ToolRegistry
        relay.attach(ToolHost(ToolRegistry(directory), subject=subject))
