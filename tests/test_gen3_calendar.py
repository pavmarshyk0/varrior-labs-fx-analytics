import unittest
from datetime import UTC, datetime
from engine.gen3.calendar import CalendarAvailabilityError, CalendarError, EconomicCalendarAdapter
def payload(events=(),generated='2025-01-01T00:00:00Z'): return {'schema_version':'gen3-economic-calendar/v1','calendar_version':'v1','generated_at_utc':generated,'events':list(events)}
def event(id='e',at='2025-01-01T12:00:00Z',known='2025-01-01T00:00:00Z',**x): return {'event_id':id,'scheduled_at_utc':at,'event_type':'SCHEDULED_MACRO','currency':'USD','importance':'HIGH','source':'synthetic','source_event_id':id,'known_at_utc':known,'calendar_version':'v1',**x}
class Tests(unittest.TestCase):
 def test_empty_and_hazard(self):
  self.assertEqual('NO_SCHEDULED_EVENT_HAZARD',EconomicCalendarAdapter.from_payload(payload()).context(datetime(2025,1,1,1,tzinfo=UTC),max_age_hours=48,buckets_minutes=[] )['macro_hazard_state'])
  c=EconomicCalendarAdapter.from_payload(payload([event('before','2025-01-01T11:59:00Z'),event('after','2025-01-01T12:01:00Z')]))
  r=c.context(datetime(2025,1,1,12,tzinfo=UTC),max_age_hours=48,buckets_minutes=[[-5,0],[0,5]])
  self.assertEqual('before',r['previous_scheduled_event']['event_id']);self.assertEqual('after',r['next_scheduled_event']['event_id']);self.assertEqual('SCHEDULED_EVENT_HAZARD',r['macro_hazard_state'])
 def test_fail_closed_and_deterministic(self):
  for x in (payload([event(),event()]),dict(payload(),schema_version='no'),payload([event(importance='NO')])):
   with self.assertRaises(CalendarError): EconomicCalendarAdapter.from_payload(x)
  future=EconomicCalendarAdapter.from_payload(payload([event(at='2025-01-02T12:00:00Z',known='2025-01-02T00:00:00Z')]))
  self.assertIsNone(future.context(datetime(2025,1,1,12,tzinfo=UTC),max_age_hours=48,buckets_minutes=[])['next_scheduled_event'])
  stale=EconomicCalendarAdapter.from_payload(payload(generated='2024-12-01T00:00:00Z'))
  with self.assertRaises(CalendarAvailabilityError): stale.context(datetime(2025,1,1,12,tzinfo=UTC),max_age_hours=48,buckets_minutes=[])
