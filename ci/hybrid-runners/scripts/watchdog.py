#!/usr/bin/env python3
"""Read-only external check. Wire exit status to the operator's existing monitor."""
import argparse,json,sqlite3,time
p=argparse.ArgumentParser();p.add_argument('--state',required=True);p.add_argument('--max-age',type=int,default=60)
a=p.parse_args()
try:
 db=sqlite3.connect('file:'+a.state+'?mode=ro',uri=True)
 row=db.execute('SELECT value FROM meta WHERE key="heartbeat"').fetchone()
 age=time.time()-float(row[0]) if row else None
 pending=db.execute("SELECT COUNT(*) FROM tasks WHERE state='dispatching' AND dispatched<?",(time.time()-120,)).fetchone()[0]
 probe=db.execute('SELECT value FROM meta WHERE key="hosted_probe"').fetchone()
 unknown_probe=bool(probe and json.loads(probe[0]).get('state')=='unknown')
 healthy=age is not None and 0<=age<=a.max_age and not pending and not unknown_probe
 print(json.dumps({'healthy':healthy,'heartbeat_age':age,'unknown_dispatches':pending,'unknown_probe':unknown_probe}))
 raise SystemExit(0 if healthy else 2)
except (sqlite3.Error,ValueError,OSError):
 print(json.dumps({'healthy':False,'reason':'state unavailable'}));raise SystemExit(2)
