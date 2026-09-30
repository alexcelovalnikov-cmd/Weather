const http = require('node:http');
const crypto = require('node:crypto');
const { URL } = require('node:url');

const cfg = {
  port: Number(process.env.PORT || 8787),
  owmKey: process.env.OWM_API_KEY || '',
  lat: process.env.WEATHER_LAT || '56.7805',
  lon: process.env.WEATHER_LON || '60.5156',
  deviceId: process.env.DEVICE_ID || 'outdoor-temperature',
  deviceName: process.env.DEVICE_NAME || 'Улица',
  userId: process.env.USER_ID || 'owner',
  cacheTtlMs: Number(process.env.CACHE_TTL_MS || 300000),
  clientId: process.env.YANDEX_CLIENT_ID || '',
  clientSecret: process.env.YANDEX_CLIENT_SECRET || '',
  tokenSecret: process.env.TOKEN_SECRET || '',
  linkPassword: process.env.YANDEX_LINK_PASSWORD || '',
  redirectUri: process.env.YANDEX_REDIRECT_URI || 'https://social.yandex.net/broker/redirect',
  scope: process.env.YANDEX_SCOPE || 'weather:read'
};

if (!cfg.owmKey) throw new Error('OWM_API_KEY is required');
if (!cfg.tokenSecret) throw new Error('TOKEN_SECRET is required');
if (!cfg.clientId || !cfg.clientSecret) throw new Error('YANDEX_CLIENT_ID and YANDEX_CLIENT_SECRET are required');
if (!cfg.linkPassword) throw new Error('YANDEX_LINK_PASSWORD is required');

const authCodes = new Map();
let weatherCache = { at: 0, value: null };

function b64url(input) {
  return Buffer.from(input).toString('base64url');
}

function signToken(payload) {
  const body = b64url(JSON.stringify(payload));
  const sig = crypto.createHmac('sha256', cfg.tokenSecret).update(body).digest('base64url');
  return body + '.' + sig;
}

function verifyToken(token, expectedType) {
  try {
    const [body, sig] = String(token || '').split('.');
    if (!body || !sig) return null;
    const expected = crypto.createHmac('sha256', cfg.tokenSecret).update(body).digest('base64url');
    if (!crypto.timingSafeEqual(Buffer.from(sig), Buffer.from(expected))) return null;
    const payload = JSON.parse(Buffer.from(body, 'base64url').toString('utf8'));
    if (payload.type !== expectedType || payload.exp < Math.floor(Date.now() / 1000)) return null;
    return payload;
  } catch {
    return null;
  }
}

function sendJson(res, status, obj) {
  const data = JSON.stringify(obj);
  res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Content-Length': Buffer.byteLength(data), 'Cache-Control': 'no-store' });
  res.end(data);
}

function sendText(res, status, text) {
  res.writeHead(status, {
    'Content-Type': 'text/plain; charset=utf-8',
    'Cache-Control': 'no-store'
  });
  res.end(text);
}

function sendHtml(res, status, html) {
  res.writeHead(status, {
    'Content-Type': 'text/html; charset=utf-8',
    'Cache-Control': 'no-store',
    'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
  });
  res.end(html);
}

function safeEqualText(a, b) {
  const aa = Buffer.from(String(a || ''));
  const bb = Buffer.from(String(b || ''));
  return aa.length === bb.length && crypto.timingSafeEqual(aa, bb);
}

async function readBody(req) {
  let raw = '';
  for await (const chunk of req) {
    raw += chunk;
    if (raw.length > 1024 * 1024) throw new Error('Body too large');
  }
  return raw;
}

function reqId(req) {
  if (!req._weatherRequestId) {
    req._weatherRequestId = req.headers['x-request-id'] || crypto.randomUUID();
  }
  return req._weatherRequestId;
}

function bearerPayload(req) {
  const header = req.headers.authorization || '';
  const match = header.match(/^Bearer\s+(.+)$/i);
  return match ? verifyToken(match[1], 'access') : null;
}

function requireAuth(req, res) {
  const token = bearerPayload(req);
  if (!token || token.sub !== cfg.userId) {
    sendJson(res, 401, { error: 'unauthorized' });
    return null;
  }
  return token;
}

function parseClientAuth(req, params) {
  let clientId = params.get('client_id') || '';
  let clientSecret = params.get('client_secret') || '';
  const auth = req.headers.authorization || '';
  if (auth.startsWith('Basic ')) {
    try {
      const [id, secret] = Buffer.from(auth.slice(6), 'base64').toString('utf8').split(':');
      clientId = id || clientId;
      clientSecret = secret || clientSecret;
    } catch {}
  }
  return { clientId, clientSecret };
}

async function getWeather() {
  if (weatherCache.value && Date.now() - weatherCache.at < cfg.cacheTtlMs) return weatherCache.value;
  const u = new URL('https://api.openweathermap.org/data/2.5/weather');
  u.searchParams.set('lat', cfg.lat);
  u.searchParams.set('lon', cfg.lon);
  u.searchParams.set('appid', cfg.owmKey);
  u.searchParams.set('units', 'metric');
  u.searchParams.set('lang', 'ru');
  const r = await fetch(u);
  if (!r.ok) throw new Error('OpenWeather HTTP ' + r.status);
  const data = await r.json();
  const value = {
    temperature: Math.round(Number(data.main.temp) * 10) / 10,
    name: data.name || '',
    fetchedAt: new Date().toISOString()
  };
  weatherCache = { at: Date.now(), value };
  return value;
}

function deviceDescription() {
  return {
    id: cfg.deviceId,
    name: cfg.deviceName,
    description: 'Температура на улице из OpenWeather',
    room: 'Улица',
    type: 'devices.types.sensor.climate',
    capabilities: [],
    properties: [{
      type: 'devices.properties.float',
      retrievable: true,
      reportable: false,
      parameters: {
        instance: 'temperature',
        unit: 'unit.temperature.celsius'
      }
    }],
    device_info: {
      manufacturer: 'Private Weather Bridge',
      model: 'OpenWeather Outdoor Sensor',
      hw_version: 'virtual',
      sw_version: '1.0'
    }
  };
}

async function handleAuthorize(req, url, res) {
  const source = req.method === 'POST'
    ? new URLSearchParams(await readBody(req))
    : url.searchParams;

  const responseType = source.get('response_type');
  const clientId = source.get('client_id');
  const redirectUri = source.get('redirect_uri');
  const state = source.get('state') || '';
  const scope = source.get('scope') || cfg.scope;

  if (
    responseType !== 'code' ||
    clientId !== cfg.clientId ||
    redirectUri !== cfg.redirectUri ||
    scope !== cfg.scope
  ) {
    return sendText(res, 400, 'Invalid OAuth request');
  }

  if (req.method === 'GET') {
    const esc = (value) => String(value).replace(/[&<>"']/g, (ch) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    })[ch]);
    return sendHtml(res, 200, `<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Weather Bridge</title>
<style>
body{font-family:-apple-system,BlinkMacSystemFont,sans-serif;max-width:420px;margin:64px auto;padding:0 20px;color:#111}
h1{font-size:24px;margin-bottom:8px}p{color:#555;line-height:1.45}
input,button{box-sizing:border-box;width:100%;font:inherit;padding:12px;border-radius:10px}
input{border:1px solid #ccc;margin:12px 0}button{border:0;background:#111;color:#fff;cursor:pointer}\n.tools{display:grid;gap:10px;margin-top:18px}.secondary{background:#f1f1f3;color:#111}.status{font-size:13px;min-height:20px;margin-top:8px}
</style>
</head>
<body>
<h1>Подключить датчик «Улица»</h1>
<p>Введите пароль Weather Bridge, чтобы разрешить Яндексу получать температуру.</p>
<form method="post" action="./authorize">
<input type="hidden" name="response_type" value="${esc(responseType)}">
<input type="hidden" name="client_id" value="${esc(clientId)}">
<input type="hidden" name="redirect_uri" value="${esc(redirectUri)}">
<input type="hidden" name="state" value="${esc(state)}">
<input type="hidden" name="scope" value="${esc(scope)}">
<input type="password" name="password" autocomplete="current-password" required autofocus>
<button type="submit">Подключить к Яндексу</button>
</form>
<div class="tools">
<button type="button" class="secondary" onclick="window.open(window.location.href,'_blank','noopener,noreferrer')">Попробовать открыть в Safari</button>
<button type="button" class="secondary" onclick="copyCurrentLink()">Скопировать ссылку</button>
</div>
<p id="copy-status" class="status"></p>
<script>
async function copyCurrentLink(){
  const status=document.getElementById('copy-status');
  try{
    await navigator.clipboard.writeText(window.location.href);
    status.textContent='Ссылка скопирована';
  }catch(e){
    const t=document.createElement('textarea');
    t.value=window.location.href;
    document.body.appendChild(t);
    t.select();
    document.execCommand('copy');
    t.remove();
    status.textContent='Ссылка скопирована';
  }
}
</script>
</body>
</html>`);
  }

  if (!safeEqualText(source.get('password'), cfg.linkPassword)) {
    console.log(JSON.stringify({ time: new Date().toISOString(), oauth: 'authorize_rejected', reason: 'invalid_password' }));
    return sendText(res, 401, 'Invalid password');
  }

  const code = crypto.randomBytes(24).toString('base64url');
  authCodes.set(code, {
    clientId,
    redirectUri,
    scope,
    exp: Date.now() + 5 * 60 * 1000
  });

  const redirect = new URL(redirectUri);
  redirect.searchParams.set('code', code);
  redirect.searchParams.set('state', state);
  redirect.searchParams.set('client_id', clientId);
  redirect.searchParams.set('scope', scope);
  console.log(JSON.stringify({ time: new Date().toISOString(), oauth: 'authorize_success', redirect_host: redirect.host }));
  const target = escHtml(redirect.toString());
  return sendHtml(res, 200, `<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Weather Bridge</title>
<style>
body{font-family:-apple-system,BlinkMacSystemFont,sans-serif;max-width:420px;margin:64px auto;padding:0 20px;color:#111}
h1{font-size:24px;margin-bottom:8px}p{color:#555;line-height:1.45}
a{display:block;box-sizing:border-box;width:100%;padding:14px;border-radius:10px;background:#111;color:#fff;text-align:center;text-decoration:none;margin-top:20px}
</style>
</head>
<body>
<h1>Пароль принят</h1>
<p>Нажмите кнопку, чтобы завершить привязку аккаунта в Яндексе.</p>
<a href="${target}">Продолжить в Яндекс</a>
</body>
</html>`);
}

async function handleToken(req, res) {
  const raw = await readBody(req);
  const params = new URLSearchParams(raw);
  const { clientId, clientSecret } = parseClientAuth(req, params);
  if (clientId !== cfg.clientId || clientSecret !== cfg.clientSecret) {
    return sendJson(res, 401, { error: 'invalid_client' });
  }

  const grantType = params.get('grant_type');
  let refreshToken = params.get('refresh_token') || '';
  if (grantType === 'authorization_code') {
    const code = params.get('code') || '';
    const record = authCodes.get(code);
    if (!record || record.exp < Date.now() || record.clientId !== clientId) {
      return sendJson(res, 400, { error: 'invalid_grant' });
    }
    const redirectUri = params.get('redirect_uri');
    if (redirectUri && redirectUri !== record.redirectUri) {
      return sendJson(res, 400, { error: 'invalid_grant' });
    }
    authCodes.delete(code);
    refreshToken = signToken({
      type: 'refresh',
      sub: cfg.userId,
      scope: record.scope || cfg.scope,
      exp: Math.floor(Date.now() / 1000) + 31536000
    });
  } else if (grantType === 'refresh_token') {
    const p = verifyToken(refreshToken, 'refresh');
    if (!p || p.sub !== cfg.userId) return sendJson(res, 400, { error: 'invalid_grant' });
  } else {
    return sendJson(res, 400, { error: 'unsupported_grant_type' });
  }

  const refreshPayload = verifyToken(refreshToken, 'refresh');
  const tokenScope = (refreshPayload && refreshPayload.scope) || cfg.scope;
  const accessToken = signToken({
    type: 'access',
    sub: cfg.userId,
    scope: tokenScope,
    exp: Math.floor(Date.now() / 1000) + 3600
  });
  return sendJson(res, 200, {
    token_type: 'bearer',
    expires_in: 3600,
    access_token: accessToken,
    refresh_token: refreshToken,
    scope: tokenScope
  });
}

async function handleDevices(req, res) {
  if (!requireAuth(req, res)) return;
  sendJson(res, 200, {
    request_id: reqId(req),
    payload: { user_id: cfg.userId, devices: [deviceDescription()] }
  });
}

async function handleQuery(req, res) {
  if (!requireAuth(req, res)) return;
  const body = JSON.parse((await readBody(req)) || '{}');
  const weather = await getWeather();
  const devices = (body.devices || []).map((d) => d.id === cfg.deviceId ? {
    id: d.id,
    properties: [{
      type: 'devices.properties.float',
      state: { instance: 'temperature', value: weather.temperature }
    }]
  } : { id: d.id, error_code: 'DEVICE_NOT_FOUND', error_message: 'Unknown device' });
  sendJson(res, 200, { request_id: reqId(req), payload: { devices } });
}

async function handleAction(req, res) {
  if (!requireAuth(req, res)) return;
  const body = JSON.parse((await readBody(req)) || '{}');
  const devices = (body.payload && body.payload.devices ? body.payload.devices : body.devices || []).map((d) => ({
    id: d.id,
    action_result: { status: 'ERROR', error_code: 'INVALID_ACTION' }
  }));
  sendJson(res, 200, { request_id: reqId(req), payload: { devices } });
}

const server = http.createServer(async (req, res) => {
  try {
    const url = new URL(req.url, 'http://' + (req.headers.host || 'localhost'));
    if (url.pathname.startsWith('/v1.0/') || url.pathname.startsWith('/oauth/')) {
      console.log(JSON.stringify({
        time: new Date().toISOString(),
        request_id: reqId(req),
        method: req.method,
        path: url.pathname
      }));
    }
    if (req.method === 'GET' && url.pathname === '/health') {
      return sendJson(res, 200, { ok: true, service: 'yandex-weather-bridge' });
    }
    if ((req.method === 'GET' || req.method === 'POST') && url.pathname === '/oauth/authorize') return handleAuthorize(req, url, res);
    if (req.method === 'POST' && url.pathname === '/oauth/token') return handleToken(req, res);
    if (req.method === 'HEAD' && url.pathname === '/v1.0/') {
      res.writeHead(200);
      return res.end();
    }
    if (req.method === 'GET' && url.pathname === '/v1.0/user/devices') return handleDevices(req, res);
    if (req.method === 'POST' && url.pathname === '/v1.0/user/devices/query') return handleQuery(req, res);
    if (req.method === 'POST' && url.pathname === '/v1.0/user/devices/action') return handleAction(req, res);
    if (req.method === 'POST' && url.pathname === '/v1.0/user/unlink') {
      if (!requireAuth(req, res)) return;
      return sendJson(res, 200, { request_id: reqId(req) });
    }
    sendJson(res, 404, { error: 'not_found' });
  } catch (err) {
    console.error(err);
    sendJson(res, 500, { error: 'internal_error' });
  }
});

server.listen(cfg.port, '0.0.0.0', () => {
  console.log('Yandex Weather Bridge listening on :' + cfg.port);
});

