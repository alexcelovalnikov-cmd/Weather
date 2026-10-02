import { spawn } from 'node:child_process';
import assert from 'node:assert/strict';
import crypto from 'node:crypto';

const port = 18877;
const base = `http://127.0.0.1:${port}`;
const env = {
  ...process.env,
  PORT: String(port),
  OWM_API_KEY: 'test-key',
  YANDEX_CLIENT_ID: 'test-client',
  YANDEX_CLIENT_SECRET: 'test-secret',
  TOKEN_SECRET: 'test-token-secret-0123456789',
  YANDEX_LINK_PASSWORD: 'test-password',
  YANDEX_REDIRECT_URI: 'https://social.yandex.net/broker/redirect',
  YANDEX_SCOPE: 'weather:read',
  USER_ID: 'synthetic-user',
  YANDEX_DIALOGS_SKILL_ID: '',
  YANDEX_DIALOGS_OAUTH_TOKEN: ''
};

const child = spawn(process.execPath, ['server.js'], {
  cwd: new URL('..', import.meta.url),
  env,
  stdio: ['ignore', 'pipe', 'pipe']
});

async function waitForHealth() {
  for (let i = 0; i < 50; i++) {
    try {
      const r = await fetch(base + '/health');
      if (r.ok) return;
    } catch {}
    await new Promise(r => setTimeout(r, 100));
  }
  throw new Error('server did not become healthy');
}
async function main() {
  await waitForHealth();
  const params = new URLSearchParams({
    response_type: 'code',
    client_id: env.YANDEX_CLIENT_ID,
    redirect_uri: env.YANDEX_REDIRECT_URI,
    state: 'smoke-state',
    scope: env.YANDEX_SCOPE
  });

  const form = await fetch(base + '/oauth/authorize?' + params);
  const html = await form.text();
  if (form.status !== 200 || !html.includes('Подключить датчик') || !html.includes('action="./authorize"')) {
    throw new Error('authorization form failed');
  }

  const bad = new URLSearchParams(params);
  bad.set('password', 'wrong');
  const badResponse = await fetch(base + '/oauth/authorize', {
    method: 'POST',
    headers: { 'content-type': 'application/x-www-form-urlencoded' },
    body: bad,
    redirect: 'manual'
  });
  if (badResponse.status !== 401) throw new Error('wrong password accepted');
  const good = new URLSearchParams(params);
  good.set('password', env.YANDEX_LINK_PASSWORD);
  const auth = await fetch(base + '/oauth/authorize', {
    method: 'POST',
    headers: { 'content-type': 'application/x-www-form-urlencoded' },
    body: good,
    redirect: 'manual'
  });
  if (auth.status !== 200) throw new Error('authorization continuation page failed');
  const continuationHtml = await auth.text();
  const href = continuationHtml.match(/href="([^"]+)"/)?.[1]?.replace(/&amp;/g, '&');
  if (!href || !continuationHtml.includes('Продолжить в Яндекс')) {
    throw new Error('authorization continuation link missing');
  }

  const callback = new URL(href);
  if (callback.origin !== 'https://social.yandex.net' ||
      callback.pathname !== '/broker/redirect' ||
      callback.searchParams.get('state') !== 'smoke-state' ||
      callback.searchParams.get('client_id') !== env.YANDEX_CLIENT_ID ||
      callback.searchParams.get('scope') !== env.YANDEX_SCOPE) {
    throw new Error('callback parameters are invalid');
  }

  const tokenBody = new URLSearchParams({
    grant_type: 'authorization_code',
    code: callback.searchParams.get('code'),
    client_id: env.YANDEX_CLIENT_ID,
    client_secret: env.YANDEX_CLIENT_SECRET,
    redirect_uri: env.YANDEX_REDIRECT_URI
  });
  const tokenResponse = await fetch(base + '/oauth/token', {
    method: 'POST',
    headers: { 'content-type': 'application/x-www-form-urlencoded' },
    body: tokenBody
  });
  const tokens = await tokenResponse.json();
  if (!tokens.access_token || !tokens.refresh_token || tokens.scope !== env.YANDEX_SCOPE) {
    throw new Error('token exchange failed');
  }

  const replayResponse = await fetch(base + '/oauth/token', {
    method: 'POST', headers: { 'content-type': 'application/x-www-form-urlencoded' }, body: tokenBody
  });
  assert.equal(replayResponse.status, 400, 'authorization code is one use');
  for (const access of ['', 'invalid', ...[
    {type:'access',sub:'synthetic-user',scope:'weather:write',exp:Math.floor(Date.now()/1000)+60},
    {type:'access',sub:'other-user',scope:'weather:read',exp:Math.floor(Date.now()/1000)+60},
    {type:'access',sub:'synthetic-user',scope:'weather:read',exp:1}
  ].map(payload => {
    const body=Buffer.from(JSON.stringify(payload)).toString('base64url');
    return body+'.'+crypto.createHmac('sha256',env.TOKEN_SECRET).update(body).digest('base64url');
  })]) {
    const response=await fetch(base+'/v1.0/user/devices/action', {
      method:'POST',headers:{authorization:'Bearer '+access,'content-type':'application/json'},
      body:JSON.stringify({devices:[{id:'synthetic-device',capabilities:[{state:{value:true}}]}]})
    });
    assert.equal(response.status,401,'invalid subject/scope/expiry must be denied');
  }
  const actionResponse=await fetch(base+'/v1.0/user/devices/action', {
    method:'POST',headers:{authorization:'Bearer '+tokens.access_token,'content-type':'application/json'},
    body:JSON.stringify({devices:[{id:'synthetic-device',capabilities:[{state:{value:true}}]}]})
  });
  assert.equal(actionResponse.status,200);
  assert.equal((await actionResponse.json()).payload.devices[0].action_result.error_code,'INVALID_ACTION');

  const refreshBody = new URLSearchParams({
    grant_type: 'refresh_token',
    refresh_token: tokens.refresh_token,
    client_id: env.YANDEX_CLIENT_ID,
    client_secret: env.YANDEX_CLIENT_SECRET
  });
  const refreshResponse = await fetch(base + '/oauth/token', {
    method: 'POST',
    headers: { 'content-type': 'application/x-www-form-urlencoded' },
    body: refreshBody
  });
  const refreshed = await refreshResponse.json();
  if (!refreshed.access_token || refreshed.scope !== env.YANDEX_SCOPE) {
    throw new Error('refresh token flow failed');
  }
  console.log('OAUTH_SMOKE_OK');
}
try {
  await main();
} finally {
  child.kill('SIGTERM');
}
