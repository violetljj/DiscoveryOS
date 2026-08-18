from __future__ import annotations

import copy
import itertools
import json
import math
import pickle
import random
import statistics
import sys
import textwrap
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from discoveryos.benchmarks.algotune_dev import (
    UPSTREAM_BINDINGS as V1_BINDINGS,
    UPSTREAM_REVISION,
    algotune_dev_specs,
)
from discoveryos.benchmarks.algotune_p2v4_dev import (
    UPSTREAM_BINDINGS as V4_BINDINGS,
    p2v4_dev_specs,
)
from discoveryos.benchmarks.algotune_r2_dev import (
    UPSTREAM_BINDINGS as R2_BINDINGS,
    r2_specs,
)
from discoveryos.benchmarks.task_types import normalized_source
from discoveryos.util import digest_bytes, digest_json


ADAPTER_ID = "discoveryos.algotune_p2v41_deterministic_dev.v1"
EVALUATOR_REGIME = "DISCOVERYOS_P2V41_DETERMINISTIC_OPCODE_DEV_V1"
PYTHON_RUNTIME = "CPYTHON_3_11"


def _normalized_bindings() -> dict[str, tuple[str, str]]:
    result = dict(R2_BINDINGS)
    result.update(V4_BINDINGS)
    result.update(
        {
            family_id: (
                binding["upstream_task_sha256"],
                binding["upstream_description_sha256"],
            )
            for family_id, binding in V1_BINDINGS.items()
        }
    )
    return result


UPSTREAM_BINDINGS = _normalized_bindings()


@dataclass(frozen=True, slots=True)
class DeterministicCalibration:
    baseline_opcode_count: int
    linear_lookup_opcode_count: int
    direct_lookup_opcode_count: int
    score_resolution: int
    baseline_score: int
    intermediate_scores: tuple[int, int]
    reference_score: int
    headroom_steps: float
    linear_lookup_source: str
    direct_lookup_source: str


def _specs() -> dict[tuple[str, str], Any]:
    return {**algotune_dev_specs(), **r2_specs(), **p2v4_dev_specs()}


def _execution_namespace(evaluator_body: str, solve: Callable[[Any], Any]) -> dict[str, Any]:
    namespace = {
        "copy": copy,
        "itertools": itertools,
        "json": json,
        "math": math,
        "random": random,
        "statistics": statistics,
        "time": time,
        "solve": solve,
    }
    exec(compile(evaluator_body, "p2v41-evaluator-body.py", "exec"), namespace)
    return namespace


def _load_solve(source: str) -> Callable[[Any], Any]:
    namespace: dict[str, Any] = {}
    exec(compile(source, "algorithm.py", "exec"), namespace)
    solve = namespace.get("solve")
    if not callable(solve):
        raise RuntimeError("P2 V4.1 calibration source does not define solve(problem)")
    return solve


def _opcode_call(solve: Callable[[Any], Any], problem: Any) -> tuple[Any, int, Any]:
    count = 0
    working = copy.deepcopy(problem)
    frozen = copy.deepcopy(working)

    def trace(frame, event, _argument):
        nonlocal count
        if event == "call" and Path(frame.f_code.co_filename).name == "algorithm.py":
            frame.f_trace_opcodes = True
            return trace
        if event == "opcode" and Path(frame.f_code.co_filename).name == "algorithm.py":
            count += 1
        return trace

    sys.settrace(trace)
    try:
        actual = solve(working)
    finally:
        sys.settrace(None)
    return actual, count, working == frozen


def _lookup_sources(cases: tuple[Any, ...], outputs: tuple[Any, ...]) -> tuple[str, str]:
    pairs = tuple(
        (pickle.dumps(problem, protocol=4), pickle.dumps(output, protocol=4))
        for problem, output in zip(cases, outputs, strict=True)
    )
    direct = normalized_source(
        "import pickle\n"
        + "_TABLE = {\n"
        + "".join(f"    {key!r}: {value!r},\n" for key, value in pairs)
        + "}\n\n"
        + "def solve(problem):\n"
        + "    key = pickle.dumps(problem, protocol=4)\n"
        + "    return pickle.loads(_TABLE[key])\n"
    )
    linear = normalized_source(
        "import pickle\n"
        + "_TABLE = (\n"
        + "".join(f"    ({key!r}, {value!r}),\n" for key, value in pairs)
        + ")\n\n"
        + "def solve(problem):\n"
        + "    key = pickle.dumps(problem, protocol=4)\n"
        + "    for candidate_key, value in _TABLE:\n"
        + "        if candidate_key == key:\n"
        + "            return pickle.loads(value)\n"
        + "    raise KeyError('unregistered deterministic DEV case')\n"
    )
    return linear, direct


def calibrate_spec(spec: Any) -> DeterministicCalibration:
    baseline_solve = _load_solve(spec.initial_source)
    evaluator = _execution_namespace(spec.evaluator_body, baseline_solve)
    cases = tuple(evaluator["make_cases"](spec.seed, spec.scale))
    outputs: list[Any] = []
    baseline_count = 0
    for problem in cases:
        wanted = evaluator["reference"](copy.deepcopy(problem))
        actual, count, unchanged = _opcode_call(baseline_solve, problem)
        if not unchanged or not evaluator["valid_solution"](copy.deepcopy(problem), actual, wanted):
            raise RuntimeError(f"P2 V4.1 baseline calibration invalid: {spec.instance_id}")
        outputs.append(actual)
        baseline_count += count

    linear_source, direct_source = _lookup_sources(cases, tuple(outputs))
    calibration_counts: list[int] = []
    for label, source in (("linear", linear_source), ("direct", direct_source)):
        solve = _load_solve(source)
        count = 0
        for problem in cases:
            wanted = evaluator["reference"](copy.deepcopy(problem))
            actual, observed, unchanged = _opcode_call(solve, problem)
            if not unchanged or not evaluator["valid_solution"](copy.deepcopy(problem), actual, wanted):
                raise RuntimeError(
                    f"P2 V4.1 {label} calibration invalid: {spec.instance_id}"
                )
            count += observed
        calibration_counts.append(count)

    improved = sorted({count for count in calibration_counts if count < baseline_count}, reverse=True)
    if len(improved) != 2:
        raise RuntimeError(
            f"P2 V4.1 requires two distinct improved calibration programs: {spec.instance_id}"
        )
    worse_count, best_count = improved
    best_gap = baseline_count - best_count
    first_gap = baseline_count - worse_count
    between_gap = worse_count - best_count
    resolution = min(best_gap // 4, first_gap, between_gap)
    if resolution < 1:
        raise RuntimeError(f"P2 V4.1 calibration lacks four-step headroom: {spec.instance_id}")
    return DeterministicCalibration(
        baseline_opcode_count=baseline_count,
        linear_lookup_opcode_count=calibration_counts[0],
        direct_lookup_opcode_count=calibration_counts[1],
        score_resolution=resolution,
        baseline_score=-baseline_count,
        intermediate_scores=(-worse_count, -best_count),
        reference_score=-best_count,
        headroom_steps=best_gap / resolution,
        linear_lookup_source=linear_source,
        direct_lookup_source=direct_source,
    )


def _evaluator_source(body: str, *, seed: int, scale: int, resolution: int) -> str:
    prefix = textwrap.dedent(
        f"""
        import copy
        import itertools
        import json
        import math
        import os
        import random
        import statistics
        import sys
        import algorithm

        solve = algorithm.solve
        SEED = {seed}
        SCALE = {scale}
        SCORE_RESOLUTION = {resolution}
        EVALUATOR_REGIME = {EVALUATOR_REGIME!r}
        ALGORITHM_FILE = os.path.normcase(os.path.abspath(algorithm.__file__))
        """
    ).strip()
    footer = textwrap.dedent(
        """
        def measured_solve(problem):
            count = 0
            working = copy.deepcopy(problem)
            frozen = copy.deepcopy(working)
            def trace(frame, event, argument):
                nonlocal count
                if event == "call" and os.path.normcase(os.path.abspath(frame.f_code.co_filename)) == ALGORITHM_FILE:
                    frame.f_trace_opcodes = True
                    return trace
                if event == "opcode" and os.path.normcase(os.path.abspath(frame.f_code.co_filename)) == ALGORITHM_FILE:
                    count += 1
                return trace
            sys.settrace(trace)
            try:
                actual = solve(working)
            finally:
                sys.settrace(None)
            return actual, count, working == frozen

        cases = make_cases(SEED, SCALE)
        expected = [reference(copy.deepcopy(problem)) for problem in cases]
        valid, error, total_opcodes = True, None, 0
        try:
            for problem, wanted in zip(cases, expected):
                actual, opcodes, unchanged = measured_solve(problem)
                total_opcodes += opcodes
                valid = valid and unchanged and valid_solution(copy.deepcopy(problem), actual, wanted)
        except Exception as exc:
            valid, error = False, type(exc).__name__
        score = -float(total_opcodes) if valid else -1.0e30
        print(json.dumps({
            "metrics": {
                "score": score,
                "valid": float(valid),
                "algorithm_opcode_count": total_opcodes,
                "score_resolution": SCORE_RESOLUTION,
                "case_count": len(cases),
            },
            "evaluator_regime": EVALUATOR_REGIME,
            "python_runtime": "CPYTHON_3_11",
            "error": error,
        }, sort_keys=True))
        """
    ).strip()
    return normalized_source(prefix + "\n\n" + body + "\n\n" + footer + "\n")


def materialize_p2v41_dev(
    family: dict[str, Any], instance_id: str, output_dir: Path
) -> dict[str, Any]:
    spec = _specs().get((family["family_id"], instance_id))
    if spec is None or instance_id not in family.get("instance_ids", []):
        raise ValueError(f"instance is not registered for family: {instance_id}")
    if family.get("upstream_task") != spec.upstream_task:
        raise RuntimeError("registered AlgoTune P2 V4.1 upstream task binding drift")
    calibration = calibrate_spec(spec)
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    initial = output_dir / "algorithm.py"
    public = output_dir / "public_tests.py"
    evaluator = output_dir / "evaluate.py"
    contract = output_dir / "task-contract.json"
    initial.write_text(spec.initial_source, encoding="utf-8")
    public.write_text(spec.public_tests_source, encoding="utf-8")
    evaluator.write_text(
        _evaluator_source(
            spec.evaluator_body,
            seed=spec.seed,
            scale=spec.scale,
            resolution=calibration.score_resolution,
        ),
        encoding="utf-8",
    )
    binding = family["development_binding"]
    contract_payload = {
        "schema_version": 2,
        "family_id": spec.family_id,
        "instance_id": spec.instance_id,
        "source_id": "algotune",
        "source_revision": UPSTREAM_REVISION,
        "upstream_task": spec.upstream_task,
        "upstream_task_sha256": binding["upstream_task_sha256"],
        "upstream_description_sha256": binding["upstream_description_sha256"],
        "adapter_id": ADAPTER_ID,
        "evaluator_regime": EVALUATOR_REGIME,
        "upstream_evaluator_reused": False,
        "dependency_profile": "CPYTHON_3_11_STANDARD_LIBRARY_ONLY",
        "partition_role": "DEV",
        "seed": spec.seed,
        "scale": spec.scale,
        "score_direction": "maximize",
        "score_semantics": "negative deterministic executed Python opcode count in algorithm.py",
        "score_resolution": calibration.score_resolution,
        "baseline_score": calibration.baseline_score,
        "intermediate_scores": calibration.intermediate_scores,
        "reference_score": calibration.reference_score,
        "headroom_steps": calibration.headroom_steps,
        "calibration_source_digests": {
            "linear_lookup": digest_bytes(calibration.linear_lookup_source.encode("utf-8")),
            "direct_lookup": digest_bytes(calibration.direct_lookup_source.encode("utf-8")),
        },
        "calibration_role": "FIXED_CASE_LOOKUP_HEADROOM_ONLY_NOT_A_SCIENTIFIC_CANDIDATE",
        "claim_ceiling": "EXTERNAL_CONTRACT_DERIVED_DEVELOPMENT_ONLY",
    }
    contract.write_text(json.dumps(contract_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    payload = {
        **contract_payload,
        "initial_program_sha256": digest_bytes(initial.read_bytes()),
        "public_tests_sha256": digest_bytes(public.read_bytes()),
        "evaluator_sha256": digest_bytes(evaluator.read_bytes()),
        "task_contract_sha256": digest_bytes(contract.read_bytes()),
    }
    (output_dir / "bank-instance.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {
        "family_id": spec.family_id,
        "instance_id": spec.instance_id,
        "initial_program_path": str(initial),
        "public_tests_path": str(public),
        "evaluator_path": str(evaluator),
        "evaluator_digest": payload["evaluator_sha256"],
        "instance_digest": digest_json(payload),
        "claim_ceiling": contract_payload["claim_ceiling"],
        "adapter_id": ADAPTER_ID,
        "source_revision": UPSTREAM_REVISION,
        "evaluator_regime": EVALUATOR_REGIME,
        "task_contract_path": str(contract),
    }
