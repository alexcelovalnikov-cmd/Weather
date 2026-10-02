import json
import unittest
from hybrid import probe
from hybrid.github import APIError
import test_hybrid as fixture
from test_hybrid import REPO, RUNTIME

class ProbeTests(unittest.TestCase):
 task=fixture.BrokerTests.task
 tearDown=fixture.BrokerTests.tearDown
 # Reuse fixture only, rather than inheriting the broker test cases.
 def setUp(self):
  fixture.BrokerTests.setUp(self)
  self.c['hosted'].update(allowed=False,verified_until=0,probe={'enabled':True,'repository':REPO,
    'workflow':'hybrid-hosted-probe.yml','ttl':900,'cooldown':900})
  self.api.runners=[]
 def test_probe_on_demand_then_success_dispatches_workload(self):
  self.b.dispatch(self.task());self.assertEqual(self.task()['state'],'pending')
  p=probe.read(self.b);self.assertEqual(p['state'],'dispatching')
  self.api.runs=[{'id':20,'display_title':'hybrid-probe-'+p['nonce'],'head_sha':RUNTIME,
                 'status':'completed','conclusion':'success'}]
  self.api.jobs=[{'conclusion':'success'}];probe.tick(self.b)
  self.assertTrue(probe.effective_config(self.b)['hosted']['allowed'])
  self.b.dispatch(self.task());self.assertEqual(self.task()['route'],'github-linux')
 def test_probe_failure_cooldown_no_workload(self):
  self.b.dispatch(self.task());p=probe.read(self.b)
  self.api.runs=[{'id':20,'display_title':'hybrid-probe-'+p['nonce'],'head_sha':RUNTIME,'status':'completed','conclusion':'failure'}]
  probe.tick(self.b);self.b.dispatch(self.task())
  self.assertEqual(self.task()['state'],'blocked')
  self.assertEqual(sum(path.endswith('/dispatches') for path,_ in self.api.writes),1)
 def test_local_never_probes(self):
  self.c['mode']='LOCAL';self.b.dispatch(self.task());self.assertIsNone(probe.read(self.b))
 def test_operator_denied_never_probes(self):
  self.c['hosted']['denied']=True;self.b.dispatch(self.task());self.assertIsNone(probe.read(self.b))
 def test_lost_probe_response_no_duplicate(self):
  self.api.unknown=True
  with self.assertRaises(APIError):self.b.dispatch(self.task())
  self.api.unknown=False;self.b.dispatch(self.task())
  self.assertEqual(sum(path.endswith('/dispatches') for path,_ in self.api.writes),1)
  self.now+=121;probe.tick(self.b);self.assertEqual(probe.read(self.b)['state'],'unknown')
  self.assertFalse(probe.request(self.b))
 def test_queued_probe_cancel(self):
  self.b.dispatch(self.task());p=probe.read(self.b)
  self.api.runs=[{'id':20,'display_title':'hybrid-probe-'+p['nonce'],'head_sha':RUNTIME,'status':'queued'}]
  self.now+=121;probe.tick(self.b);self.assertEqual(probe.read(self.b)['state'],'cancelling')
  self.assertTrue(any(path.endswith('/cancel') for path,_ in self.api.writes))
 def test_probe_skipped_success_denied(self):
  self.b.dispatch(self.task());p=probe.read(self.b)
  self.api.runs=[{'id':20,'display_title':'hybrid-probe-'+p['nonce'],'head_sha':RUNTIME,'status':'completed','conclusion':'success'}]
  self.api.jobs=[];probe.tick(self.b);self.assertEqual(probe.read(self.b)['state'],'failed')

