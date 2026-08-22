import unittest
from datetime import UTC,datetime,timezone,timedelta
from engine.gen3.contracts import *
class T(unittest.TestCase):
 def test_roles_and_lock(self):
  self.assertEqual(len(DatasetRole),4)
  for r in (DatasetRole.DISCOVERY,DatasetRole.CONFIRMATION): require_outcome_access(r)
  for r in (DatasetRole.LEGACY_LOCKED_NOT_PRISTINE_GEN3,DatasetRole.FORWARD_LOCKED_HOLDOUT):
   with self.assertRaises(LockedOutcomeAccessError): require_outcome_access(r)
 def test_boundaries(self):
  t=datetime(2026,2,2,tzinfo=UTC)
  with self.assertRaises(InvalidDatasetRoleTransition): role_for(t,forward_start=t)
  with self.assertRaises(RetroactiveForwardHoldout): role_for(t,freeze=t,forward_start=datetime(2026,2,1,tzinfo=UTC))
  with self.assertRaises(InvalidTemporalBoundary): role_for(datetime(2026,2,2))
  with self.assertRaises(InvalidTemporalBoundary): role_for(datetime(2026,2,2,tzinfo=timezone.utc).astimezone(timezone.utc)) if False else role_for(datetime(2026,2,2,tzinfo=timezone(timedelta(hours=1))))
