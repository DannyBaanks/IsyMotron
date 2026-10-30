import http.server, json, os, subprocess, threading, time, urllib.request, urllib.error
from pathlib import Path

root = Path('/tmp/isymotron-audit-20261021-9gqd5ba8')
fixture_token = 'audit-fixture-only-not-a-real-secret'
payload = json.loads((root/'backend-state.json').read_text())
payload['receipts'][0]['result']['audit_canary'] = 'AUDIT_FIXTURE_PRIVATE_RESULT'

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.headers.get('X-IsyMotron-Token') != fixture_token:
            self.send_response(401);self.end_headers();return
        body=json.dumps(payload).encode()
        self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(body)
    def log_message(self,*args):pass

backend = http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
threading.Thread(target=backend.serve_forever,daemon=True).start()
base = f'http://127.0.0.1:{backend.server_port}'
env = dict(os.environ,ISYMOTRON_SESSION_TOKEN=fixture_token,ISYMOTRON_BACKEND_URL=base)
log = (root/'evidence/auth-server.log').open('w')
proc = subprocess.Popen(['npm','run','start','--','--hostname','127.0.0.1','--port','3182'],cwd=root/'master/web',env=env,stdout=log,stderr=log,start_new_session=True)
try:
    for _ in range(100):
        try:
            urllib.request.urlopen('http://127.0.0.1:3182/',timeout=1).close();break
        except (urllib.error.URLError,TimeoutError):time.sleep(.1)
    try:urllib.request.urlopen(base+'/api/state',timeout=5)
    except urllib.error.HTTPError as error:direct_status=error.code
    with urllib.request.urlopen('http://127.0.0.1:3182/api/dashboard',timeout=5) as response:
        result={'direct_backend_without_token':direct_status,'frontend_proxy_without_token_or_cookie':response.status,'private_result_exposed':'AUDIT_FIXTURE_PRIVATE_RESULT' in response.read().decode()}
    (root/'evidence/auth-results.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
finally:
    import signal
    os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=10)
    backend.shutdown();backend.server_close();log.close()
