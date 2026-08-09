from __future__ import annotations

import csv
from pathlib import Path

from ..contracts import Tick


REQUIRED_COLUMNS = {"time_msc", "bid", "ask"}


def load_ticks_csv(path: str | Path) -> list[Tick]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = set(reader.fieldnames or ())
        missing = REQUIRED_COLUMNS - fields
        if missing:
            raise ValueError(f"tick CSV missing columns: {sorted(missing)}")
        ticks: list[Tick] = []
        for line_no, row in enumerate(reader, start=2):
            try:
                ticks.append(
                    Tick(
                        time_msc=int(row["time_msc"]),
                        bid=float(row["bid"]),
                        ask=float(row["ask"]),
                        flags=int(row.get("flags") or 0),
                    )
                )
            except (TypeError, ValueError) as exc:
                raise ValueError(f"invalid tick at CSV line {line_no}: {exc}") from exc
    return ticks

