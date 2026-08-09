"""Deterministic session-open event studies with locked chronological holdout."""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean, median
from zoneinfo import ZoneInfo

from .exit_ablation_runner import BarDataset, INVALID_FLAGS, _utc
from .research_statistics import block_bootstrap_expectancy_ci

HORIZONS=(1,3,6,12,24,36)
DISCOVERY_END=datetime(2025,8,1,tzinfo=UTC); CONFIRMATION_END=datetime(2026,2,1,tzinfo=UTC)

def _session_open(timestamp: datetime) -> str | None:
    london=timestamp.astimezone(ZoneInfo('Europe/London')); ny=timestamp.astimezone(ZoneInfo('America/New_York'))
    if london.hour == 8 and london.minute == 0: return 'LONDON_OPEN'
    if ny.hour == 8 and ny.minute == 0: return 'NEW_YORK_OPEN'
    return None

def _period(timestamp: datetime) -> str:
    return 'DISCOVERY' if timestamp < DISCOVERY_END else 'CONFIRMATION' if timestamp < CONFIRMATION_END else 'LOCKED_HOLDOUT'

def run_session_open_studies(bars_dir: str | Path, output_dir: str | Path) -> Path:
    dataset=BarDataset.load(bars_dir); bars=dataset.bars['M5']; results=defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for i,row in enumerate(bars):
        timestamp=_utc(row['bar_start']); event=_session_open(timestamp)
        if not event or set(row.get('quality_flags') or ()) & INVALID_FLAGS: continue
        period=_period(timestamp)
        for horizon in HORIZONS:
            if i+horizon >= len(bars): continue
            future=bars[i+horizon]
            if _utc(future['bar_start']) != timestamp.replace() and (_utc(future['bar_start'])-timestamp).total_seconds() != horizon*300: continue
            ret=(future['bid_close']-row['ask_open'])/.0001
            results[event][period][str(horizon)].append(ret)
    output={'schema_version':'event-studies/v1','dataset':dataset.manifest,'boundaries':{'discovery_end':DISCOVERY_END,'confirmation_end':CONFIRMATION_END,'holdout_status':'LOCKED'},'events':{}}
    for event, periods in results.items():
        output['events'][event]={}
        for period, horizons in periods.items():
            output['events'][event][period]={}
            for horizon, values in horizons.items():
                # No outcome aggregate is computed or shown for the locked segment.
                output['events'][event][period][horizon]={'n':len(values)} if period=='LOCKED_HOLDOUT' else {'n':len(values),'mean_pips':mean(values),'median_pips':median(values),'ci_95':asdict(block_bootstrap_expectancy_ci(values,block_size=min(5,len(values)),samples=500)) if values else None}
    root=Path(output_dir); root.mkdir(parents=True,exist_ok=True); (root/'event_studies.json').write_text(json.dumps(output,indent=2,default=str,sort_keys=True),encoding='utf-8')
    return root
