from __future__ import annotations

from dataclasses import dataclass

from .contracts import Candidate, Direction


class RiskViolation(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RiskPolicy:
    min_planned_rr: float = 3.0
    max_risk_fraction: float = 0.01
    enforce_min_planned_rr: bool = True

    def validate(self, candidate: Candidate) -> None:
        violations: list[str] = []
        if not candidate.candidate:
            violations.append("candidate flag must be true")
        if candidate.pair != "EUR_USD":
            violations.append("only EUR_USD is allowed in demo-0.0-beta")
        if candidate.risk_fraction <= 0 or candidate.risk_fraction > self.max_risk_fraction:
            violations.append(
                f"risk_fraction must be in (0, {self.max_risk_fraction:.4f}], got {candidate.risk_fraction:.4f}"
            )
        # Fixed-RR remains the frozen control baseline.  New research policies
        # deliberately opt out and are accepted only by the EV/feasibility path.
        if self.enforce_min_planned_rr and candidate.planned_rr + 1e-12 < self.min_planned_rr:
            violations.append(
                f"planned RR must be >= {self.min_planned_rr:.2f}, got {candidate.planned_rr:.4f}"
            )
        if candidate.direction is Direction.LONG:
            if not candidate.stop_loss < candidate.entry < candidate.take_profit:
                violations.append("LONG requires stop_loss < entry < take_profit")
        else:
            if not candidate.take_profit < candidate.entry < candidate.stop_loss:
                violations.append("SHORT requires take_profit < entry < stop_loss")
        if violations:
            raise RiskViolation("; ".join(violations))
