import json
import unittest
from pathlib import Path

class DashboardArtifactTests(unittest.TestCase):
    def test_alpha_summary_contract_is_loadable_when_available(self):
        path = Path('data/research/alpha/latest/families.json')
        if not path.exists(): self.skipTest('alpha benchmark artifacts not built')
        data = json.loads(path.read_text(encoding='utf-8'))
        self.assertTrue(data)
        for item in data.values():
            self.assertIn('dataset', item); self.assertIn('metrics', item); self.assertEqual(item['final_holdout_status'], 'LOCKED')

if __name__ == '__main__': unittest.main()
