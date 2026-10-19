import json,tempfile,unittest
from pathlib import Path
from dashboard.artifacts import EVENT_KEYS,EVENT_SCHEMA,build_status,canonical_hash,legacy_families,legacy_rows,load_events,read_json_detail,resolve_event_artifact,resolve_families,status_projection,write_status
from dashboard.view_models import hypothesis_cards,status_view

class Tests(unittest.TestCase):
 def test_status_model_keeps_implementation_separate_from_evidence(self):
  status=build_status('.');model=status_view(status)
  self.assertEqual('COMPLETE_IMPLEMENTATION_NOT_RUN',model['m3b']);self.assertEqual('NOT RUN',model['events']);self.assertEqual('NOT COMPUTED',model['outcomes']);self.assertEqual('UNKNOWN',model['edge'])
  cards=hypothesis_cards(status);self.assertEqual('BLOCKED_NO_CALENDAR_DATA',cards[2]['status']);self.assertEqual('UNKNOWN',cards[0]['evidence'])
 def test_paths_missing_and_malformed_fail_closed(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);p=root/'data/research/alpha/latest';p.mkdir(parents=True);(p/'families.json').write_text('{}')
   self.assertEqual('RESOLVED',resolve_families(root)['status']);self.assertEqual('UNAVAILABLE',resolve_families(root/'none')['status']);self.assertEqual('NOT_RUN',resolve_event_artifact(root)['status'])
   bad=root/'bad.json';bad.write_text('{');self.assertEqual('MALFORMED',read_json_detail(bad)['status']);self.assertEqual('MALFORMED',legacy_families(bad)['status'])
 def test_legacy_adapter_and_deterministic_status(self):
  valid={'F':{'family_id':'F','metrics':{'n':12,'net_expectancy_r':-0.1},'dataset':{},'status':'REJECTED'}}
  with tempfile.TemporaryDirectory() as d:
   p=Path(d,'families.json');p.write_text(json.dumps(valid));data=legacy_families(p);self.assertEqual('VALID',data['status']);self.assertEqual(12,legacy_rows(data['families'])[0]['sample_size'])
   one=build_status('.');self.assertEqual(canonical_hash(status_projection(one)),canonical_hash(status_projection(dict(reversed(list(one.items()))))))
   self.assertTrue(write_status('.',Path(d,'status.json'),test_status={'suite':'pytest verified'})['analytical_hash'])
 def test_bounded_events_and_outcome_fields_are_rejected(self):
  event={key:None for key in EVENT_KEYS};event.update({'schema_version':EVENT_SCHEMA,'hypothesis_id':'G3_H01_COHERENT_REPRICING_V2','event_id':'e','event_at_utc':'2026-01-01T00:00:00Z','available_at_utc':'2026-01-01T00:00:00Z','direction':'LONG','dataset_role':'DISCOVERY','lineage':{},'frozen_hashes':{},'feature_values':{},'quality_flags':[]})
  with tempfile.TemporaryDirectory() as d:
   p=Path(d,'events.json');p.write_text(json.dumps([event]));self.assertEqual('VALID',load_events(p)['status'])
   event['feature_values']={'forward_return':1};p.write_text(json.dumps([event]));self.assertEqual('UNSUPPORTED',load_events(p)['status'])
 def test_launcher_and_engine_safety_contracts(self):
  root=Path(__file__).parents[1];launcher=(root/'Start_Varrior_Dashboard.bat').read_text();engine='\n'.join(path.read_text(errors='ignore') for path in (root/'engine').rglob('*.py'))
  self.assertIn('--server.port %DASHBOARD_PORT%',launcher);self.assertNotIn('order_send',engine)
