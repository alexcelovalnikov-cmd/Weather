"""On-demand hosted availability probe. Zero repository checkout or secrets in probe job."""
import json
import uuid
from .github import APIError

KEY='hosted_probe'

def effective_config(broker):
    config={**broker.config,'hosted':dict(broker.config.get('hosted',{}))}
    until=broker.db.execute('SELECT value FROM meta WHERE key="hosted_until"').fetchone()
    if not config['hosted'].get('denied') and until and float(until['value'])>broker.clock():
        config['hosted'].update(allowed=True,verified_until=float(until['value']))
    return config

def read(broker):
    row=broker.db.execute('SELECT value FROM meta WHERE key=?',(KEY,)).fetchone()
    return json.loads(row['value']) if row else None

def save(broker,state):
    broker.db.execute('INSERT OR REPLACE INTO meta VALUES(?,?)',(KEY,json.dumps(state)));broker.db.commit()


def request(broker):
    cfg=broker.config.get('hosted',{}).get('probe',{})
    if broker.config.get('hosted',{}).get('denied') or not cfg.get('enabled'):return False
    old=read(broker)
    if old:
        if old['state'] in ('dispatching','active','cancelling'):return True
        if old['state']=='unknown':return False
        if broker.clock()-old['at']<cfg.get('cooldown',900):return False
    repo=cfg['repository'];policy=broker.config['repositories'][repo]
    if not policy.get('runtime_sha') or broker.api.ref_sha(repo,policy['runtime_ref'])!=policy['runtime_sha']:
        return False
    nonce=uuid.uuid4().hex
    state={'state':'dispatching','nonce':nonce,'at':broker.clock(),'run_id':None,
           'repo':repo,'runtime_sha':policy['runtime_sha'],'workflow':cfg['workflow']}
    save(broker,state)
    broker.log('hosted_probe_dispatch',nonce=nonce)
    # Intent persisted before write; an unknown response cannot cause another probe.
    broker.api.post(f'/repos/{repo}/actions/workflows/{cfg["workflow"]}/dispatches',
                   {'ref':policy['runtime_ref'],'inputs':{'dispatch_id':nonce}})
    return True


def tick(broker):
    state=read(broker)
    if not state or state['state'] not in ('dispatching','active','cancelling'):return
    repo=state['repo'];cfg=broker.config.get('hosted',{}).get('probe',{})
    if not state['run_id']:
        matches=[r for r in broker.api.pages(f'/repos/{repo}/actions/workflows/{state["workflow"]}/runs?event=workflow_dispatch','workflow_runs')
                 if r.get('display_title')=='hybrid-probe-'+state['nonce'] and r['head_sha']==state['runtime_sha']]
        if len(matches)>1:raise APIError('duplicate hosted probe; manual reconciliation required')
        if not matches:
            if broker.clock()-state['at']>broker.config['queue_timeout']:
                state['state']='unknown';save(broker,state);broker.log('hosted_probe_unknown',nonce=state['nonce'])
            return
        run=matches[0];state.update(run_id=run['id'],state='active');save(broker,state)
    else:run=broker.api.get(f'/repos/{repo}/actions/runs/{state["run_id"]}')
    if run['status']=='completed':
        jobs=broker.api.pages(f'/repos/{repo}/actions/runs/{run["id"]}/jobs','jobs')
        success=(run.get('conclusion')=='success' and bool(jobs) and all(j.get('conclusion')=='success' for j in jobs))
        state.update(state='success' if success else 'failed',at=broker.clock());save(broker,state)
        if success:
            ttl=max(60,min(3600,cfg.get('ttl',900)))
            broker.db.execute('INSERT OR REPLACE INTO meta VALUES("hosted_until",?)',(str(broker.clock()+ttl),))
            broker.db.execute('DELETE FROM meta WHERE key="hosted_blocked"')
        else:
            broker.db.execute('DELETE FROM meta WHERE key="hosted_until"')
            broker.db.execute('INSERT OR REPLACE INTO meta VALUES("hosted_blocked","probe failed")')
        broker.db.commit();broker.log('hosted_probe_result',success=success,run_id=run['id']);return
    if broker.clock()-state['at']>broker.config['queue_timeout']:
        state['state']='cancelling';save(broker,state)
        broker.api.post(f'/repos/{repo}/actions/runs/{run["id"]}/cancel')
