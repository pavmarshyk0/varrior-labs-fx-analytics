"""Read-only, bounded artifact adapters for the local research dashboard."""
from __future__ import annotations
import hashlib,json,os,tempfile
from datetime import UTC,datetime
from pathlib import Path
from typing import Any,Mapping
FAMILIES="families.json"; EVENT_SCHEMA="gen3-causal-event/v1"; STATUS_SCHEMA="gen3-dashboard-status/v1"; MAX_EVENT_BYTES=2_000_000; MAX_EVENTS=5_000
FORBIDDEN_EVENT_TERMS=("outcome","forward","mfe","mae","expectancy","profit","win_rate","tp","sl")
EVENT_KEYS={"schema_version","hypothesis_id","event_id","event_at_utc","available_at_utc","direction","dataset_role","level_id","lineage","frozen_hashes","feature_values","quality_flags"}
def canonical_hash(value:Any)->str:return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
def read_json_detail(path:str|Path,*,max_bytes:int=MAX_EVENT_BYTES)->dict[str,Any]:
 source=Path(path)
 try:
  if not source.is_file():return {"status":"UNAVAILABLE","data":None,"error":"artifact not found"}
  if source.stat().st_size>max_bytes:return {"status":"UNSUPPORTED","data":None,"error":f"artifact exceeds {max_bytes} byte dashboard limit"}
  data=json.loads(source.read_text(encoding="utf-8"))
 except json.JSONDecodeError as error:return {"status":"MALFORMED","data":None,"error":f"line {error.lineno}, column {error.colno}: {error.msg}"}
 except OSError as error:return {"status":"UNAVAILABLE","data":None,"error":str(error)}
 return {"status":"VALID","data":data,"error":None}
def read_json(path:str|Path):
 result=read_json_detail(path);return result["data"] if result["status"]=="VALID" and isinstance(result["data"],dict) else None
def candidates(value:str|Path)->list[Path]:
 path=Path(value);bases=[path,path/'data'/'research'/'alpha'/'latest',path/'research'/'alpha'/'latest',path/'alpha'/'latest']
 return sorted({(base if base.name==FAMILIES else base/FAMILIES).resolve() for base in bases if (base if base.name==FAMILIES else base/FAMILIES).is_file()},key=str)
def resolve_families(value:str|Path)->dict[str,Any]:
 path=Path(value);direct=[path.resolve()] if path.name==FAMILIES and path.is_file() else candidates(path)
 return {"status":"UNAVAILABLE" if not direct else "AMBIGUOUS" if len(direct)>1 else "RESOLVED","candidates":[str(item) for item in direct],"path":str(direct[0]) if len(direct)==1 else None}
def legacy_families(path:str|Path)->dict[str,Any]:
 result=read_json_detail(path)
 if result["status"]!="VALID":return {"status":result["status"],"error":result["error"],"families":None}
 data=result["data"]
 if not isinstance(data,dict) or not data or not all(isinstance(value,dict) and {"family_id","metrics","dataset","status"}.issubset(value) for value in data.values()):return {"status":"INCOMPATIBLE","error":"families.json does not match the supported legacy family mapping","families":None}
 return {"status":"VALID","error":None,"families":data}
def legacy_rows(families:Mapping[str,Mapping[str,Any]])->list[dict[str,Any]]:
 aliases={"sample_size":("sample_size","n","trades","oos_trades"),"win_rate":("win_rate",),"gross_expectancy":("gross_expectancy","gross_expectancy_r"),"net_expectancy":("net_expectancy","net_expectancy_r"),"confidence_interval":("confidence_interval","ci_95","confidence_interval_95"),"cost_drag":("cost_drag","cost_drag_r"),"drawdown":("max_drawdown","drawdown","max_drawdown_r")};rows=[]
 for key,family in sorted(families.items()):
  metrics=family.get("metrics",{}) if isinstance(family.get("metrics"),dict) else {};row={"family":family.get("family_id",key),"research_conclusion":family.get("status","Unavailable")}
  for label,names in aliases.items():row[label]=next((metrics[name] for name in names if name in metrics),"Unavailable")
  rows.append(row)
 return rows
def resolve_event_artifact(root:str|Path)->dict[str,Any]:
 root=Path(root);found=[root/'data'/'research'/'gen3'/'latest'/name for name in ("events.json","causal_events.json","gen3_events.json")];found=[path for path in found if path.is_file()]
 if not found:return {"status":"NOT_RUN","path":None,"events":[],"error":"event materialization has not been run"}
 if len(found)!=1:return {"status":"AMBIGUOUS","path":None,"events":[],"error":"multiple causal event artifacts found"}
 return load_events(found[0])
def _forbidden(value:Any)->bool:
 if isinstance(value,dict):return any(any(term in str(key).lower() for term in FORBIDDEN_EVENT_TERMS) or _forbidden(item) for key,item in value.items())
 return any(_forbidden(item) for item in value) if isinstance(value,list) else False
def load_events(path:str|Path)->dict[str,Any]:
 result=read_json_detail(path)
 if result["status"]!="VALID":return {"status":result["status"],"path":str(path),"events":[],"error":result["error"]}
 data=result["data"];events=data.get("events") if isinstance(data,dict) and set(data)=={"events"} else data
 if not isinstance(events,list) or len(events)>MAX_EVENTS:return {"status":"UNSUPPORTED","path":str(path),"events":[],"error":"event artifact must be a bounded JSON event list"}
 for event in events:
  if not isinstance(event,dict) or set(event)!=EVENT_KEYS or event.get("schema_version")!=EVENT_SCHEMA or _forbidden(event):return {"status":"UNSUPPORTED","path":str(path),"events":[],"error":"event schema is unsupported or contains prohibited outcome fields"}
 return {"status":"VALID","path":str(path),"events":events,"error":None}
def status_projection(status:Mapping[str,Any])->dict[str,Any]:return {key:value for key,value in status.items() if key not in {"generated_at_utc","analytical_hash","local_paths"}}
def build_status(repo_root:str|Path,*,test_status:Mapping[str,str]|None=None)->dict[str,Any]:
 root=Path(repo_root);registry=read_json(root/'config/gen3/tier_a_v3.json') or {}
 return {"schema_version":STATUS_SCHEMA,"generated_at_utc":datetime.now(UTC).isoformat().replace('+00:00','Z'),"project":"Varrior Labs FX Analytics","active_stage":"M3B","milestones":{"M0":"COMPLETE","M1":"COMPLETE","M2":"COMPLETE","M3A":"COMPLETE_WITH_PRE_RUN_DIMENSIONAL_DEFECT_FOUND","M3A.1":"COMPLETE","M3B":"COMPLETE_IMPLEMENTATION_NOT_RUN","M4":"NOT_STARTED","M5":"NOT_STARTED"},"test_status":dict(test_status or {"suite":"UNAVAILABLE — no verified test record in artifact"}),"dataset_lineage":{"fingerprint":"89c5a2f618337c2e92601049ae937ab4ac559f037cfed7c41f500093e461015a","coverage":"2024-08-01T00:00:00Z to 2026-08-01T00:00:00Z","chunks":{"COMPLETED":519,"EXPECTED_MARKET_CLOSED":208,"NO_BROKER_HISTORY":3},"missing_intervals":[]},"registry":{"active_execution_set":registry.get("active_execution_set",[]),"hypotheses":[{"id":row.get("hypothesis_id"),"feature_hash":row.get("feature_definition_hash"),"config_hash":row.get("config_hash")} for row in registry.get("hypotheses",[])]},"temporal_config_hash":"36e9d009427c470d01bf191a4405e63f9616d6251eac5934c472db55b210b2e2","hypothesis_states":{"H01":"PREREGISTERED_NOT_RUN","H02":"PREREGISTERED_NOT_RUN","H03":"BLOCKED_NO_CALENDAR_DATA"},"blockers":["H03 calendar unavailable"],"warnings":["Legacy Gen-2 artifacts are not Gen-3 results."],"trading_status":"NO_LIVE_EXECUTION","profitability_claim":"NONE","validated_conclusion":"NO_EDGE_FOUND_GEN2","gen3_outcome":"NOT_YET_EVALUATED","next_step":"M4_IMPLEMENT_MATCHED_CONTROL_ENGINE","local_paths":{}}
def write_status(repo_root:str|Path,output_path:str|Path,*,test_status:Mapping[str,str]|None=None)->dict[str,Any]:
 status=build_status(repo_root,test_status=test_status);status["analytical_hash"]=canonical_hash(status_projection(status));output=Path(output_path);output.parent.mkdir(parents=True,exist_ok=True)
 with tempfile.NamedTemporaryFile("w",encoding="utf-8",delete=False,dir=output.parent) as handle:json.dump(status,handle,sort_keys=True,indent=2);handle.write("\n");temporary=handle.name
 os.replace(temporary,output);return status
