import json
import unittest
from pathlib import Path

class Gen2DiagnosticsTests(unittest.TestCase):
    def test_failure_analysis_schema_is_honest_when_present(self):
        path=Path('data/research/alpha_gen2/latest/failure_analysis.json')
        if not path.exists(): self.skipTest('diagnostics artifact not built')
        data=json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual(data['final_holdout_status'],'LOCKED')
        self.assertIn('families',data)
        for family in data['families'].values():
            self.assertIn('outcome_geometry',family)
            self.assertIn('by_direction',family)

if __name__=='__main__': unittest.main()
