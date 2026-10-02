"""Durable serial dispatcher. Only pre-start infrastructure failures can fall back."""
import argparse
import datetime
import fcntl
import json
import pathlib
import re
import sqlite3
import time
import uuid
from .github import GitHub, APIError
from .router import choose
from . import probe

SHA=re.compile(r'^[0-9a-f]{40}$')

def timestamp():return datetime.datetime.now(datetime.timezone.utc).isoformat()

class Broker:
    def __init__(self, config, api, database, health_dir, clock=time.time):
        self.config=config;self.api=api;self.clock=clock;self.health_dir=pathlib.Path(health_dir)
        self.db=sqlite3.connect(database)
        self.db.row_factory=sqlite3.Row
        self.db.executescript('''
          PRAGMA journal_mode=WAL;
          CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY, repo TEXT, sha TEXT, trusted INTEGER, source TEXT,
            state TEXT, attempted TEXT DEFAULT '[]', route TEXT, host TEXT, runtime_sha TEXT,
            nonce TEXT, run_id INTEGER, dispatched REAL, updated REAL, reason TEXT,
            UNIQUE(repo,sha));
          CREATE TABLE IF NOT EXISTS cursors (key TEXT PRIMARY KEY, sha TEXT);
          CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
        ''')
        if 'runtime_sha' not in {r['name'] for r in self.db.execute('PRAGMA table_info(tasks)')}:
            self.db.execute('ALTER TABLE tasks ADD COLUMN runtime_sha TEXT');self.db.commit()

    def log(self, event, **fields):
        print(json.dumps({'at':timestamp(),'event':event,**fields}),flush=True)

    def health(self):
        out={}
        for p in self.health_dir.glob('*.json'):
            try:
                d=json.loads(p.read_text());out[d['runner_name']]=d
            except (ValueError, KeyError, OSError):pass
        return out

    def update(self, task, **values):
        values['updated']=self.clock()
        keys=list(values)
        self.db.execute('UPDATE tasks SET '+','.join(k+'=?' for k in keys)+' WHERE id=?',
                        [values[k] for k in keys]+[task['id']]);self.db.commit()

    def status(self, task, state, description, run_id=None):
        payload={'state':state,'context':'hybrid/ci','description':description[:140]}
        if run_id:payload['target_url']=f'https://github.com/{task["repo"]}/actions/runs/{run_id}'
        self.api.post(f'/repos/{task["repo"]}/statuses/{task["sha"]}',payload)

    def enqueue(self, repo, sha, trusted, source):
        if not SHA.fullmatch(sha):raise ValueError('expected immutable SHA')
        if repo not in self.config['repositories']:raise ValueError('repository not allowlisted')
        ident=uuid.uuid4().hex
        cur=self.db.execute('INSERT OR IGNORE INTO tasks(id,repo,sha,trusted,source,state,updated) VALUES(?,?,?,?,?,?,?)',
                           (ident,repo,sha,int(trusted),source,'pending',self.clock()))
        self.db.commit()
        if cur.rowcount:self.log('enqueued',repo=repo,sha=sha,task=ident,trusted=trusted)
        return self.db.execute('SELECT * FROM tasks WHERE repo=? AND sha=?',(repo,sha)).fetchone()

    def discover(self):
        # Baseline existing refs on first observation; do not run historical production heads.
        for repo, policy in self.config['repositories'].items():
            if not policy.get('enabled'):continue
            observations=[]
            initialized=self.db.execute('SELECT value FROM meta WHERE key=?',('initialized:'+repo,)).fetchone()
            for branch in policy['branches']:
                obj=self.api.get(f'/repos/{repo}/git/ref/heads/{branch}')['object']
                observations.append((f'branch:{branch}',obj['sha'],True))
            for pr in self.api.pages(f'/repos/{repo}/pulls?state=open'):
                if pr['base']['ref'] not in policy['pr_bases']:continue
                full=self.api.get(f'/repos/{repo}/pulls/{pr["number"]}')
                if full.get('draft') or full.get('mergeable') is not True:continue
                sha=full.get('merge_commit_sha')
                if not sha:continue
                trusted=(full['head']['repo'] is not None and full['head']['repo']['full_name']==repo
                    and full['user']['login'] in self.config['trusted_actors'])
                observations.append((f'pr:{pr["number"]}',sha,trusted))
            for source, sha, trusted in observations:
                key=repo+':'+source
                old=self.db.execute('SELECT sha FROM cursors WHERE key=?',(key,)).fetchone()
                if (old and old['sha']!=sha) or (not old and initialized):self.enqueue(repo,sha,trusted,source)
                self.db.execute('INSERT OR REPLACE INTO cursors VALUES(?,?)',(key,sha))
                self.db.commit()
            self.db.execute('INSERT OR REPLACE INTO meta VALUES(?,?)',('initialized:'+repo,'yes'));self.db.commit()

    def finish(self, task, state, reason):
        # Publish first. If it fails, persisted task remains active and retries the same result.
        self.status(task,'success' if state=='success' else 'error' if state=='blocked' else 'failure',
                    reason,task['run_id'])
        self.update(task,state=state,reason=reason)
        self.log('terminal',task=task['id'],repo=task['repo'],state=state,reason=reason)

    def dispatch(self, task):
        policy=self.config['repositories'][task['repo']]
        if not policy.get('enabled'):return
        # Match the reviewed workflow implementation, even if someone moves the tag.
        if not SHA.fullmatch(policy.get('runtime_sha','')):
            return self.finish(task,'blocked','Runtime tag/SHA has not been approved')
        if self.api.ref_sha(task['repo'],policy['runtime_ref'])!=policy['runtime_sha']:
            return self.finish(task,'blocked','Runtime tag drift; dispatch denied')
        attempted=json.loads(task['attempted'])
        if self.db.execute('SELECT value FROM meta WHERE key="hosted_blocked"').fetchone():
            attempted=list(set(attempted+['github-linux']))
        leased=[r['host'] for r in self.db.execute("SELECT host FROM tasks WHERE state IN ('dispatching','active','cancelling')")]
        runners=self.api.pages(f'/repos/{task["repo"]}/actions/runners','runners')
        candidate=choose(probe.effective_config(self),policy,runners,self.health(),attempted,
                         bool(task['trusted']),leased,self.clock())
        if not candidate:
            if self.config['mode'] != 'LOCAL' and 'github-linux' in policy['routes'] and 'github-linux' not in json.loads(task['attempted']):
                if probe.request(self):
                    self.status(task,'pending','Waiting for bounded hosted availability probe')
                    return
            return self.finish(task,'blocked','No verified compatible capacity; no job queued')
        nonce=uuid.uuid4().hex
        self.status(task,'pending',f'{candidate.route}: dispatch planned')
        # Persist intent BEFORE HTTP write. Unknown dispatch outcome is never blindly retried.
        self.update(task,state='dispatching',route=candidate.route,host=candidate.host_id,nonce=nonce,
                    run_id=None,dispatched=self.clock(),runtime_sha=policy['runtime_sha'],attempted=json.dumps(attempted+[candidate.route]))
        self.log('dispatch',task=task['id'],route=candidate.route,nonce=nonce)
        self.api.post(f'/repos/{task["repo"]}/actions/workflows/{policy["workflow"]}/dispatches',
            {'ref':policy['runtime_ref'],'inputs':{'target_sha':task['sha'],
             'runner':candidate.route,'dispatch_id':nonce}})

    def find_run(self, task):
        policy=self.config['repositories'][task['repo']]
        # Exact random run-name correlation; never select by latest run/branch alone.
        runs=self.api.pages(f'/repos/{task["repo"]}/actions/workflows/{policy["workflow"]}/runs?event=workflow_dispatch','workflow_runs')
        matches=[r for r in runs if r.get('display_title')=='hybrid-'+task['nonce']
                 and r['head_sha']==(task['runtime_sha'] or policy['runtime_sha'])]
        if len(matches)>1:raise APIError('duplicate dispatch correlation; operator intervention required')
        return matches[0] if matches else None

    def monitor(self, task):
        run=self.find_run(task) if not task['run_id'] else self.api.get(f'/repos/{task["repo"]}/actions/runs/{task["run_id"]}')
        if not run:
            if self.clock()-task['dispatched']>self.config['queue_timeout']:
                # Unknown may appear late. Do not release lease or dispatch another attempt.
                self.status(task,'error','Dispatch outcome unknown; reconcile manually')
                self.log('unknown_dispatch',task=task['id'])
            return
        if not task['run_id']:
            self.update(task,run_id=run['id'],state='active');task=dict(task);task['run_id']=run['id']
        jobs=self.api.pages(f'/repos/{task["repo"]}/actions/runs/{run["id"]}/jobs','jobs')
        started=any(j.get('runner_id', 0) > 0 or j.get('status') == 'in_progress'
                    or any(s.get('started_at') for s in j.get('steps', [])) for j in jobs)
        if run['status']=='completed':
            if task['state']=='cancelling':
                # Cancellation race: if ANY code might have started, do not retry.
                if run.get('conclusion')!='cancelled' or started:
                    return self.finish(task,'failure','Cancellation raced job start; fallback denied')
                self.update(task,state='pending',host=None,run_id=None)
                self.log('fallback_ready',task=task['id'],previous=task['route']);return
            if run.get('conclusion')=='success':
                if not jobs or any(j.get('conclusion') != 'success' for j in jobs):
                    return self.finish(task,'failure','CI skipped/incomplete; success denied')
                return self.finish(task,'success','CI passed')
            billing=False
            if task['route']=='github-linux' and not started:
                for job in jobs:
                    url=job.get('check_run_url','')
                    check_id=url.rsplit('/',1)[-1]
                    if not check_id.isdigit():continue
                    for note in self.api.pages(f'/repos/{task["repo"]}/check-runs/{check_id}/annotations'):
                        msg=note.get('message','').lower()
                        if ('payments have failed' in msg or 'spending limit' in msg):billing=True
            if billing:
                self.db.execute('INSERT OR REPLACE INTO meta VALUES("hosted_blocked","billing")');self.db.commit()
                self.update(task,state='pending',host=None,run_id=None)
                self.log('billing_blocked',task=task['id']);return
            return self.finish(task,'failure','CI '+str(run.get('conclusion'))+'; no test retry')
        if task['state']=='cancelling':
            if not started:
                self.api.post(f'/repos/{task["repo"]}/actions/runs/{run["id"]}/cancel')
            return
        elapsed=self.clock()-task['dispatched']
        if not started and elapsed>=self.config['queue_timeout']:
            self.update(task,state='cancelling',reason='pre-start queue timeout')
            self.api.post(f'/repos/{task["repo"]}/actions/runs/{run["id"]}/cancel')
            self.log('cancel_requested',task=task['id'],run_id=run['id'])
        elif elapsed>self.config.get('run_timeout',2400):
            # A started run is never retried automatically. Cancellation bounds resource use.
            self.api.post(f'/repos/{task["repo"]}/actions/runs/{run["id"]}/cancel')
            self.log('runtime_cancel_requested',task=task['id'],run_id=run['id'])

    def tick(self):
        probe.tick(self)
        self.discover()
        for task in self.db.execute("SELECT * FROM tasks WHERE state IN ('pending','dispatching','active','cancelling') ORDER BY updated").fetchall():
            try:
                if task['state']=='pending':self.dispatch(task)
                else:self.monitor(task)
            except APIError as e:self.log('api_error',task=task['id'],detail=str(e))
        self.db.execute('INSERT OR REPLACE INTO meta VALUES("heartbeat",?)',(str(self.clock()),));self.db.commit()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True)
    parser.add_argument('--state',required=True);parser.add_argument('--health',required=True)
    parser.add_argument('--once',action='store_true');parser.add_argument('--enqueue',nargs=3,metavar=('REPO','SHA','SOURCE'))
    args=parser.parse_args();path=pathlib.Path(args.state);path.parent.mkdir(parents=True,exist_ok=True)
    # One coordinator owns mutation. Restart retains leases and dispatch intent.
    with open(str(path)+'.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        config=json.loads(pathlib.Path(args.config).read_text())
        broker=Broker(config,GitHub(),str(path),args.health)
        if args.enqueue:
            # Explicit manual canary enqueue is trusted only on allowlisted branch SHA.
            repo,sha,source=args.enqueue
            policy=config['repositories'][repo]
            heads=[broker.api.get(f'/repos/{repo}/git/ref/heads/{b}')['object']['sha'] for b in policy['branches']]
            broker.enqueue(repo,sha,sha in heads,source)
        while True:
            # Mode/settings can change without workflow edits; reload at each bounded cycle.
            broker.config=json.loads(pathlib.Path(args.config).read_text())
            try:broker.tick()
            except APIError as e:broker.log('poll_error',detail=str(e))
            if args.once:break
            time.sleep(config.get('poll_seconds',15))

if __name__=='__main__':main()
