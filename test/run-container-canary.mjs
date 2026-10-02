import assert from 'node:assert/strict';
import { readFileSync, writeFileSync, mkdtempSync, rmSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { resolve, join } from 'node:path';
import { tmpdir } from 'node:os';

// Redirect the exact production env reference to an empty synthetic file before
// invoking Compose: --no-env-resolution alone still checks file existence.
const source = readFileSync('deploy/compose.production.yaml', 'utf8');
const reference = '/opt/weather-bridge/secrets/.env';
assert.equal(source.split(reference).length, 2, 'expected exactly one known env reference');
const temporary = mkdtempSync(join(tmpdir(), 'weather-compose-canary-'));
let app;
try {
  const env = join(temporary, 'synthetic.env');
  const compose = join(temporary, 'compose.yaml');
  writeFileSync(env, '', { mode: 0o600 });
  writeFileSync(compose, source.replace(reference, env), { mode: 0o600 });
  app = JSON.parse(execFileSync('docker', ['compose', '-f', compose, 'config',
    '--format', 'json'], { encoding: 'utf8', timeout: 15000 })).services.app;
} finally {
  rmSync(temporary, { recursive: true, force: true });
}
assert.equal(app.user, '1000:1000');
assert.equal(app.read_only, true);
assert.deepEqual(app.cap_drop, ['ALL']);
assert.deepEqual(app.security_opt, ['no-new-privileges:true']);
assert.equal(app.pids_limit, 128);
assert.ok(!app.privileged);
assert.ok(!app.volumes?.length, 'production application must have no host mounts');
execFileSync('docker', ['run', '--rm', '--network', 'none', '--read-only',
  '--cap-drop', app.cap_drop[0], '--security-opt', app.security_opt[0],
  '--pids-limit', String(app.pids_limit), '--user', app.user,
  '--mount', `type=bind,source=${resolve('test')},target=/app/test,readonly`,
  '--entrypoint', 'node', 'weather-security-canary', 'test/container-safety-smoke.mjs'],
{ stdio: 'inherit', timeout: 60000 });
