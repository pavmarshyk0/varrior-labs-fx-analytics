from datetime import UTC, datetime
from enum import Enum
class LockedOutcomeAccessError(PermissionError): pass
class InvalidDatasetRoleTransition(ValueError): pass
class RetroactiveForwardHoldout(ValueError): pass
class InvalidTemporalBoundary(ValueError): pass
class DatasetRole(str,Enum):
 DISCOVERY='DISCOVERY'; CONFIRMATION='CONFIRMATION'; LEGACY_LOCKED_NOT_PRISTINE_GEN3='LEGACY_LOCKED_NOT_PRISTINE_GEN3'; FORWARD_LOCKED_HOLDOUT='FORWARD_LOCKED_HOLDOUT'
def _utc(x):
 if x.tzinfo is None or x.utcoffset() is None or x.utcoffset().total_seconds()!=0: raise InvalidTemporalBoundary('UTC-aware timestamp required')
 return x
def require_outcome_access(role):
 if role not in (DatasetRole.DISCOVERY,DatasetRole.CONFIRMATION): raise LockedOutcomeAccessError(role.value)
def role_for(timestamp,*,freeze=None,forward_start=None):
 _utc(timestamp)
 if timestamp<datetime(2025,8,1,tzinfo=UTC): return DatasetRole.DISCOVERY
 if timestamp<datetime(2026,2,1,tzinfo=UTC): return DatasetRole.CONFIRMATION
 if forward_start is not None:
  _utc(forward_start)
  if freeze is None: raise InvalidDatasetRoleTransition('forward holdout requires freeze')
  _utc(freeze)
  if forward_start<freeze: raise RetroactiveForwardHoldout('forward start predates freeze')
  if timestamp>=forward_start:return DatasetRole.FORWARD_LOCKED_HOLDOUT
 return DatasetRole.LEGACY_LOCKED_NOT_PRISTINE_GEN3
