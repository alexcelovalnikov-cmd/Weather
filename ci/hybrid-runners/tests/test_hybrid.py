import contextlib
import io
import json
import pathlib
import tempfile
import unittest
from hybrid.router import choose, LABELS
from hybrid.broker import Broker
from hybrid.github import APIError

SHA='a'*40
RUNTIME='b'*40
REPO='alexcelovalnikov-cmd/Weather'

def config():
 return {'mode':'AUTO','health_ttl':90,'queue_timeout':120,'run_timeout':2400,
  'trusted_actors':['alexcelovalnikov-cmd'],'hosted':{'allowed':True,'verified_until':2000},
  'repositories':{REPO:{'enabled':True,'workflow':'hybrid-ci.yml','runtime_ref':'hybrid-runtime-v1',
   'runtime_sha':RUNTIME,'branches':[],'pr_bases':[],
   'routes':['local-mac','local-linux','github-linux'],'capabilities':['node24'],
   'runner_names':{'local-mac':['hybrid-weather-mac'],'local-linux':['hybrid-weather-linux']}}}}

def runner(route,ident=1):
 return {'id':ident,'name':'hybrid-weather-'+('mac' if route=='local-mac' else 'linux'),
  'status':'online','busy':False,'labels':[{'name':x} for x in LABELS[route]+['hybrid-weather-'+('mac' if route=='local-mac' else 'linux')]]}

def health(route,now=1000):
 name=runner(route)['name']
 return {name:{'observed_at':now,'healthy':True,'host_id':route+'-host','capabilities':['node24']}}

class API:
 def __init__(self):
  self.writes=[];self.runners=[runner('local-mac')];self.runs=[];self.jobs=[];self.annotations=[]
  self.run=None;self.unknown=False;self.tag_sha=RUNTIME;self.cancel_error=False
 def ref_sha(self,*args):return self.tag_sha
 def post(self,path,data=None):
  self.writes.append((path,data))
  if path.endswith('/dispatches') and self.unknown:raise APIError('unknown outcome')
  if path.endswith('/cancel') and self.cancel_error:raise APIError('cancel API temporarily down')
 def get(self,path):return self.run
 def pages(self,path,key=None):
  if '/runners' in path:return self.runners
  if '/annotations' in path:return self.annotations
  if '/jobs' in path:return self.jobs
  if '/runs?' in path:return self.runs
  if '/pulls' in path:return []
  raise AssertionError(path)

class RouteTests(unittest.TestCase):
 def setUp(self):self.c=config();self.p=self.c['repositories'][REPO]
 def pick(self,rs=None,hs=None,**kwargs):
  return choose(self.c,self.p,rs or [],hs or {},now=1000,**kwargs)
 def test_mac_then_linux_then_hosted(self):
  rs=[runner('local-mac'),runner('local-linux',2)];hs={**health('local-mac'),**health('local-linux')}
  self.assertEqual(self.pick(rs,hs).route,'local-mac')
  rs[0]['status']='offline';self.assertEqual(self.pick(rs,hs).route,'local-linux')
  rs[1]['busy']=True;self.assertEqual(self.pick(rs,hs).route,'github-linux')
 def test_unknown_and_expired_hosted_denied(self):
  self.c['hosted']={};self.assertIsNone(self.pick())
  self.c['hosted']={'allowed':True,'verified_until':900};self.assertIsNone(self.pick())
 def test_local_never_spends_hosted(self):
  self.c['mode']='LOCAL';self.assertIsNone(self.pick())
 def test_github_never_uses_local(self):
  self.c['mode']='GITHUB';self.assertEqual(self.pick([runner('local-mac')],health('local-mac')).route,'github-linux')
 def test_docker_never_mac(self):
  self.p['routes']=['local-linux','github-linux'];self.p['capabilities']=['docker-rootless']
  self.c['mode']='LOCAL';self.assertIsNone(self.pick([runner('local-mac')],health('local-mac')))
 def test_untrusted_only_hosted(self):
  self.assertEqual(self.pick([runner('local-mac')],health('local-mac'),trusted=False).route,'github-linux')
 def test_stale_health_and_lease(self):
  self.c['mode']='LOCAL'
  self.assertIsNone(self.pick([runner('local-mac')],health('local-mac',800)))
  self.assertIsNone(self.pick([runner('local-mac')],health('local-mac'),leased=['local-mac-host']))
 def test_wrong_labels_or_unknown_names(self):
  self.c['mode']='LOCAL';r=runner('local-mac');r['labels']=[]
  self.assertIsNone(self.pick([r],health('local-mac')))
  r=runner('local-mac');r['name']='rogue';self.assertIsNone(self.pick([r],health('local-mac')))
 def test_no_same_route_retry(self):
  self.assertEqual(self.pick([runner('local-mac')],health('local-mac'),attempted=['local-mac']).route,'github-linux')
 def test_bad_mode(self):
  self.c['mode']='TYPO'
  with self.assertRaises(ValueError):self.pick()

class BrokerTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.temp.name);self.api=API();self.now=1000
  self.c=config();self.b=Broker(self.c,self.api,str(self.root/'state.sqlite'),str(self.root),lambda:self.now)
  (self.root/'mac.json').write_text(json.dumps({'runner_name':'hybrid-weather-mac',**health('local-mac')['hybrid-weather-mac']}))
  self.t=self.b.enqueue(REPO,SHA,True,'canary')
 def tearDown(self):self.b.db.close();self.temp.cleanup()
 def task(self):return self.b.db.execute('SELECT * FROM tasks WHERE id=?',(self.t['id'],)).fetchone()
 def dispatch(self):
  self.b.dispatch(self.task());t=self.task()
  self.api.run={'id':10,'status':'queued','head_sha':RUNTIME,'display_title':'hybrid-'+t['nonce']}
  self.api.runs=[self.api.run];return t
 def test_idempotent_enqueue(self):
  self.b.enqueue(REPO,SHA,True,'branch:main');self.assertEqual(self.b.db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0],1)
 def test_runtime_drift(self):
  self.api.tag_sha='c'*40;self.b.dispatch(self.task());self.assertEqual(self.task()['state'],'blocked')
  self.assertFalse(any(p.endswith('/dispatches') for p,_ in self.api.writes))
 def test_queue_cancel_confirm_then_fallback(self):
  self.dispatch();self.now+=121;self.b.monitor(self.task());self.assertEqual(self.task()['state'],'cancelling')
  self.b.monitor(self.task());self.assertEqual(self.task()['state'],'cancelling')
  self.api.run.update(status='completed',conclusion='cancelled');self.b.monitor(self.task())
  self.assertEqual(self.task()['state'],'pending');self.b.dispatch(self.task())
  self.assertEqual(self.task()['route'],'github-linux')
 def test_cancel_write_failure_reconciled(self):
  self.dispatch();self.now+=121;self.api.cancel_error=True
  with self.assertRaises(APIError):self.b.monitor(self.task())
  self.api.cancel_error=False;self.b.monitor(self.task())
  self.assertEqual(self.task()['state'],'cancelling');self.assertEqual(sum(p.endswith('/cancel') for p,_ in self.api.writes),2)
 def test_cancel_race_never_retries(self):
  self.dispatch();self.now+=121;self.b.monitor(self.task())
  self.api.jobs=[{'runner_id':11,'steps':[]}];self.api.run.update(status='completed',conclusion='cancelled')
  self.b.monitor(self.task());self.assertEqual(self.task()['state'],'failure')
 def test_test_failure_never_retries(self):
  self.dispatch();self.api.run.update(status='completed',conclusion='failure')
  self.api.jobs=[{'runner_id':11,'status':'completed','steps':[{'started_at':'time'}]}]
  self.b.monitor(self.task());self.assertEqual(self.task()['state'],'failure')
 def test_billing_timestamp_without_runner_falls_back(self):
  self.api.runners=[];self.b.dispatch(self.task());self.assertEqual(self.task()['route'],'github-linux')
  t=self.task();self.api.runs=[{'id':10,'status':'completed','conclusion':'failure','head_sha':RUNTIME,'display_title':'hybrid-'+t['nonce']}]
  self.api.jobs=[{'runner_id':0,'status':'completed','started_at':'fake','steps':[], 'check_run_url':'https://api.github.com/repos/x/check-runs/7'}]
  self.api.annotations=[{'message':'The job was not started because recent account payments have failed'}]
  self.b.monitor(self.task());self.assertEqual(self.task()['state'],'pending')
  self.api.runners=[runner('local-mac')]
  self.b.dispatch(self.task());self.assertEqual(self.task()['route'],'local-mac')
  self.assertIsNotNone(self.b.db.execute('SELECT * FROM meta WHERE key="hosted_blocked"').fetchone())
 def test_unknown_dispatch_no_duplicate_even_after_restart(self):
  self.api.unknown=True
  with self.assertRaises(APIError):self.b.dispatch(self.task())
  self.b.db.close();self.b=Broker(self.c,self.api,str(self.root/'state.sqlite'),str(self.root),lambda:self.now)
  self.now+=200;self.b.monitor(self.task());self.assertEqual(self.task()['state'],'dispatching')
  self.assertEqual(sum(p.endswith('/dispatches') for p,_ in self.api.writes),1)
 def test_exact_correlation_ignores_unrelated_run(self):
  self.dispatch();self.api.runs[0]['display_title']='hybrid-unrelated';self.assertIsNone(self.b.find_run(self.task()))
 def test_busy_host_serialized_across_tasks(self):
  self.dispatch();other=self.b.enqueue(REPO,'d'*40,True,'other')
  self.b.dispatch(other);other=self.b.db.execute('SELECT * FROM tasks WHERE id=?',(other['id'],)).fetchone()
  self.assertEqual(other['route'],'github-linux')
 def test_success_requires_actual_jobs(self):
  self.dispatch();self.api.run.update(status='completed',conclusion='success');self.b.monitor(self.task())
  self.assertEqual(self.task()['state'],'failure')
 def test_real_success_and_canonical_status(self):
  self.dispatch();self.api.run.update(status='completed',conclusion='success')
  self.api.jobs=[{'runner_id':11,'status':'completed','conclusion':'success','steps':[{'started_at':'time'}]}]
  self.b.monitor(self.task());self.assertEqual(self.task()['state'],'success')
  self.assertEqual(self.api.writes[-1][1]['context'],'hybrid/ci')
  self.assertIn('/statuses/'+SHA,self.api.writes[-1][0])
 def test_no_capacity_fails_without_dispatch(self):
  self.c['mode']='LOCAL';self.api.runners=[];self.b.dispatch(self.task())
  self.assertEqual(self.task()['state'],'blocked');self.assertFalse(any(p.endswith('/dispatches') for p,_ in self.api.writes))
 def test_new_pr_after_baseline_is_enqueued_untrusted(self):
  self.c['repositories'][REPO]['pr_bases']=['main']
  self.b.discover()
  pr={'number':5,'base':{'ref':'main'},'draft':False,'mergeable':True,
      'merge_commit_sha':'e'*40,'head':{'repo':{'full_name':'someone/fork'}},'user':{'login':'someone'}}
  orig=self.api.pages
  self.api.pages=lambda path,key=None: [pr] if '/pulls' in path else orig(path,key)
  self.api.get=lambda path: pr
  self.b.discover()
  t=self.b.db.execute('SELECT * FROM tasks WHERE sha=?',('e'*40,)).fetchone()
  self.assertEqual(t['trusted'],0)
 def test_initial_pr_is_baselined_without_dispatch(self):
  self.c['repositories'][REPO]['pr_bases']=['main']
  pr={'number':5,'base':{'ref':'main'},'draft':False,'mergeable':True,
      'merge_commit_sha':'e'*40,'head':{'repo':{'full_name':REPO}},'user':{'login':'alexcelovalnikov-cmd'}}
  orig=self.api.pages
  self.api.pages=lambda path,key=None: [pr] if '/pulls' in path else orig(path,key)
  self.api.get=lambda path: pr
  self.b.discover();self.assertEqual(self.b.db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0],1)
 def test_hosted_probe_proof_expires(self):
  from hybrid import probe
  self.b.db.execute('INSERT INTO meta VALUES("hosted_until","1001")');self.b.db.commit()
  self.c['hosted']={'allowed':False,'verified_until':0}
  self.assertTrue(probe.effective_config(self.b)['hosted']['allowed'])
  self.now=1002;self.assertFalse(probe.effective_config(self.b)['hosted']['allowed'])
 def test_read_only_baseline_no_backfill(self):
  self.b.discover();self.assertFalse(self.api.writes)

if __name__=='__main__':unittest.main()
