"""Pure presentation models for Dashboard V2.1; no engine or market-data access."""
from __future__ import annotations
from typing import Any,Mapping
def short_hash(value:Any)->str:
 text=str(value or "Unavailable");return f"{text[:8]}…{text[-4:]}" if len(text)==64 else text
def status_view(status:Mapping[str,Any]|None)->dict[str,Any]:
 value=dict(status or {});milestones=value.get("milestones",{}) if isinstance(value.get("milestones"),dict) else {};h=value.get("hypothesis_states",{}) if isinstance(value.get("hypothesis_states"),dict) else {}
 return {"available":bool(status),"research_only":True,"live_execution":"OFF","tradable_edge":"NOT ESTABLISHED","m3b":milestones.get("M3B","UNAVAILABLE"),"events":"NOT RUN","outcomes":"NOT COMPUTED","edge":"UNKNOWN","next_step":value.get("next_step","UNAVAILABLE"),"tests":(value.get("test_status") or {}).get("suite","UNAVAILABLE"),"blockers":value.get("blockers",["Status artifact unavailable"]),"hypotheses":h,"updated":value.get("generated_at_utc","Unavailable"),"lineage":value.get("dataset_lineage",{}),"registry":value.get("registry",{}),"raw":value}
def hypothesis_cards(status:Mapping[str,Any])->list[dict[str,str]]:
 rows={row.get("id"):row for row in status.get("registry",{}).get("hypotheses",[]) if isinstance(row,dict)};states=status.get("hypothesis_states",{})
 details=[("G3_H01_COHERENT_REPRICING_V2","H01 · Coherent repricing V2","Causal quote-flow coherence beyond price impulse.","Validated quote updates","No stable incremental information over the matched price impulse.","H01"),("G3_H02_BREAK_STATE_V3","H02 · Break state V3","Price-defined break acceptance or rejection.","Causal quotes and completed one-minute midpoint closes","No incremental information over simple excursion and return controls.","H02"),("G3_H03_MACRO_HAZARD_V1","H03 · Macro hazard","Timestamp-only scheduled-event risk context.","Authorized historical calendar snapshot","BLOCKED_NO_CALENDAR_DATA","H03")]
 result=[]
 for ident,title,mechanism,source,blocker,key in details:
  row=rows.get(ident,{})
  result.append({"id":ident,"title":title,"mechanism":mechanism,"source":source,"status":states.get(key,"UNAVAILABLE"),"implementation":"COMPLETE — NOT RUN" if key in {"H01","H02"} else "BLOCKED","materialization":"NOT RUN","outcomes":"NOT COMPUTED","evidence":"UNKNOWN","blocker":blocker,"feature_hash":str(row.get("feature_hash","Unavailable")),"config_hash":str(row.get("config_hash","Unavailable"))})
 return result
