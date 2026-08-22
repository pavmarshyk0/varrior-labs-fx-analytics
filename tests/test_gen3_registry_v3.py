import json, tempfile, unittest
from pathlib import Path
from engine.gen3.registry import load_registry
V2=Path('config/gen3/tier_a_v2.json');V3=Path('config/gen3/tier_a_v3.json')
class Tests(unittest.TestCase):
 def write(self,x):
  d=tempfile.TemporaryDirectory();p=Path(d.name,'x.json');p.write_text(json.dumps(x));self.addCleanup(d.cleanup);return p
 def test_actual_v2_defect_and_active_v3(self):
  v2=json.loads(V2.read_text()); h02=v2['hypotheses'][1]['executable_definition']
  self.assertIn('V_tau',h02['break']['penetration']);self.assertIn('spread_at_break',h02['break']['penetration'])
  v3=load_registry(V3);self.assertEqual(['G3_H01_COHERENT_REPRICING_V2','G3_H02_BREAK_STATE_V3','G3_H03_MACRO_HAZARD_V1'],v3['active_execution_set'])
  self.assertEqual('SUPERSEDED_PRE_RUN_DIMENSIONAL_DEFECT',v3['supersession_records'][0]['status'])
 def test_v3_units_and_semantics(self):
  h=load_registry(V3)['hypotheses'][1]['executable_definition'];self.assertEqual('LOG_RETURN',h['units']['volatility_scale']);self.assertEqual('LOG_RETURN',h['units']['log_spread']);self.assertEqual(61,h['volatility_scale']['closes']);self.assertEqual(60,h['volatility_scale']['returns']);self.assertTrue(h['rejection']['return_excluded']);self.assertIn('max(0.10*V_tau,1.0*g_tau)',h['break']['threshold'])
 def test_mutation_and_invalid_units_fail(self):
  x=json.loads(V3.read_text());x['hypotheses'][1]['executable_definition']['break']['threshold']='max(0.10*V_tau,raw_spread)'
  with self.assertRaises(ValueError):load_registry(self.write(x))
  x=json.loads(V3.read_text());x['hypotheses'][1]['executable_definition']['inside_buffer']='changed'
  with self.assertRaises(ValueError):load_registry(self.write(x))
if __name__=='__main__':unittest.main()
