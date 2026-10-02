#!/usr/bin/env python3
"""Registration checkpoint helper. Run ONLY inside an approved disposable worker VM.
Token enters via stdin, never via a log, GitHub PAT, shell history or subprocess argv.
One registration = one job. Restore the guest before every subsequent registration.
"""
import argparse
import hashlib
import json
import os
import pathlib
import platform
import re
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

p=argparse.ArgumentParser()
p.add_argument('--repo',required=True);p.add_argument('--route',choices=['local-linux','local-mac'],required=True)
p.add_argument('--name',required=True);p.add_argument('--archive',required=True);p.add_argument('--sha256',required=True)
p.add_argument('--workdir',required=True);p.add_argument('--approved-disposable-vm',action='store_true')
a=p.parse_args()
repos={'Weather','Server-Admin-Controller','telegram-manager','rentrabbit-chatgpt-connector'}
if a.repo not in {'alexcelovalnikov-cmd/'+x for x in repos}:p.error('repo not allowlisted')
if not a.approved_disposable_vm:p.error('disposable VM checkpoint required')
if a.route=='local-mac' and (a.repo!='alexcelovalnikov-cmd/Weather' or platform.system()!='Darwin' or platform.machine()!='arm64'):p.error('Mac canary only, Darwin ARM64 required')
if a.route=='local-linux' and (platform.system()!='Linux' or platform.machine()!='x86_64'):p.error('Linux X64 required')
expected='hybrid-weather-mac' if a.route=='local-mac' else 'hybrid-'+a.repo.split('/')[1].lower()+'-linux'
if a.name!=expected:p.error('name must match reviewed workflow label '+expected)
if os.getuid()==0:p.error('unprivileged VM worker required')
if not re.fullmatch('[0-9a-f]{64}',a.sha256):p.error('reviewed GitHub runner archive SHA256 required')
archive=pathlib.Path(a.archive)
if hashlib.sha256(archive.read_bytes()).hexdigest()!=a.sha256:p.error('archive checksum mismatch')
work=pathlib.Path(a.workdir).resolve()
work.mkdir(parents=True,exist_ok=True,mode=0o700)
if any(work.iterdir()):p.error('fresh empty VM workdir required; registration is never repeated blindly')
with tarfile.open(archive) as tf:
 for m in tf.getmembers():
  target=(work/m.name).resolve()
  if not target.is_relative_to(work) or m.isdev() or m.issym() or m.islnk():p.error('unsafe archive member')
 tf.extractall(work)
# config.sh supports RUNNER_INPUT_*; stdin token cannot appear in process command lines.
token=sys.stdin.readline().strip()
if not token:p.error('one-time registration token required on stdin')
env=os.environ.copy()
for key in ('GH_TOKEN','GITHUB_TOKEN','GITHUB_PAT'):env.pop(key,None)
env.update({'RUNNER_INPUT_TOKEN':token})
args=['./config.sh','--unattended','--ephemeral','--url','https://github.com/'+a.repo,
      '--name',a.name,'--labels',a.route+',hybrid-v1,'+a.name,'--work','_work']
r=subprocess.run(args,cwd=work,env=env,capture_output=True,text=True)
env.pop('RUNNER_INPUT_TOKEN',None);token=''
if r.returncode:raise SystemExit('Registration failed; inspect protected VM diagnostics; no automatic retry')
print(json.dumps({'registered':True,'name':a.name,'ephemeral':True,'next':'./run.sh inside disposable VM, then destroy/reset VM'}))
