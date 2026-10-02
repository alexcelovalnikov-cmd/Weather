import hashlib
import io
import json
import os
import pathlib
import platform
import subprocess
import sys
import tarfile
import tempfile
import unittest

class RegistrationTests(unittest.TestCase):
 def test_verified_fixture_token_uses_current_runner_input_without_argv_or_logs(self):
  if os.getuid()==0:self.skipTest('unprivileged runner helper required')
  if platform.system()=='Darwin' and platform.machine()=='arm64':route='local-mac';name='hybrid-weather-mac'
  elif platform.system()=='Linux' and platform.machine()=='x86_64':route='local-linux';name='hybrid-weather-linux'
  else:self.skipTest('registration supported on Mac ARM64 and Linux X64')
  token='unit-test-one-time-token'
  config=b'''#!/bin/bash
set -eu
[[ "${ACTIONS_RUNNER_INPUT_TOKEN:-}" == "unit-test-one-time-token" ]]
[[ -z "${GH_TOKEN:-}" ]]
[[ -z "${GITHUB_TOKEN:-}" ]]
for arg in "$@"; do [[ "$arg" != "unit-test-one-time-token" ]]; done
'''
  with tempfile.TemporaryDirectory() as d:
   root=pathlib.Path(d);archive=root/'runner.tar'
   with tarfile.open(archive,'w') as tf:
    m=tarfile.TarInfo('config.sh');m.size=len(config);m.mode=0o755;tf.addfile(m,io.BytesIO(config))
   sha=hashlib.sha256(archive.read_bytes()).hexdigest()
   script=pathlib.Path(__file__).resolve().parents[1]/'scripts/register-runner.py'
   args=[sys.executable,str(script),'--repo','alexcelovalnikov-cmd/Weather','--route',route,
         '--name',name,'--archive',str(archive),'--sha256',sha,'--workdir',str(root/'work'),
         '--approved-disposable-vm']
   env={**os.environ,'GH_TOKEN':'fake-parent-credential','GITHUB_TOKEN':'fake-parent-credential'}
   approvals=['--approved-disposable-vm']
   if route=='local-mac':approvals.append('--approved-direct-mac')
   for index,flag in enumerate(approvals):
    with self.subTest(approval=flag):
     attempt=args[:-1]+[flag];attempt[attempt.index('--workdir')+1]=str(root/('work'+str(index)))
     r=subprocess.run(attempt,input=token+'\n',capture_output=True,text=True,env=env)
     self.assertEqual(r.returncode,0,r.stderr)
     self.assertTrue(json.loads(r.stdout)['registered'])
     self.assertNotIn(token,r.stdout+r.stderr)
