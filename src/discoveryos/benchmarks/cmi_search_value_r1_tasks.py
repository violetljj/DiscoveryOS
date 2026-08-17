from __future__ import annotations

import hashlib

from discoveryos.benchmarks.search_value_mvp0_tasks import SearchValueTask
from discoveryos.benchmarks.si2_tasks import _assignment_task, _coverage_task


PROTOCOL_SALT = "CMI_SEARCH_VALUE_R1_V3_INVALID_DESCENDANT_TERMINALIZATION"
TASKS_PER_FAMILY = 3
EVALUATOR_CASES_PER_TASK = 6


def cmi_search_value_r1_tasks() -> tuple[SearchValueTask, ...]:
    """Return the complete unscreened fresh population for CMI Search Value R1."""

    assignment = tuple(
        _assignment_task(
            f"cmi_svr3_assignment_{index + 1:02d}",
            _derived_seeds("capacitated_cost_assignment", index),
        )
        for index in range(TASKS_PER_FAMILY)
    )
    coverage = tuple(
        _coverage_task(
            f"cmi_svr3_coverage_{index + 1:02d}",
            _derived_seeds("budgeted_weighted_coverage", index),
        )
        for index in range(TASKS_PER_FAMILY)
    )
    return assignment + coverage


def probe_seeds(task_id: str) -> tuple[int, ...]:
    return tuple(_derive_integer(f"probe:{task_id}:{index}") for index in range(3))


def _derived_seeds(family: str, task_index: int) -> tuple[int, ...]:
    seeds = tuple(
        _derive_integer(f"evaluator:{family}:{task_index}:{case_index}")
        for case_index in range(EVALUATOR_CASES_PER_TASK)
    )
    if len(set(seeds)) != len(seeds):
        raise RuntimeError("CMI Search Value R1 seed derivation collided")
    return seeds


def _derive_integer(identity: str) -> int:
    payload = f"{PROTOCOL_SALT}:{identity}".encode("utf-8")
    return 100_000 + int.from_bytes(hashlib.sha256(payload).digest()[:8], "big") % 800_000
