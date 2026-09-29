import { spawn } from 'node:child_process';

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
  YANDEX_SCOPE: 'weather:read'
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
  if (form.status !== 200 || !html.includes('Подключить датчик')) {
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
  if (auth.status !== 302) throw new Error('authorization did not redirect');

  const callback = new URL(auth.headers.get('location'));
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
