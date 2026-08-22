import json, tempfile, unittest
from pathlib import Path
from engine.gen3.registry import load_registry
V1=Path('config/gen3/tier_a_v1.json'); V2=Path('config/gen3/tier_a_v2.json')
class RegistryV2Tests(unittest.TestCase):
 def write(self,payload):
  d=tempfile.TemporaryDirectory(); p=Path(d.name,'x.json');p.write_text(json.dumps(payload));self.addCleanup(d.cleanup);return p
 def test_v1_unchanged_and_v2_executable(self):
  one=load_registry(V1); two=load_registry(V2)
  self.assertEqual('HISTORICAL_NON_EXECUTABLE',one['execution_status']); self.assertEqual({'G3_H01_COHERENT_REPRICING_V2','G3_H02_BREAK_STATE_V2','G3_H03_MACRO_HAZARD_V1'},{x['hypothesis_id'] for x in two['hypotheses']})
  self.assertEqual('b5e0a60fc147ab8e2cb58abf95caf29d4abb216a42fdabac1d0551240aafb236',next(x for x in two['hypotheses'] if x['hypothesis_id'].startswith('G3_H03'))['feature_definition_hash'])
 def test_executable_omissions_and_hash_mutation_fail(self):
  original=json.loads(V2.read_text())
  for field in ('midpoint_formula','trigger','baseline','refractory','controls','falsification'):
   payload=json.loads(json.dumps(original)); payload['hypotheses'][0]['executable_definition'].pop(field)
   with self.subTest(field=field),self.assertRaises(ValueError): load_registry(self.write(payload))
  payload=json.loads(json.dumps(original)); payload['hypotheses'][1]['executable_definition']['break']['penetration']='changed'
  with self.assertRaises(ValueError): load_registry(self.write(payload))
 def test_round_trip_and_no_outcomes(self):
  payload=json.loads(V2.read_text()); self.assertEqual(load_registry(V2)['hypotheses'][0]['config_hash'],load_registry(self.write(dict(reversed(list(payload.items())))))['hypotheses'][0]['config_hash'])
  executable=[row for row in payload['hypotheses'] if row['hypothesis_id'].endswith('_V2')]
  self.assertFalse(any(word in json.dumps(executable).lower() for word in {'outcome','mfe','mae','expectancy','winner','optimized','best'}))
if __name__=='__main__': unittest.main()
