from __future__ import annotations

import hashlib

from discoveryos.benchmarks.search_value_mvp0_tasks import SearchValueTask
from discoveryos.benchmarks.si2_tasks import _assignment_task, _coverage_task


PROTOCOL_SALT = "CMI_R7_FRESH_CAUSAL_REPLICATION_V1"
TASKS_PER_FAMILY = 3
EVALUATOR_CASES_PER_STATE = 6


def cmi_r7_fresh_tasks() -> tuple[SearchValueTask, ...]:
    """Return the complete preregistered R7 neighboring-hidden population.

    Seeds are derived without screening from the protocol salt, family, state,
    and case indexes.  The construction deliberately reuses the frozen SI-2
    evaluator regime while creating exact instances that were never part of
    CMI-R3 through CMI-R6.
    """

    assignment = tuple(
        _assignment_task(
            f"cmi_r7_assignment_{state_index + 1:02d}",
            _derived_seeds("capacitated_cost_assignment", state_index),
        )
        for state_index in range(TASKS_PER_FAMILY)
    )
    coverage = tuple(
        _coverage_task(
            f"cmi_r7_coverage_{state_index + 1:02d}",
            _derived_seeds("budgeted_weighted_coverage", state_index),
        )
        for state_index in range(TASKS_PER_FAMILY)
    )
    return assignment + coverage


def _derived_seeds(family: str, state_index: int) -> tuple[int, ...]:
    seeds = []
    for case_index in range(EVALUATOR_CASES_PER_STATE):
        identity = f"{PROTOCOL_SALT}:{family}:{state_index}:{case_index}".encode("utf-8")
        seed = 100_000 + int.from_bytes(hashlib.sha256(identity).digest()[:8], "big") % 800_000
        seeds.append(seed)
    if len(set(seeds)) != len(seeds):
        raise RuntimeError("CMI-R7 deterministic seed derivation collided")
    return tuple(seeds)
