import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { resolve } from 'node:path';

// Compose is parsed without reading production env_file. The canary uses only
// synthetic credentials supplied by oauth-smoke and has no external network.
const app = JSON.parse(readFileSync(process.argv[2], 'utf8')).services.app;
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
