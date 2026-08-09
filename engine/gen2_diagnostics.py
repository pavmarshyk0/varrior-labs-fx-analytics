"""Gen-2 diagnostic layer: descriptive, leakage-safe and non-promotional."""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import asdict
from datetime import UTC
from pathlib import Path
from statistics import mean
from typing import Any, Iterable

from .alpha_families import standard_alpha_families
from .exit_ablation_runner import BarDataset, RunnerConfig, _utc

def _aggregate(rows: Iterable[dict[str, Any]], key: str) -> dict[str, dict[str, float | int | None]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows: groups[str(row.get(key, "UNKNOWN"))].append(row)
    output = {}
    for name, values in sorted(groups.items()):
        net=[x["net_r"] for x in values if x.get("net_r") is not None]; gross=[x["gross_r"] for x in values if x.get("gross_r") is not None]
        output[name] = {"n": len(values), "gross_ev_r": mean(gross) if gross else None, "net_ev_r": mean(net) if net else None,
                        "win_rate": sum(x > 0 for x in net)/len(net) if net else None, "mean_mfe_r": mean(x.get("mfe_r",0.) for x in values), "mean_mae_r": mean(x.get("mae_r",0.) for x in values)}
    return output

def _geometry(candidate, m5, start_index: int, horizon: int) -> dict[str, float | int]:
    risk=candidate.structural_invalidation.stop_distance; targets=(.5,1.,1.5,2.,3.,4.); hits={str(t):0 for t in targets}; ambiguity=0
    stop_seen=False; counted=set()
    for row in m5[start_index:start_index+horizon]:
        high=(row['bid_high']-candidate.entry_price)/risk if candidate.direction.value=='LONG' else (candidate.entry_price-row['ask_low'])/risk
        low=(row['bid_low']-candidate.entry_price)/risk if candidate.direction.value=='LONG' else (candidate.entry_price-row['ask_high'])/risk
        stop=low <= -1
        for target in targets:
            target_hit=high >= target
            if target_hit and stop and target not in counted: ambiguity += 1; counted.add(target)
            elif target_hit and not stop_seen and target not in counted:
                hits[str(target)] += 1; counted.add(target)
        stop_seen |= stop
    return {f'hit_{t}_before_sl': hits[str(t)] for t in targets} | {'ambiguity_bars': ambiguity}

def run_gen2_diagnostics(bars_dir: str | Path, alpha_root: str | Path, output_dir: str | Path, *, config: RunnerConfig = RunnerConfig(minimum_train_size=40, validation_size=30)) -> Path:
    """Write diagnosis tables using only pre-entry snapshots plus separate future paths."""
    try:
        import pyarrow.parquet as pq
    except ImportError as exc: raise RuntimeError('pyarrow required') from exc
    dataset=BarDataset.load(bars_dir); m5=dataset.bars['M5']; index={_utc(r['bar_start']):i for i,r in enumerate(m5)}
    output: dict[str, Any]={'schema_version':'alpha-gen2-diagnostics/v1','dataset':dataset.manifest,'final_holdout_status':'LOCKED','families':{},'limitations':['Bar-path geometry is conservative when a target and stop coexist in one M5 OHLC bar. Tick-level event path is not recomputed here.','Diagnostics are descriptive; they do not select thresholds or modify any candidate generator.']}
    for family in standard_alpha_families(config):
        path=Path(alpha_root)/family.family_id/'detailed_results.parquet'
        if not path.exists(): continue
        trades=[r for r in pq.read_table(path).to_pylist() if r['exit_policy']=='FIXED_RR' and r['cost_scenario']=='BASELINE_1X']
        candidates={c.candidate_id:c for c in family.generate_candidates(dataset)}
        joined=[]; geometry=[]
        for trade in trades:
            candidate=candidates.get(trade['candidate_id'])
            if candidate is None: continue
            row={**trade,'direction':candidate.direction.value,'hour_utc':candidate.timestamp.hour,'day_of_week':candidate.timestamp.strftime('%a'),'h1_direction':candidate.regime,'atr_proxy':candidate.feature_snapshot.get('atr_proxy'),'m5_impulse':candidate.feature_snapshot.get('m5_close_minus_open')}
            joined.append(row)
            geometry.append(_geometry(candidate,m5,index[candidate.timestamp],config.max_holding_bars))
        feature_ic={}
        for feature in ('atr_proxy','m5_impulse'):
            pairs=[(r[feature],r['gross_r']) for r in joined if r[feature] is not None and r['gross_r'] is not None]
            if len(pairs)>2:
                xs,ys=zip(*pairs); mx,my=mean(xs),mean(ys); den=((sum((x-mx)**2 for x in xs)*sum((y-my)**2 for y in ys))**.5); feature_ic[feature]=sum((x-mx)*(y-my) for x,y in pairs)/den if den else 0.
        output['families'][family.family_id]={'oos_trades':len(joined),'by_direction':_aggregate(joined,'direction'),'by_session':_aggregate(joined,'session'),'by_regime':_aggregate(joined,'regime'),'by_hour_utc':_aggregate(joined,'hour_utc'),'by_day_of_week':_aggregate(joined,'day_of_week'),'feature_gross_ev_correlation':feature_ic,'outcome_geometry':{'n':len(geometry),'target_hits_before_sl':{f'{t}R':sum(x[f'hit_{t}_before_sl'] for x in geometry)/len(geometry) if geometry else None for t in (.5,1.,1.5,2.,3.,4.)},'ambiguity_bar_rate':sum(x['ambiguity_bars'] for x in geometry)/(len(geometry)*config.max_holding_bars) if geometry else None}}
    out=Path(output_dir); out.mkdir(parents=True,exist_ok=True); (out/'failure_analysis.json').write_text(json.dumps(output,indent=2,sort_keys=True,default=str),encoding='utf-8')
    registry={'schema_version':'hypothesis-registry/v1','development_dataset_fingerprint':dataset.manifest['dataset_fingerprint'],'final_holdout_status':'LOCKED','hypotheses':[{'hypothesis_id':name,'version':'v1','rationale':'Predeclared deterministic alpha family; benchmarked with frozen 3R control exit.','status':'REJECTED' if data.get('oos_trades',0) else 'INSUFFICIENT_DATA'} for name,data in output['families'].items()]}
    (out/'hypothesis_registry.json').write_text(json.dumps(registry,indent=2,sort_keys=True),encoding='utf-8')
    return out
