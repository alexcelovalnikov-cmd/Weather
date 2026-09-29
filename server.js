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
  tokenSecret: process.env.TOKEN_SECRET || ''
};

if (!cfg.owmKey) throw new Error('OWM_API_KEY is required');
if (!cfg.tokenSecret) throw new Error('TOKEN_SECRET is required');

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
  res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Content-Length': Buffer.byteLength(data) });
  res.end(data);
}

function sendText(res, status, text) {
  res.writeHead(status, { 'Content-Type': 'text/plain; charset=utf-8' });
  res.end(text);
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
  return req.headers['x-request-id'] || crypto.randomUUID();
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

async function handleAuthorize(url, res) {
  const responseType = url.searchParams.get('response_type');
  const clientId = url.searchParams.get('client_id');
  const redirectUri = url.searchParams.get('redirect_uri');
  const state = url.searchParams.get('state') || '';
  if (responseType !== 'code' || clientId !== cfg.clientId || !redirectUri) {
    return sendText(res, 400, 'Invalid OAuth request');
  }
  const code = crypto.randomBytes(24).toString('base64url');
  authCodes.set(code, { clientId, redirectUri, exp: Date.now() + 5 * 60 * 1000 });
  const redirect = new URL(redirectUri);
  redirect.searchParams.set('code', code);
  if (state) redirect.searchParams.set('state', state);
  res.writeHead(302, { Location: redirect.toString(), 'Cache-Control': 'no-store' });
  res.end();
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
    refreshToken = signToken({ type: 'refresh', sub: cfg.userId, exp: Math.floor(Date.now() / 1000) + 31536000 });
  } else if (grantType === 'refresh_token') {
    const p = verifyToken(refreshToken, 'refresh');
    if (!p || p.sub !== cfg.userId) return sendJson(res, 400, { error: 'invalid_grant' });
  } else {
    return sendJson(res, 400, { error: 'unsupported_grant_type' });
  }

  const accessToken = signToken({ type: 'access', sub: cfg.userId, exp: Math.floor(Date.now() / 1000) + 3600 });
  return sendJson(res, 200, {
    token_type: 'bearer',
    expires_in: 3600,
    access_token: accessToken,
    refresh_token: refreshToken
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
    if (req.method === 'GET' && url.pathname === '/health') {
      return sendJson(res, 200, { ok: true, service: 'yandex-weather-bridge' });
    }
    if (req.method === 'GET' && url.pathname === '/oauth/authorize') return handleAuthorize(url, res);
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

