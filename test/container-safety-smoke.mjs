import assert from 'node:assert/strict';
import { readFileSync, writeFileSync } from 'node:fs';

assert.equal(process.getuid(), 1000, 'application must use an unprivileged UID');
const status = readFileSync('/proc/self/status', 'utf8');
assert.match(status, /^CapEff:\s+0+$/m, 'effective capabilities must be empty');
assert.match(status, /^NoNewPrivs:\s+1$/m, 'privilege escalation must be disabled');
for (const target of ['/app/security-canary', '/tmp/security-canary', '/security-canary']) {
  assert.throws(() => writeFileSync(target, 'synthetic'),
    error => ['EROFS', 'EACCES'].includes(error.code), 'filesystem must deny writes');
}
const cgroupLimit = ['/sys/fs/cgroup/pids.max', '/sys/fs/cgroup/pids/pids.max']
  .map(path => { try { return readFileSync(path, 'utf8').trim(); } catch { return null; } })
  .find(value => value !== null);
assert.equal(cgroupLimit, '128', 'process limit must be enforced');
console.log('Container boundaries verified; starting synthetic OAuth acceptance.');
await import('./oauth-smoke.mjs');
