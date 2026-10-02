import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, rmSync, symlinkSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const root = mkdtempSync(join(tmpdir(), 'weather-ops-test-'));
const lib = fileURLToPath(new URL('../ops/lib.sh', import.meta.url));
const harness = '. "$1"; BASE="$2"; MARKER="$5"; docker() { echo DOCKER_CALLED >> "$MARKER"; return 0; }; "$3" "$4"';
const marker = join(root, 'docker-called');
function invoke(operation, version) {
  rmSync(marker, { force: true });
  return spawnSync('/bin/sh', ['-c', harness, 'test', lib, root, operation, version, marker],
    { encoding: 'utf8', timeout: 5000 });
}
function denied(operation, version) {
  const result = invoke(operation, version);
  assert.equal(result.status, 2, `${operation}: expected rejection`);
  assert.ok(!existsSync(marker), 'rejection must precede Docker');
}
try {
  mkdirSync(join(root, 'releases', 'V12'), { recursive: true });
  assert.equal(invoke('require_release', 'V12').status, 0);
  const valid = invoke('ensure_image', 'V12');
  assert.equal(valid.status, 0);
  assert.ok(existsSync(marker));
  for (const operation of ['require_release', 'ensure_image']) {
    for (const version of ['', 'V', '../V12', 'V12/../V12', 'V12\n', 'V12;echo x',
      'V12$(echo x)', 'V12 x', '-V12', 'V１２', 'V' + '1'.repeat(16), 'V13']) {
      denied(operation, version);
    }
  }
  symlinkSync(join(root, 'releases', 'V12'), join(root, 'releases', 'V14'));
  denied('require_release', 'V14');
  denied('ensure_image', 'V14');
  rmSync(join(root, 'releases'), { recursive: true });
  mkdirSync(join(root, 'other', 'V12'), { recursive: true });
  symlinkSync(join(root, 'other'), join(root, 'releases'));
  denied('require_release', 'V12');
  denied('ensure_image', 'V12');
  console.log('Release input smoke passed: valid source, hostile versions, missing and symlink releases.');
} finally {
  rmSync(root, { recursive: true, force: true });
}
