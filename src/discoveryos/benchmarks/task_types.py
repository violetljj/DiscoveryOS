from __future__ import annotations

import textwrap
from dataclasses import dataclass

from discoveryos.benchmarks.real_code_tasks import RealCodeTask
from discoveryos.util import digest_json


@dataclass(frozen=True, slots=True)
class SearchValueTask:
    """Protocol-neutral executable optimization task used by the Benchmark Bank."""

    task: RealCodeTask
    reference_source: str
    intermediate_sources: tuple[str, ...]
    score_resolution: float
    baseline_basin_id: str
    trajectory_classes: tuple[str, ...]

    @property
    def payload_digest(self) -> str:
        return digest_json(self)


def normalized_source(source: str) -> str:
    return textwrap.dedent(source).strip() + "\n"
