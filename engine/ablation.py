"""Frozen M4 ablation definitions; no module gains execution authority here."""

from __future__ import annotations

from dataclasses import dataclass


MODULES = ("tick", "time", "regime")


@dataclass(frozen=True, slots=True)
class AblationArm:
    name: str
    enabled_modules: tuple[str, ...]
    preregistered: bool = True
    execution_authority: str = "NONE"


def preregistered_ablation_matrix() -> tuple[AblationArm, ...]:
    """The fixed M4 comparison family; do not data-mine additional arms mid-run."""
    return (
        AblationArm("Baseline", ()),
        AblationArm("Tick", ("tick",)),
        AblationArm("Time", ("time",)),
        AblationArm("Regime", ("regime",)),
        AblationArm("Tick+Time", ("tick", "time")),
        AblationArm("Tick+Regime", ("tick", "regime")),
        AblationArm("Time+Regime", ("time", "regime")),
        AblationArm("Full", MODULES),
        AblationArm("Full-minus-Tick", ("time", "regime")),
        AblationArm("Full-minus-Time", ("tick", "regime")),
        AblationArm("Full-minus-Regime", ("tick", "time")),
    )


def exit_policy_ablation_matrix() -> tuple[AblationArm, ...]:
    """Frozen, like-for-like exit-policy comparison family.

    Runners must supply the same candidate ids, folds, costs, risk and event
    timestamps to every arm; this definition itself never selects a winner.
    """
    return (
        AblationArm("A-Fixed-3R", ("exit:FIXED_RR",)),
        AblationArm("B-Dynamic-RR", ("exit:DYNAMIC_RR",)),
        AblationArm("C-Structure-Liquidity", ("exit:STRUCTURE_TARGET",)),
        AblationArm("D-Partial-Trailing", ("exit:PARTIAL_TRAILING",)),
        AblationArm("E-Best-Deterministic-OOS", ("exit:SELECTED_AFTER_TRAIN",)),
    )
