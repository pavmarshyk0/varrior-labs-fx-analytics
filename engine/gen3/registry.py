"""Fail-closed loaders for immutable Tier-A preregistrations."""
import hashlib
import json
from pathlib import Path

V1_IDS = {"G3_H01_COHERENT_REPRICING_V1", "G3_H02_BREAK_STATE_V1", "G3_H03_MACRO_HAZARD_V1"}
V2_IDS = {"G3_H01_COHERENT_REPRICING_V2", "G3_H02_BREAK_STATE_V2", "G3_H03_MACRO_HAZARD_V1"}
V3_IDS = {"G3_H01_COHERENT_REPRICING_V2", "G3_H02_BREAK_STATE_V3", "G3_H03_MACRO_HAZARD_V1"}

def canonical_json(value): return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
def canonical_hash(value): return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
def feature_projection(record): return record["executable_definition"] if "executable_definition" in record else {k:record[k] for k in ("event_definition","matched_control_definition","frozen_parameters")}

def _verify_hashes(row):
    if row.get("config_hash") != canonical_hash({k:v for k,v in row.items() if k!="config_hash"}): raise ValueError("registry config hash mismatch")
    if row.get("feature_definition_hash") != canonical_hash(feature_projection(row)): raise ValueError("registry feature hash mismatch")

def _v1(payload):
    rows=payload.get("hypotheses",[])
    required={"hypothesis_id","version","classification","economic_mechanism","available_information_at_event_time","event_definition","matched_control_definition","frozen_parameters","outcome_horizons","dataset_roles","cost_model_version","kill_criteria","feature_definition_hash","config_hash","freeze_timestamp","status"}
    if payload.get("schema_version")!="gen3-tier-a/v1" or len(rows)!=3 or {x.get("hypothesis_id") for x in rows}!=V1_IDS: raise ValueError("exact Tier-A V1 set required")
    for row in rows:
        if set(row)!=required: raise ValueError("registry V1 schema mismatch")
        _verify_hashes(row)
        if row["hypothesis_id"].startswith("G3_H03") and row["classification"]=="ALPHA": raise ValueError("H03 is not alpha")
    payload["execution_status"]="HISTORICAL_NON_EXECUTABLE"
    return payload

def _executable(row):
    definition=row.get("executable_definition")
    common={"observation","quality_policy","availability","refractory","controls","falsification","overlap_policy"}
    if not isinstance(definition,dict) or not common.issubset(definition) or definition["overlap_policy"]!="INDEPENDENT_NO_CROSS_HYPOTHESIS_SUPPRESSION": raise ValueError("incomplete executable preregistration")
    if row["hypothesis_id"].startswith("G3_H01"):
        required={"midpoint_formula","spread_formula","pip_size","dti","sync","er","baseline","trigger","direction_rule","trigger_transition"}
    else:
        required={"level_source","base_representation","volatility_scale","break","inside_buffer","acceptance","rejection","unclassified_resolution"}
    if not required.issubset(definition): raise ValueError("missing executable definition")
    return True

def _v2(payload):
    rows=payload.get("hypotheses",[])
    if payload.get("schema_version")!="gen3-tier-a/v2" or payload.get("registry_version")!="V2" or len(rows)!=3 or {x.get("hypothesis_id") for x in rows}!=V2_IDS: raise ValueError("exact Tier-A V2 set required")
    if payload.get("development_state")!="PREREGISTERED_NOT_RUN": raise ValueError("V2 must be preregistered not run")
    for row in rows:
        if "immutable_reference" in row:
            if set(row)!={"hypothesis_id","immutable_reference","feature_definition_hash","config_hash"}: raise ValueError("invalid immutable reference")
            continue
        _verify_hashes(row)
        if row["hypothesis_id"].endswith("_V2"):
            if row.get("execution_status")!="EXECUTABLE_PREREGISTRATION" or row.get("status")!="PREREGISTERED_NOT_RUN": raise ValueError("invalid V2 execution status")
            _executable(row)
        elif row.get("hypothesis_id")!="G3_H03_MACRO_HAZARD_V1" or row.get("status")!="BLOCKED_NO_CALENDAR_DATA": raise ValueError("H03 reference mismatch")
    return payload

def _v3(payload):
    rows=payload.get("hypotheses",[])
    if payload.get("schema_version")!="gen3-tier-a/v3" or payload.get("registry_version")!="V3" or {x.get("hypothesis_id") for x in rows}!=V3_IDS: raise ValueError("exact Tier-A V3 set required")
    supersession=payload.get("supersession_records",[])
    if supersession != [{"hypothesis_id":"G3_H02_BREAK_STATE_V2","status":"SUPERSEDED_PRE_RUN_DIMENSIONAL_DEFECT","reason":"PRE_RUN_DIMENSIONAL_UNIT_CORRECTION"}]: raise ValueError("V2 supersession audit missing")
    if payload.get("active_execution_set") != ["G3_H01_COHERENT_REPRICING_V2","G3_H02_BREAK_STATE_V3","G3_H03_MACRO_HAZARD_V1"]: raise ValueError("invalid active execution set")
    for row in rows:
        if "immutable_reference" in row:
            if set(row)!={"hypothesis_id","immutable_reference","feature_definition_hash","config_hash"}: raise ValueError("invalid immutable reference")
            continue
        _verify_hashes(row)
        if row["hypothesis_id"]=="G3_H02_BREAK_STATE_V3":
            if row.get("execution_status")!="EXECUTABLE_PREREGISTRATION" or row.get("supersedes")!="G3_H02_BREAK_STATE_V2": raise ValueError("invalid H02 V3 lineage")
            definition=row.get("executable_definition",{})
            units=definition.get("units",{})
            expected={"midpoint":"PRICE","raw_spread":"PRICE","log_midpoint":"LOG_PRICE","oriented_log_distance":"LOG_RETURN","volatility_scale":"LOG_RETURN","log_spread":"LOG_RETURN","normalized_penetration":"DIMENSIONLESS_RATIO"}
            if units!=expected or "raw_spread" in definition.get("break",{}).get("threshold"," "): raise ValueError("incompatible H02 V3 units")
            _executable(row)
    return payload

def load_registry(path):
    payload=json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version")=="gen3-tier-a/v1": return _v1(payload)
    return _v2(payload) if payload.get("schema_version")=="gen3-tier-a/v2" else _v3(payload)
