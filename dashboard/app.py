"""Varrior Labs local read-only research cockpit."""
import os
from datetime import datetime
from pathlib import Path
import pandas as pd
import streamlit as st
from dashboard.artifacts import legacy_families,legacy_rows,read_json_detail,resolve_event_artifact,resolve_families
from dashboard.view_models import hypothesis_cards,short_hash,status_view

st.set_page_config(page_title="Varrior Labs FX Analytics",page_icon=":material/query_stats:",layout="wide")
st.html("""<style>
[data-testid="stAppViewContainer"] { background:#131517; }
[data-testid="stSidebar"] { border-right:1px solid #343a40; }
.vr-caption { color:#9aa1a8; font-size:.86rem; letter-spacing:.03em; }
.vr-mono { font-family:monospace; font-size:.84rem; }
</style>""")
ROOT=Path(__file__).resolve().parents[1]
STATUS_PATH=ROOT/"data/research/gen3/latest/project_status.json"

@st.cache_data(ttl=30,max_entries=8)
def cached_status(path:str): return read_json_detail(path,max_bytes=250_000)
@st.cache_data(ttl=30,max_entries=8)
def cached_events(root:str): return resolve_event_artifact(root)

status_result=cached_status(str(STATUS_PATH)); status=status_view(status_result["data"] if status_result["status"]=="VALID" else None)
local=read_json_detail(os.environ.get("VARRIOR_DASHBOARD_CONFIG",ROOT/"config/local/dashboard_paths.json"),max_bytes=100_000)
local_data=local["data"] if local["status"]=="VALID" and isinstance(local["data"],dict) else {}
with st.sidebar:
 st.markdown("## VARrior")
 st.caption("EUR/USD research cockpit · local read-only")
 page=st.selectbox("View",["Overview","Research pipeline","Gen-3 hypotheses","Data health","Event explorer","Gen-3 results","Legacy Gen-2","Technical details"],label_visibility="collapsed")
 st.caption("Legacy artifact location")
 artifact_root=st.text_input("Research artifact directory",value=os.environ.get("VARRIOR_ARTIFACT_ROOT") or local_data.get("legacy_alpha_artifact_root","") or "",placeholder="Project root or families.json",label_visibility="collapsed")
 st.caption("The dashboard reads small JSON artifacts only. It never opens market data.")

st.title("Varrior Labs FX Analytics")
st.caption("Deterministic EUR/USD research platform · dashboard V2.1")

def badge(text,color="gray"):
 st.badge(text,color=color)
def section(title,caption):
 st.header(title); st.caption(caption)
def overview():
 section("Research state","Implementation and evidence are deliberately kept separate.")
 with st.container(horizontal=True):
  st.metric("Research mode","RESEARCH ONLY",border=True);st.metric("Live execution","OFF",border=True);st.metric("Tradable edge","NOT ESTABLISHED",border=True);st.metric("Gen-3 evidence","UNKNOWN",border=True)
 with st.container(horizontal=True):
  st.metric("M3B implementation",status["m3b"],border=True);st.metric("Causal events","NOT RUN",border=True);st.metric("Forward outcomes","NOT COMPUTED",border=True);st.metric("Next permitted action",status["next_step"],border=True)
 st.subheader("Active hypotheses")
 with st.container(horizontal=True):
  for key in ("H01","H02","H03"): st.metric(key,status["hypotheses"].get(key,"UNAVAILABLE"),border=True)
 st.subheader("Verification and blockers")
 st.write(f"Verified test record: {status['tests']}")
 for item in status["blockers"]: st.warning(item)
 st.caption(f"Last artifact update: {status['updated']}")
def pipeline():
 section("Research pipeline","Code readiness does not imply a market-data evaluation has occurred.")
 steps=[("Data","Complete","Historical lineage recorded"),("Quality","Complete","M1 lineage audit"),("Features","Complete","M3B causal feature code"),("Events","Ready","Detector implemented; materialization not run"),("Controls","Pending","M4 not started"),("Outcomes","Unavailable","No forward outcomes computed"),("Validation","Pending","Requires outcomes and controls"),("Paper","Pending","No tradable edge")]
 for label,state,note in steps:
  with st.container(border=True):
   left,right=st.columns([1,3]);left.markdown(f"**{label}**");right.write(f"{state} — {note}")
def hypotheses():
 section("Gen-3 hypotheses","Frozen definitions and hashes are display-only.")
 for card in hypothesis_cards(status["raw"]):
  with st.container(border=True):
   st.subheader(card["title"]); badge(card["status"],"orange" if "BLOCKED" in card["status"] else "gray")
   st.write(card["mechanism"]);st.caption(f"Required source: {card['source']}")
   a,b,c=st.columns(3);a.metric("Implementation",card["implementation"]);b.metric("Materialization",card["materialization"]);c.metric("Outcomes / evidence",f"{card['outcomes']} · {card['evidence']}")
   st.caption(f"Blocker / kill criterion: {card['blocker']}")
   with st.expander("Frozen identifiers"):
    st.code(f"feature  {card['feature_hash']}\nconfig   {card['config_hash']}",language=None)
def health():
 section("Data health","Only lineage/status metadata is displayed; raw market files are never opened.")
 lineage=status["lineage"]
 if not lineage: st.info("Unavailable — status artifact is missing or malformed.");return
 st.metric("Dataset coverage",lineage.get("coverage","Unavailable"),border=True)
 st.metric("Dataset fingerprint",short_hash(lineage.get("fingerprint")),border=True)
 chunks=lineage.get("chunks")
 if isinstance(chunks,dict): st.dataframe(pd.DataFrame(sorted(chunks.items()),columns=["Daily chunk state","Count"]),hide_index=True)
 else: st.info("Daily chunk states: Unavailable")
 st.caption("Tick count, bar counts, invalid bars, suspicious gaps, extreme-spread bars, and source freshness are Unavailable unless supplied by a small status artifact.")
def explorer():
 section("Event explorer","Displays only causal `gen3-causal-event/v1` fields when a bounded artifact exists.")
 events=cached_events(str(ROOT))
 if events["status"]=="NOT_RUN": st.info("EVENT MATERIALIZATION NOT RUN — M3B implemented the causal detector but has not evaluated it on market data.");return
 if events["status"]!="VALID": st.error(f"{events['status']}: {events['error']}");return
 data=events["events"]
 choices=sorted({x["hypothesis_id"] for x in data}); selected=st.multiselect("Hypothesis",choices,default=choices)
 directions=sorted({x["direction"] for x in data});direction=st.multiselect("Direction / classification",directions,default=directions)
 sessions=sorted({str(x["feature_values"].get("session","Unavailable")) for x in data});session=st.multiselect("Session",sessions,default=sessions)
 levels=sorted({str(x.get("level_id") or "Unavailable").split(":")[0] for x in data});level=st.multiselect("Level type",levels,default=levels)
 quality=st.multiselect("Quality status",["VALID","FLAGGED"],default=["VALID","FLAGGED"])
 dates=[datetime.fromisoformat(x["event_at_utc"].replace("Z","+00:00")).date() for x in data];window=st.date_input("UTC time range",value=(min(dates),max(dates)))
 start,end=window if isinstance(window,tuple) and len(window)==2 else (min(dates),max(dates))
 filtered=[x for x in data if x["hypothesis_id"] in selected and x["direction"] in direction and str(x["feature_values"].get("session","Unavailable")) in session and str(x.get("level_id") or "Unavailable").split(":")[0] in level and ("FLAGGED" if x["quality_flags"] else "VALID") in quality and start<=datetime.fromisoformat(x["event_at_utc"].replace("Z","+00:00")).date()<=end]
 rows=[{"Hypothesis":x["hypothesis_id"],"Direction":x["direction"],"Event UTC":x["event_at_utc"],"Available UTC":x["available_at_utc"],"Level":x.get("level_id") or "—","Quality":", ".join(x["quality_flags"]) or "VALID"} for x in filtered]
 st.dataframe(pd.DataFrame(rows),hide_index=True)
 with st.expander("Causal event details"):
  st.json(filtered[:50])
def results():
 section("Gen-3 results","NOT YET EVALUATED")
 st.info("No Gen-3 forward outcomes, matched-control results, or profitability claims are available.")
def legacy():
 section("Legacy Gen-2","LEGACY GEN-2 — NOT GEN-3 RESULTS")
 if not artifact_root: st.info("Legacy artifacts unavailable; provide a project root or direct families.json path.");return
 resolved=resolve_families(artifact_root)
 if resolved["status"]!="RESOLVED": st.error(f"{resolved['status']}: choose one direct families.json path.");return
 data=legacy_families(resolved["path"])
 if data["status"]!="VALID": st.error(f"{data['status']}: {data['error']}");return
 st.dataframe(pd.DataFrame(legacy_rows(data["families"])),hide_index=True)
 with st.expander("Technical source"):
  st.code(resolved["path"],language=None)
def technical():
 section("Technical details","Raw artifacts remain secondary to the research state.")
 with st.expander("Status artifact"):
  st.json(status_result["data"] if status_result["status"]=="VALID" else status_result)
 with st.expander("Resolved paths and schemas"):
  st.code(f"status: {STATUS_PATH}\nstatus schema: {status_result['data'].get('schema_version','Unavailable') if status_result['status']=='VALID' else 'Unavailable'}\nevent schema: gen3-causal-event/v1\nlegacy configuration: {os.environ.get('VARRIOR_DASHBOARD_CONFIG',ROOT/'config/local/dashboard_paths.json')}",language=None)

{"Overview":overview,"Research pipeline":pipeline,"Gen-3 hypotheses":hypotheses,"Data health":health,"Event explorer":explorer,"Gen-3 results":results,"Legacy Gen-2":legacy,"Technical details":technical}[page]()
