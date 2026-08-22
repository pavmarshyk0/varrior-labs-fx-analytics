import json,unittest
from pathlib import Path
from engine.gen3.registry import load_registry,canonical_hash
P=Path('config/gen3/tier_a_v1.json')
class T(unittest.TestCase):
 def test_frozen(self):
  p=load_registry(P); self.assertEqual(p['schema_version'],'gen3-tier-a/v1'); self.assertEqual(len(p['hypotheses']),3)
 def test_order(self): self.assertEqual(canonical_hash({'a':1,'b':2}),canonical_hash({'b':2,'a':1}))
 def test_mutation(self):
  p=json.loads(P.read_text());p['hypotheses'][0]['status']='X';q=Path('config/gen3/_tmp.json');q.write_text(json.dumps(p))
  try:
   with self.assertRaises(ValueError):load_registry(q)
  finally:q.unlink()
