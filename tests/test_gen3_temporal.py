import json, tempfile, unittest
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from engine.gen3.temporal import EventTimeHazardContext, InvalidTemporalContext, TemporalConfigError, config_hash, load_temporal_config
CONFIG=Path('config/gen3/temporal_context_v1.json')
class Hostile(dict):
 def __getitem__(self,key):
  if key!='timestamp_utc': raise AssertionError(key)
  return super().__getitem__(key)
class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(c): c.config=load_temporal_config(CONFIG)
 def ctx(self,x): return EventTimeHazardContext(self.config).context(x)
 def test_utc_determinism_and_hostile(self):
  x=datetime(2025,1,2,8,tzinfo=UTC); self.assertEqual(self.ctx(x),self.ctx(x)); self.assertEqual(self.ctx(x),EventTimeHazardContext(self.config).context_from_row(Hostile(timestamp_utc=x,bid=1,outcome=2),dataset_role='LOCKED'))
  for bad in (datetime(2025,1,2,8),datetime(2025,1,2,9,tzinfo=timezone(timedelta(hours=1)))):
   with self.assertRaises(InvalidTemporalContext): self.ctx(bad)
 def test_dst_boundaries_and_dates(self):
  self.assertTrue(self.ctx(datetime(2025,1,2,8,tzinfo=UTC))['active_windows']['london_open']); self.assertTrue(self.ctx(datetime(2025,7,2,7,tzinfo=UTC))['active_windows']['london_open'])
  self.assertEqual('US_DST_EU_STANDARD_MISMATCH',self.ctx(datetime(2024,3,15,12,tzinfo=UTC))['dst_relationship']); self.assertEqual('US_DST_EU_STANDARD_MISMATCH',self.ctx(datetime(2024,10,28,12,tzinfo=UTC))['dst_relationship'])
  self.assertFalse(self.ctx(datetime(2025,1,2,6,59,tzinfo=UTC))['active_windows']['london_open']); self.assertTrue(self.ctx(datetime(2024,2,29,8,tzinfo=UTC))['timestamp_utc'].endswith('Z'))
 def test_fix_rollover_and_hash(self):
  self.assertTrue(self.ctx(datetime(2025,7,2,14,55,tzinfo=UTC))['active_windows']['london_fix_proxy']); self.assertFalse(self.ctx(datetime(2025,7,2,15,5,tzinfo=UTC))['active_windows']['london_fix_proxy'])
  self.assertTrue(self.ctx(datetime(2025,1,2,22,tzinfo=UTC))['active_windows']['fx_rollover']); self.assertEqual(self.config['config_hash'],config_hash(dict(reversed(list(self.config.items())))))
  with tempfile.TemporaryDirectory() as d:
   bad=dict(self.config); bad['calendar']=dict(bad['calendar'],max_age_hours=1); p=Path(d,'x.json');p.write_text(json.dumps(bad))
   with self.assertRaises(TemporalConfigError): load_temporal_config(p)
