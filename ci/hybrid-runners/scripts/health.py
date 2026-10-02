#!/usr/bin/env python3
"""Publish a bounded health record in the operator-owned heartbeat directory.
Run from VM management context, never as a workflow step. No authenticated payloads.
"""
import argparse
import json
import os
import pathlib
import shutil
import subprocess
import time
p=argparse.ArgumentParser();p.add_argument('--runner-name',required=True);p.add_argument('--host-id',required=True)
p.add_argument('--listener-pid',type=int,required=True);p.add_argument('--output',required=True)
p.add_argument('--min-free-gb',type=int,default=10);p.add_argument('--min-available-mb',type=int,default=768)
a=p.parse_args();cap=[];reasons=[]
process=subprocess.run(['ps','-p',str(a.listener_pid),'-o','comm='],capture_output=True,text=True)
if process.returncode or 'Runner.Listener' not in process.stdout:reasons.append('listener-unavailable')
free=shutil.disk_usage(pathlib.Path(a.output).parent).free
if free<a.min_free_gb*1024**3:reasons.append('disk-headroom')
for binary,label,version in [('node','node24','v24.'),('node','node22','v22.'),('python3.12','python312','Python 3.12.'),('python3.9','python39','Python 3.9.')]:
 try:
  r=subprocess.run([binary,'--version'],capture_output=True,text=True,timeout=5)
  if version in r.stdout+r.stderr:cap.append(label)
 except (OSError,subprocess.TimeoutExpired):pass
if pathlib.Path('/proc/meminfo').exists():
 lines=pathlib.Path('/proc/meminfo').read_text().splitlines()
 available=next(int(x.split()[1])*1024 for x in lines if x.startswith('MemAvailable:'))
 if available<a.min_available_mb*1024**2:reasons.append('ram-headroom')
 try:
  context=subprocess.check_output(['docker','context','inspect'],text=True,timeout=5)
  endpoint=json.loads(context)[0]['Endpoints']['docker']['Host']
  info=json.loads(subprocess.check_output(['docker','info','--format','{{json .}}'],text=True,timeout=5))
  # No production/root Docker socket. Require verified rootless daemon.
  if endpoint=='unix:///var/run/docker.sock' or not any('rootless' in x for x in info.get('SecurityOptions',[])):
   reasons.append('docker-not-rootless')
  else:cap.append('docker-rootless')
  subprocess.run(['docker','compose','version'],check=True,capture_output=True,timeout=5);cap.append('compose')
 except (OSError,ValueError,KeyError,subprocess.SubprocessError):pass
record={'runner_name':a.runner_name,'host_id':a.host_id,'observed_at':time.time(),
        'healthy':not reasons,'capabilities':cap,'reasons':reasons}
out=pathlib.Path(a.output);out.parent.mkdir(parents=True,exist_ok=True)
tmp=out.with_suffix('.tmp');tmp.write_text(json.dumps(record)+'\n');os.chmod(tmp,0o600);os.replace(tmp,out)
print(json.dumps(record))
