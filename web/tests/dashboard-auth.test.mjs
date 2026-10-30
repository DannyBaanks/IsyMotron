import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { spawn } from 'node:child_process';
import { once } from 'node:events';

async function listen(server) { server.listen(0, '127.0.0.1'); await once(server, 'listening'); return server.address().port; }

test('dashboard requires its own visitor key before proxying backend state', { timeout: 60000 }, async () => {
  let calls = 0;
  const backend = http.createServer((req, res) => { calls++; res.setHeader('content-type','application/json'); res.end(JSON.stringify({hosts:[], secret: 'private-canary'})); });
  const backendPort = await listen(backend);
  const reservation = http.createServer(); const port = await listen(reservation); await new Promise(r => reservation.close(r));
  const child = spawn(process.execPath, ['node_modules/next/dist/bin/next','dev','--hostname','127.0.0.1','--port',String(port)], { env: {...process.env, ISYMOTRON_BACKEND_URL:`http://127.0.0.1:${backendPort}`, ISYMOTRON_SESSION_TOKEN:'backend-key', ISYMOTRON_DASHBOARD_TOKEN:'visitor-key'}, stdio:'ignore' });
  const base = `http://127.0.0.1:${port}`;
  try {
    let response;
    for (let i=0;i<150;i++) { try { response=await fetch(base+'/api/dashboard'); break; } catch { await new Promise(r=>setTimeout(r,200)); } }
    assert.ok(response, 'Next server started');
    assert.equal(response.status,401);
    assert.equal(calls,0);
    response=await fetch(base+'/api/dashboard',{headers:{Authorization:'Bearer wrong'}});
    assert.equal(response.status,401);
    assert.equal(calls,0);
    response=await fetch(base+'/api/dashboard',{headers:{Authorization:'Bearer visitor-key'}});
    assert.equal(response.status,200);
    assert.equal((await response.json()).secret,'private-canary');
    assert.equal(calls,1);
  } finally { child.kill('SIGTERM'); await new Promise(r=>backend.close(r)); }
});
