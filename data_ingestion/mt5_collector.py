"""MetaTrader 5 tick collection and validated Parquet persistence.

The implementation lives in :mod:`demo_beta.data.mt5`; this public module keeps
the research tree stable while preserving one implementation of the collector.
"""

from pathlib import Path
from typing import Sequence

from demo_beta.contracts import Tick
from demo_beta.data.mt5 import MT5Like, MT5TickCollector
from demo_beta.data.validation import DataQualityViolation, TickFeedValidator


def write_validated_parquet(
    ticks: Sequence[Tick],
    path: str | Path,
    *,
    validator: TickFeedValidator | None = None,
) -> Path:
    """Write an immutable-order tick sample after a hard data-quality gate.

    UTC milliseconds remain canonical; an explicit timezone-aware timestamp
    column is stored alongside the raw `time_msc` value for analytics engines.
    """

    quality = (validator or TickFeedValidator()).validate(ticks)
    if not quality.valid:
        raise DataQualityViolation(f"refusing Parquet export: {', '.join(quality.hard_failures)}")
    try:
        import pyarrow as pa  # type: ignore[import-not-found]
        import pyarrow.parquet as pq  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("Parquet export requires pyarrow; install requirements.txt") from exc

    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    table = pa.table(
        {
            "time_msc": [tick.time_msc for tick in ticks],
            "timestamp_utc": pa.array(
                [tick.timestamp for tick in ticks],
                type=pa.timestamp("ms", tz="UTC"),
            ),
            "bid": [tick.bid for tick in ticks],
            "ask": [tick.ask for tick in ticks],
            "flags": [tick.flags for tick in ticks],
        }
    )
    pq.write_table(table, output, compression="zstd")
    return output

__all__ = ["MT5Like", "MT5TickCollector", "write_validated_parquet"]
