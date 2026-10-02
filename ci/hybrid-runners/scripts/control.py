#!/usr/bin/env python3
"""Local operator control; no workflow rewrites and no GitHub mutation."""
import argparse
import json
import os
import pathlib
import sqlite3
import time
p=argparse.ArgumentParser();p.add_argument('--config',required=True)
p.add_argument('--state');p.add_argument('--mode',choices=['AUTO','LOCAL','GITHUB'])
p.add_argument('--hosted-auto-probe',action='store_true')
p.add_argument('--hosted-verified-minutes',type=int);p.add_argument('--hosted-block',action='store_true')
a=p.parse_args();path=pathlib.Path(a.config);config=json.loads(path.read_text())
if a.mode:config['mode']=a.mode
if a.hosted_verified_minutes is not None:
 if not 1<=a.hosted_verified_minutes<=60:p.error('hosted probe TTL 1..60 minutes')
 config['hosted'].update(allowed=True,denied=False,verified_until=time.time()+60*a.hosted_verified_minutes)
 if a.state:
  db=sqlite3.connect(a.state);db.execute('DELETE FROM meta WHERE key="hosted_blocked"');db.commit()
if a.hosted_auto_probe:
 config['hosted']['probe']['enabled']=True;config['hosted']['denied']=False
if a.hosted_block:
 config['hosted'].update(allowed=False,denied=True,verified_until=0)
 config['hosted'].get('probe',{})['enabled']=False
if a.mode or a.hosted_block or a.hosted_auto_probe or a.hosted_verified_minutes is not None:
 tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(config,indent=2)+'\n');os.chmod(tmp,0o600);os.replace(tmp,path)
print(json.dumps({'mode':config['mode'],'hosted':config['hosted'],'enabled':[k for k,v in config['repositories'].items() if v['enabled']]}))
if a.state:
 db=sqlite3.connect(a.state);db.row_factory=sqlite3.Row
 print(json.dumps([dict(r) for r in db.execute('SELECT repo,sha,state,route,run_id,reason,updated FROM tasks ORDER BY updated DESC LIMIT 20')]))
 h=db.execute('SELECT value FROM meta WHERE key="heartbeat"').fetchone()
 print(json.dumps({'coordinator_heartbeat_age':time.time()-float(h[0]) if h else None}))
