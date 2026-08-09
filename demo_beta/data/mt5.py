from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from ..contracts import Tick


class MT5Like(Protocol):
    COPY_TICKS_ALL: int

    def initialize(self) -> bool: ...
    def shutdown(self) -> None: ...
    def last_error(self) -> Any: ...
    def copy_ticks_range(self, symbol: str, date_from: datetime, date_to: datetime, flags: int) -> Any: ...


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("MT5 collection bounds must be timezone-aware")
    return value.astimezone(UTC)


@dataclass(slots=True)
class MT5TickCollector:
    api: MT5Like
    symbol: str = "EURUSD"

    def collect(self, start: datetime, end: datetime) -> list[Tick]:
        start_utc = _as_utc(start)
        end_utc = _as_utc(end)
        if end_utc <= start_utc:
            raise ValueError("end must be after start")
        if not self.api.initialize():
            raise RuntimeError(f"MT5 initialize failed: {self.api.last_error()}")
        try:
            rows = self.api.copy_ticks_range(self.symbol, start_utc, end_utc, self.api.COPY_TICKS_ALL)
            if rows is None:
                raise RuntimeError(f"MT5 copy_ticks_range failed: {self.api.last_error()}")
            return [
                Tick(
                    time_msc=int(row["time_msc"]),
                    bid=float(row["bid"]),
                    ask=float(row["ask"]),
                    flags=int(row["flags"]),
                )
                for row in rows
            ]
        finally:
            self.api.shutdown()

    @classmethod
    def from_terminal(cls, symbol: str = "EURUSD") -> "MT5TickCollector":
        try:
            import MetaTrader5 as mt5  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError("Install the optional 'mt5' dependency on a machine with MetaTrader 5") from exc
        return cls(api=mt5, symbol=symbol)

