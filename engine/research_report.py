"""Deterministic Markdown report for preregistered walk-forward experiments."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from .ablation import AblationArm
from .research_statistics import BootstrapCI, TradeObservation, block_bootstrap_expectancy_ci, performance_statistics


@dataclass(frozen=True, slots=True)
class ArmReport:
    arm: AblationArm
    trades: tuple[TradeObservation, ...]
    lineage_ids: tuple[str, ...]
    gross_expectancy_r: float | None = None
    cost_stress_net_expectancy: Mapping[str, float] | None = None
    experiment_id: str = "UNSPECIFIED"


def render_research_report(reports: Sequence[ArmReport], *, bootstrap_block_size: int = 5,
                           bootstrap_samples: int = 2_000) -> str:
    """Render only observed OOS results; no arm is promoted by this report."""
    rows = [
        "# EUR/USD M4 research report", "", "Status: **RESEARCH**. This report cannot authorise trading changes.",
        "All returns are executable net R; gross/net are not combined with a second spread charge.", "",
        "| Arm | Trades | Net expectancy R (95% block CI) | Gross expectancy R | Win rate | Max DD R | Losing streak | Frequency/week |",
        "| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for report in reports:
        stats = performance_statistics(report.trades)
        if stats.trade_count:
            ci = block_bootstrap_expectancy_ci([item.net_r for item in report.trades], block_size=bootstrap_block_size,
                                                samples=bootstrap_samples)
            expectancy = f"{ci.point_estimate:.3f} [{ci.lower_95:.3f}, {ci.upper_95:.3f}]"
            win_rate = f"{stats.win_rate:.1%}"
            dd, freq = f"{stats.maximum_drawdown_r:.3f}", (f"{stats.frequency_per_week:.2f}" if stats.frequency_per_week is not None else "n/a")
        else:
            expectancy = win_rate = dd = freq = "n/a"
        gross = f"{report.gross_expectancy_r:.3f}" if report.gross_expectancy_r is not None else "NOT_RECORDED"
        rows.append(f"| {report.arm.name} | {stats.trade_count} | {expectancy} | {gross} | {win_rate} | {dd} | {stats.longest_losing_streak} | {freq} |")
    rows.extend(["", "## Lineage", ""])
    for report in reports:
        rows.append(f"- {report.arm.name}: {', '.join(report.lineage_ids) or 'NOT_RECORDED'}")
    rows.extend(["", "## Edge survival by cost scenario", ""])
    for report in reports:
        stress = report.cost_stress_net_expectancy or {}
        observed = ", ".join(f"{name}={value:.3f}R" for name, value in sorted(stress.items())) or "NOT_RECORDED"
        fragile = stress.get("BASELINE_1.25X") is not None and stress["BASELINE_1.25X"] <= 0
        rows.append(f"- {report.arm.name}: {observed}; execution-fragile={str(fragile).lower()}")
    rows.extend(["", "## Guardrails", "", "- Fixed 3R is the frozen control baseline; non-baseline exits require positive OOS net expectancy after costs.",
                 "- Risk <= 1%; paper default risk is 0.5%.",
                 "- No martingale, grid, averaging, or AI-generated direction.",
                 "- Tick/Time/Regime modules remain SHADOW/RESEARCH and have no execution authority."])
    return "\n".join(rows) + "\n"


def write_research_report(path: str | Path, reports: Sequence[ArmReport], **kwargs: object) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_research_report(reports, **kwargs), encoding="utf-8")
    return output
