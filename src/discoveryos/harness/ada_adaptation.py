from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from discoveryos.operators.action_controller import BranchSearchState, SearchDecision, SearchState
from discoveryos.util import canonical_json, digest_json


class AdaLocalMode(str, Enum):
    EXPLORE = "EXPLORE"
    REFINE = "REFINE"


@dataclass(frozen=True, slots=True)
class AdaTrajectoryConfig:
    window_size: int = 4
    decay: float = 0.75
    productive_signal_threshold: float = 0.05
    explore_intensity: float = 0.75
    refine_intensity: float = 0.25

    def __post_init__(self) -> None:
        if self.window_size < 1:
            raise ValueError("Ada trajectory window must be positive")
        if not 0.0 < self.decay <= 1.0:
            raise ValueError("Ada trajectory decay must be in (0, 1]")
        if self.productive_signal_threshold < 0:
            raise ValueError("Ada productive signal threshold cannot be negative")
        if not 0.0 <= self.refine_intensity < self.explore_intensity <= 1.0:
            raise ValueError("Ada exploration intensities must be ordered in [0, 1]")

    @property
    def digest(self) -> str:
        return digest_json(self)


@dataclass(frozen=True, slots=True)
class AdaTrajectoryState:
    run_id: str
    step: int
    branch_id: str
    parent_candidate_id: str
    recent_improvements: tuple[float, ...]
    accumulated_improvement_signal: float
    generations_since_improvement: int
    sibling_outcomes: tuple[str, ...]
    lineage_receipt_ids: tuple[str, ...]

    @property
    def digest(self) -> str:
        return digest_json(self)


@dataclass(frozen=True, slots=True)
class AdaTrajectoryReceipt:
    state: AdaTrajectoryState
    config_digest: str
    mode: AdaLocalMode
    exploration_intensity: float

    @property
    def digest(self) -> str:
        return digest_json(self)

    @property
    def reason_codes(self) -> tuple[str, ...]:
        return (
            f"ADA_LOCAL_MODE:{self.mode.value}",
            f"ADA_EXPLORATION_INTENSITY:{self.exploration_intensity:.2f}",
            f"ADA_TRAJECTORY_RECEIPT:{self.digest}",
        )

    def generation_guidance(self) -> tuple[str, ...]:
        direction = (
            "Explore a materially different local approach while preserving the parent lineage."
            if self.mode is AdaLocalMode.EXPLORE
            else "Refine the productive approach with a narrow, evidence-directed local change."
        )
        return (
            "ADA_TRAJECTORY_RECEIPT_V1=" + canonical_json(self),
            f"ADA_LOCAL_MODE:{self.mode.value};"
            f"EXPLORATION_INTENSITY:{self.exploration_intensity:.2f};"
            "GUIDANCE="
            + direction,
        )


class AdaTrajectoryPolicy:
    def __init__(self, config: AdaTrajectoryConfig | None = None) -> None:
        self.config = config or AdaTrajectoryConfig()

    def project(self, state: SearchState, branch_id: str | None) -> AdaTrajectoryReceipt:
        if branch_id is None:
            raise ValueError("Ada trajectory adaptation requires a selected branch")
        try:
            branch = next(item for item in state.branches if item.branch_id == branch_id)
        except StopIteration as error:
            raise ValueError("Ada trajectory branch is absent from the projected search state") from error
        trajectory = self._trajectory_state(state, branch)
        productive = (
            trajectory.accumulated_improvement_signal
            >= self.config.productive_signal_threshold
        )
        mode = AdaLocalMode.REFINE if productive else AdaLocalMode.EXPLORE
        intensity = (
            self.config.refine_intensity if productive else self.config.explore_intensity
        )
        return AdaTrajectoryReceipt(
            state=trajectory,
            config_digest=self.config.digest,
            mode=mode,
            exploration_intensity=intensity,
        )

    def verify_decision(
        self,
        state: SearchState,
        decision: SearchDecision,
    ) -> AdaTrajectoryReceipt:
        receipt = self.project(state, decision.branch_id)
        prefixes = (
            "ADA_LOCAL_MODE:",
            "ADA_EXPLORATION_INTENSITY:",
            "ADA_TRAJECTORY_RECEIPT:",
        )
        bound_codes = tuple(
            code for code in decision.reason_codes if code.startswith(prefixes)
        )
        if bound_codes != receipt.reason_codes:
            raise ValueError(
                "Ada decision is not bound to the projected trajectory receipt: "
                + ",".join(bound_codes)
            )
        return receipt

    def _trajectory_state(
        self,
        state: SearchState,
        branch: BranchSearchState,
    ) -> AdaTrajectoryState:
        window = branch.recent_improvements[-self.config.window_size :]
        if any(not math.isfinite(value) for value in window):
            raise ValueError("Ada trajectory improvements must be finite")
        accumulated = sum(
            max(0.0, improvement) * (self.config.decay**age)
            for age, improvement in enumerate(reversed(window))
        )
        sibling_outcomes = tuple(
            "IMPROVED" if value > 0 else "TIED" if value == 0 else "REGRESSED"
            for value in window
        )
        return AdaTrajectoryState(
            run_id=state.run_id,
            step=state.step,
            branch_id=branch.branch_id,
            parent_candidate_id=branch.parent_candidate_id,
            recent_improvements=window,
            accumulated_improvement_signal=round(accumulated, 12),
            generations_since_improvement=branch.generations_since_improvement,
            sibling_outcomes=sibling_outcomes,
            lineage_receipt_ids=branch.lineage_receipt_ids[-(self.config.window_size + 1) :],
        )
