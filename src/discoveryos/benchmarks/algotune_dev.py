from __future__ import annotations

import json
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from discoveryos.benchmarks.task_types import normalized_source
from discoveryos.util import digest_bytes, digest_json


ADAPTER_ID = "discoveryos.algotune_contract_dev.v1"
EVALUATOR_REGIME = "DISCOVERYOS_STDLIB_ALGOTUNE_CONTRACT_DEV_V1"
UPSTREAM_REVISION = "dff9914c10800c7a031c9e8c3d4d1c8cd1b38906"
UPSTREAM_BINDINGS = {
    "connected_components": {
        "upstream_task_sha256": "e13d1ead63a21df9973aab2484c717b780ea5621a98b0ccf28ab72e90c2fbe54",
        "upstream_description_sha256": "8dc6a9d49599c2ab56f9f16b24f022aa27b13e9f920e19bc95600ea59affe497",
    },
    "dijkstra": {
        "upstream_task_sha256": "6ee9caf07d82c05ac314de9cd19618736e6bc7aec047d6fbd074051c63d32cfd",
        "upstream_description_sha256": "6f0a06e1f8448103af94c0c8cfd43a8e6f01ab4746bec28bf10bad6d602d4e91",
    },
    "convolution_1d": {
        "upstream_task_sha256": "acd287ef6f098b8afafa057d646679aaa6df1a8489a78e22ea7193cce992d1bf",
        "upstream_description_sha256": "2ed13ea949fdb6d2bf2c9717962e410693f168a7a4abb30a6ee469cfa8e7000f",
    },
    "convex_hull": {
        "upstream_task_sha256": "e9bce689030869626ac2fd3ee04b013a3d25f1966f2aec396718e78749e525e3",
        "upstream_description_sha256": "770a4ab90394bbac2043ca1d21fa091de83c4dab61380fb557dc7251df3519c1",
    },
    "cholesky": {
        "upstream_task_sha256": "f5dca1c8d99056db791ab6096522f0c66fe544271055adff7c5cd267001f086d",
        "upstream_description_sha256": "b1e8aebd2feff5956c30de5e5d62b7316078c4fc53796e37baa8779551f5cbf7",
    },
    "linear_system_solver": {
        "upstream_task_sha256": "2d2b808301e127a1df9afd5ae83f1365710a8c9f0100d4630d64fd2a4b195571",
        "upstream_description_sha256": "3bdb4849718805985b639e7e115c6495ce5b5e0fec5dc71f56da185b85989bfd",
    },
}


@dataclass(frozen=True, slots=True)
class AlgoTuneDevSpec:
    family_id: str
    upstream_task: str
    instance_id: str
    seed: int
    scale: int
    initial_source: str
    public_tests_source: str
    evaluator_body: str


def _source(value: str) -> str:
    return normalized_source(textwrap.dedent(value).strip() + "\n")


CONNECTED_COMPONENTS = _source(
    """
    def solve(problem):
        n = problem["num_nodes"]
        adjacency = [[] for _ in range(n)]
        for left, right in problem["edges"]:
            adjacency[left].append(right)
            adjacency[right].append(left)
        seen = [False] * n
        components = 0
        for start in range(n):
            if seen[start]:
                continue
            components += 1
            seen[start] = True
            stack = [start]
            while stack:
                node = stack.pop()
                for neighbor in adjacency[node]:
                    if not seen[neighbor]:
                        seen[neighbor] = True
                        stack.append(neighbor)
        return {"number_connected_components": components}
    """
)

CONNECTED_COMPONENTS_PUBLIC = _source(
    """
    from algorithm import solve

    assert solve({"num_nodes": 5, "edges": [(0, 1), (2, 3), (3, 4)]}) == {
        "number_connected_components": 2
    }
    assert solve({"num_nodes": 4, "edges": []}) == {"number_connected_components": 4}
    """
)

CONNECTED_COMPONENTS_EVALUATOR = _source(
    """
    def make_cases(seed, scale):
        rng = random.Random(seed)
        cases = []
        for offset in range(4):
            n = scale + offset * 37
            component_count = 3 + offset
            buckets = [[] for _ in range(component_count)]
            order = list(range(n))
            rng.shuffle(order)
            for index, node in enumerate(order):
                buckets[index % component_count].append(node)
            edges = []
            for bucket in buckets:
                for index in range(1, len(bucket)):
                    parent = bucket[rng.randrange(index)]
                    edges.append((bucket[index], parent))
                for _ in range(len(bucket) // 2):
                    left, right = rng.sample(bucket, 2)
                    edges.append((left, right))
            cases.append({"num_nodes": n, "edges": edges})
        return cases

    def reference(problem):
        n = problem["num_nodes"]
        parent = list(range(n))
        def find(node):
            while parent[node] != node:
                parent[node] = parent[parent[node]]
                node = parent[node]
            return node
        for left, right in problem["edges"]:
            root_left, root_right = find(left), find(right)
            if root_left != root_right:
                parent[root_right] = root_left
        return len({find(node) for node in range(n)})

    def valid_solution(problem, actual, expected):
        return isinstance(actual, dict) and actual.get("number_connected_components") == expected
    """
)


DIJKSTRA = _source(
    """
    import heapq

    def solve(problem):
        n = problem["shape"][0]
        adjacency = [[] for _ in range(n)]
        data, indices, indptr = problem["data"], problem["indices"], problem["indptr"]
        for node in range(n):
            for cursor in range(indptr[node], indptr[node + 1]):
                adjacency[node].append((indices[cursor], float(data[cursor])))
        distances = [float("inf")] * n
        queue = []
        for source in problem["source_indices"]:
            distances[source] = 0.0
            heapq.heappush(queue, (0.0, source))
        while queue:
            distance, node = heapq.heappop(queue)
            if distance != distances[node]:
                continue
            for neighbor, weight in adjacency[node]:
                candidate = distance + weight
                if candidate < distances[neighbor]:
                    distances[neighbor] = candidate
                    heapq.heappush(queue, (candidate, neighbor))
        return {"distances": [[None if value == float("inf") else value for value in distances]]}
    """
)

DIJKSTRA_PUBLIC = _source(
    """
    from algorithm import solve

    problem = {
        "data": [2, 5, 2, 1, 5, 1],
        "indices": [1, 2, 0, 2, 0, 1],
        "indptr": [0, 2, 4, 6],
        "shape": [3, 3],
        "source_indices": [0],
    }
    assert solve(problem) == {"distances": [[0.0, 2.0, 3.0]]}
    """
)

DIJKSTRA_EVALUATOR = _source(
    """
    def make_cases(seed, scale):
        rng = random.Random(seed)
        cases = []
        for offset in range(3):
            n = scale + offset * 19
            rows = [dict() for _ in range(n)]
            for node in range(n - 1):
                weight = 1 + rng.randrange(20)
                rows[node][node + 1] = weight
                rows[node + 1][node] = weight
            for _ in range(n * 3):
                left, right = rng.sample(range(n), 2)
                weight = 1 + rng.randrange(50)
                rows[left][right] = min(rows[left].get(right, weight), weight)
                rows[right][left] = rows[left][right]
            data, indices, indptr = [], [], [0]
            for row in rows:
                for neighbor, weight in sorted(row.items()):
                    indices.append(neighbor)
                    data.append(weight)
                indptr.append(len(data))
            cases.append({
                "data": data,
                "indices": indices,
                "indptr": indptr,
                "shape": [n, n],
                "source_indices": sorted(rng.sample(range(n), 3)),
            })
        return cases

    def reference(problem):
        import heapq
        n = problem["shape"][0]
        rows = [[] for _ in range(n)]
        for node in range(n):
            for cursor in range(problem["indptr"][node], problem["indptr"][node + 1]):
                rows[node].append((problem["indices"][cursor], problem["data"][cursor]))
        distance = [float("inf")] * n
        queue = []
        for source in problem["source_indices"]:
            distance[source] = 0.0
            heapq.heappush(queue, (0.0, source))
        while queue:
            value, node = heapq.heappop(queue)
            if value != distance[node]:
                continue
            for neighbor, weight in rows[node]:
                candidate = value + weight
                if candidate < distance[neighbor]:
                    distance[neighbor] = candidate
                    heapq.heappush(queue, (candidate, neighbor))
        return distance

    def valid_solution(problem, actual, expected):
        if not isinstance(actual, dict) or not isinstance(actual.get("distances"), list):
            return False
        rows = actual["distances"]
        if len(rows) != 1 or len(rows[0]) != len(expected):
            return False
        for observed, wanted in zip(rows[0], expected):
            if wanted == float("inf"):
                if observed is not None:
                    return False
            elif not isinstance(observed, (int, float)) or abs(observed - wanted) > 1e-9:
                return False
        return True
    """
)


CONVOLVE = _source(
    """
    def solve(problem):
        left, right = problem
        output = [0.0] * (len(left) + len(right) - 1)
        for left_index, left_value in enumerate(left):
            for right_index, right_value in enumerate(right):
                output[left_index + right_index] += left_value * right_value
        return output
    """
)

CONVOLVE_PUBLIC = _source(
    """
    from algorithm import solve

    assert solve(([1.0, 2.0, 3.0], [4.0, 5.0])) == [4.0, 13.0, 22.0, 15.0]
    assert solve(([2.0], [3.0])) == [6.0]
    """
)

CONVOLVE_EVALUATOR = _source(
    """
    def make_cases(seed, scale):
        rng = random.Random(seed)
        return [
            ([rng.uniform(-2.0, 2.0) for _ in range(scale + offset * 17)],
             [rng.uniform(-1.0, 1.0) for _ in range(31 + offset * 8)])
            for offset in range(4)
        ]

    def reference(problem):
        left, right = problem
        output = [0.0] * (len(left) + len(right) - 1)
        for i, left_value in enumerate(left):
            for j, right_value in enumerate(right):
                output[i + j] += left_value * right_value
        return output

    def valid_solution(problem, actual, expected):
        return (
            isinstance(actual, list)
            and len(actual) == len(expected)
            and all(isinstance(value, (int, float)) and math.isfinite(value) for value in actual)
            and max((abs(value - wanted) for value, wanted in zip(actual, expected)), default=0.0) <= 1e-8
        )
    """
)


CONVEX_HULL = _source(
    """
    def solve(problem):
        points = problem["points"]
        indexed = sorted((point[0], point[1], index) for index, point in enumerate(points))
        def cross(origin, left, right):
            return (left[0] - origin[0]) * (right[1] - origin[1]) - (left[1] - origin[1]) * (right[0] - origin[0])
        lower = []
        for point in indexed:
            while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
                lower.pop()
            lower.append(point)
        upper = []
        for point in reversed(indexed):
            while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
                upper.pop()
            upper.append(point)
        hull = lower[:-1] + upper[:-1]
        vertices = [point[2] for point in hull]
        return {"hull_vertices": vertices, "hull_points": [points[index] for index in vertices]}
    """
)

CONVEX_HULL_PUBLIC = _source(
    """
    from algorithm import solve

    points = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0], [0.5, 0.5]]
    result = solve({"points": points})
    assert set(result["hull_vertices"]) == {0, 1, 2, 3}
    assert len(result["hull_points"]) == 4
    """
)

CONVEX_HULL_EVALUATOR = _source(
    """
    def make_cases(seed, scale):
        rng = random.Random(seed)
        cases = []
        for offset in range(4):
            points = [[rng.random(), rng.random()] for _ in range(scale + offset * 71)]
            points.extend([[-1.0, -1.0], [2.0, -1.0], [2.0, 2.0], [-1.0, 2.0]])
            cases.append({"points": points})
        return cases

    def reference(problem):
        points = problem["points"]
        ordered = sorted((point[0], point[1], index) for index, point in enumerate(points))
        def cross(origin, left, right):
            return (left[0] - origin[0]) * (right[1] - origin[1]) - (left[1] - origin[1]) * (right[0] - origin[0])
        lower = []
        for point in ordered:
            while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
                lower.pop()
            lower.append(point)
        upper = []
        for point in reversed(ordered):
            while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
                upper.pop()
            upper.append(point)
        return {point[2] for point in lower[:-1] + upper[:-1]}

    def valid_solution(problem, actual, expected):
        if not isinstance(actual, dict):
            return False
        vertices, hull_points = actual.get("hull_vertices"), actual.get("hull_points")
        if not isinstance(vertices, list) or not isinstance(hull_points, list) or len(vertices) != len(hull_points):
            return False
        if set(vertices) != expected or len(vertices) != len(set(vertices)):
            return False
        return all(problem["points"][index] == point for index, point in zip(vertices, hull_points))
    """
)


CHOLESKY = _source(
    """
    import math

    def solve(problem):
        matrix = problem["matrix"]
        n = len(matrix)
        lower = [[0.0] * n for _ in range(n)]
        for row in range(n):
            for column in range(row + 1):
                residual = matrix[row][column] - sum(lower[row][k] * lower[column][k] for k in range(column))
                if row == column:
                    lower[row][column] = math.sqrt(residual)
                else:
                    lower[row][column] = residual / lower[column][column]
        return {"Cholesky": {"L": lower}}
    """
)

CHOLESKY_PUBLIC = _source(
    """
    from algorithm import solve

    result = solve({"matrix": [[4.0, 2.0], [2.0, 3.0]]})["Cholesky"]["L"]
    assert abs(result[0][0] - 2.0) < 1e-12
    assert abs(result[1][0] - 1.0) < 1e-12
    assert abs(result[1][1] - 2.0 ** 0.5) < 1e-12
    """
)

CHOLESKY_EVALUATOR = _source(
    """
    def make_cases(seed, scale):
        rng = random.Random(seed)
        cases = []
        for offset in range(3):
            n = scale + offset * 3
            base = [[rng.uniform(-1.0, 1.0) for _ in range(n)] for _ in range(n)]
            matrix = [[sum(base[row][k] * base[column][k] for k in range(n)) + (n if row == column else 0.0) for column in range(n)] for row in range(n)]
            cases.append({"matrix": matrix})
        return cases

    def reference(problem):
        return problem["matrix"]

    def valid_solution(problem, actual, expected):
        if not isinstance(actual, dict) or not isinstance(actual.get("Cholesky"), dict):
            return False
        lower = actual["Cholesky"].get("L")
        n = len(expected)
        if not isinstance(lower, list) or len(lower) != n or any(not isinstance(row, list) or len(row) != n for row in lower):
            return False
        if any(abs(lower[row][column]) > 1e-10 for row in range(n) for column in range(row + 1, n)):
            return False
        for row in range(n):
            for column in range(n):
                reconstructed = sum(lower[row][k] * lower[column][k] for k in range(n))
                if not math.isfinite(reconstructed) or abs(reconstructed - expected[row][column]) > 1e-7:
                    return False
        return True
    """
)


LINEAR_SOLVER = _source(
    """
    def solve(problem):
        matrix = [list(row) for row in problem["A"]]
        vector = list(problem["b"])
        n = len(vector)
        for pivot in range(n):
            best = max(range(pivot, n), key=lambda row: abs(matrix[row][pivot]))
            matrix[pivot], matrix[best] = matrix[best], matrix[pivot]
            vector[pivot], vector[best] = vector[best], vector[pivot]
            divisor = matrix[pivot][pivot]
            for column in range(pivot, n):
                matrix[pivot][column] /= divisor
            vector[pivot] /= divisor
            for row in range(pivot + 1, n):
                factor = matrix[row][pivot]
                for column in range(pivot, n):
                    matrix[row][column] -= factor * matrix[pivot][column]
                vector[row] -= factor * vector[pivot]
        solution = [0.0] * n
        for row in range(n - 1, -1, -1):
            solution[row] = vector[row] - sum(matrix[row][column] * solution[column] for column in range(row + 1, n))
        return solution
    """
)

LINEAR_SOLVER_PUBLIC = _source(
    """
    from algorithm import solve

    result = solve({"A": [[3.0, 1.0], [1.0, 2.0]], "b": [9.0, 8.0]})
    assert abs(result[0] - 2.0) < 1e-12
    assert abs(result[1] - 3.0) < 1e-12
    """
)

LINEAR_SOLVER_EVALUATOR = _source(
    """
    def make_cases(seed, scale):
        rng = random.Random(seed)
        cases = []
        for offset in range(3):
            n = scale + offset * 3
            matrix = [[rng.uniform(-1.0, 1.0) for _ in range(n)] for _ in range(n)]
            for row in range(n):
                matrix[row][row] += n
            expected = [rng.uniform(-2.0, 2.0) for _ in range(n)]
            vector = [sum(matrix[row][column] * expected[column] for column in range(n)) for row in range(n)]
            cases.append({"A": matrix, "b": vector})
        return cases

    def reference(problem):
        return problem

    def valid_solution(problem, actual, expected):
        n = len(problem["b"])
        if not isinstance(actual, list) or len(actual) != n or not all(isinstance(value, (int, float)) and math.isfinite(value) for value in actual):
            return False
        residual = max(abs(sum(problem["A"][row][column] * actual[column] for column in range(n)) - problem["b"][row]) for row in range(n))
        return residual <= 1e-7
    """
)


_FAMILY_SOURCES = {
    "connected_components": ("count_connected_components", CONNECTED_COMPONENTS, CONNECTED_COMPONENTS_PUBLIC, CONNECTED_COMPONENTS_EVALUATOR, 900),
    "dijkstra": ("dijkstra_from_indices", DIJKSTRA, DIJKSTRA_PUBLIC, DIJKSTRA_EVALUATOR, 120),
    "convolution_1d": ("convolve_1d", CONVOLVE, CONVOLVE_PUBLIC, CONVOLVE_EVALUATOR, 260),
    "convex_hull": ("convex_hull", CONVEX_HULL, CONVEX_HULL_PUBLIC, CONVEX_HULL_EVALUATOR, 700),
    "cholesky": ("cholesky_factorization", CHOLESKY, CHOLESKY_PUBLIC, CHOLESKY_EVALUATOR, 26),
    "linear_system_solver": ("linear_system_solver", LINEAR_SOLVER, LINEAR_SOLVER_PUBLIC, LINEAR_SOLVER_EVALUATOR, 28),
}


def _evaluator_source(body: str, *, seed: int, scale: int) -> str:
    harness = f"""
import copy
import json
import math
import random
import statistics
import time

from algorithm import solve

SEED = {seed}
SCALE = {scale}
EVALUATOR_REGIME = {EVALUATOR_REGIME!r}

{body}

cases = make_cases(SEED, SCALE)
expected = [reference(copy.deepcopy(problem)) for problem in cases]
valid = True
error = None
try:
    for problem, wanted in zip(cases, expected):
        frozen = copy.deepcopy(problem)
        actual = solve(problem)
        valid = valid and problem == frozen and valid_solution(frozen, actual, wanted)
except Exception as exc:
    valid = False
    error = type(exc).__name__

timings = []
if valid:
    for _ in range(5):
        started = time.perf_counter()
        for problem in cases:
            solve(copy.deepcopy(problem))
        timings.append(time.perf_counter() - started)
median_runtime_ms = statistics.median(timings) * 1000.0 if timings else None
score = 1.0 / (1.0 + median_runtime_ms) if valid and median_runtime_ms is not None else 0.0
print(json.dumps({{
    "metrics": {{
        "score": score,
        "valid": float(valid),
        "median_runtime_ms": median_runtime_ms,
        "case_count": len(cases),
    }},
    "evaluator_regime": EVALUATOR_REGIME,
    "error": error,
}}, sort_keys=True))
"""
    return _source(harness)


def algotune_dev_specs() -> dict[tuple[str, str], AlgoTuneDevSpec]:
    specs: dict[tuple[str, str], AlgoTuneDevSpec] = {}
    for family_id, (upstream_task, initial, public, evaluator, base_scale) in _FAMILY_SOURCES.items():
        for suffix, seed, scale_offset in (("alpha", 1103, 0), ("beta", 2207, 11)):
            instance_id = f"{family_id}_dev_{suffix}"
            specs[(family_id, instance_id)] = AlgoTuneDevSpec(
                family_id=family_id,
                upstream_task=upstream_task,
                instance_id=instance_id,
                seed=seed,
                scale=base_scale + scale_offset,
                initial_source=initial,
                public_tests_source=public,
                evaluator_body=evaluator,
            )
    return specs


def materialize_algotune_dev(
    family: dict[str, Any],
    instance_id: str,
    output_dir: Path,
) -> dict[str, Any]:
    spec = algotune_dev_specs().get((family["family_id"], instance_id))
    if spec is None or instance_id not in family.get("instance_ids", []):
        raise ValueError(f"instance is not registered for family: {instance_id}")
    if family.get("upstream_task") != spec.upstream_task:
        raise RuntimeError("registered AlgoTune upstream task binding drift")
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    initial = output_dir / "algorithm.py"
    public_tests = output_dir / "public_tests.py"
    evaluator = output_dir / "evaluate.py"
    contract = output_dir / "task-contract.json"
    initial.write_text(spec.initial_source, encoding="utf-8")
    public_tests.write_text(spec.public_tests_source, encoding="utf-8")
    evaluator.write_text(_evaluator_source(spec.evaluator_body, seed=spec.seed, scale=spec.scale), encoding="utf-8")
    contract_payload = {
        "schema_version": 1,
        "family_id": spec.family_id,
        "instance_id": spec.instance_id,
        "source_id": "algotune",
        "source_revision": UPSTREAM_REVISION,
        "upstream_task": spec.upstream_task,
        "upstream_task_sha256": family["development_binding"]["upstream_task_sha256"],
        "upstream_description_sha256": family["development_binding"]["upstream_description_sha256"],
        "adapter_id": ADAPTER_ID,
        "evaluator_regime": EVALUATOR_REGIME,
        "upstream_evaluator_reused": False,
        "dependency_profile": "PYTHON_3_11_STANDARD_LIBRARY_ONLY",
        "partition_role": "DEV",
        "seed": spec.seed,
        "scale": spec.scale,
        "claim_ceiling": "EXTERNAL_CONTRACT_DERIVED_DEVELOPMENT_ONLY",
    }
    contract.write_text(json.dumps(contract_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    instance_payload = {
        **contract_payload,
        "initial_program_sha256": digest_bytes(initial.read_bytes()),
        "public_tests_sha256": digest_bytes(public_tests.read_bytes()),
        "evaluator_sha256": digest_bytes(evaluator.read_bytes()),
        "task_contract_sha256": digest_bytes(contract.read_bytes()),
    }
    (output_dir / "bank-instance.json").write_text(
        json.dumps(instance_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "family_id": spec.family_id,
        "instance_id": spec.instance_id,
        "initial_program_path": str(initial),
        "public_tests_path": str(public_tests),
        "evaluator_path": str(evaluator),
        "evaluator_digest": instance_payload["evaluator_sha256"],
        "instance_digest": digest_json(instance_payload),
        "claim_ceiling": contract_payload["claim_ceiling"],
        "adapter_id": ADAPTER_ID,
        "source_revision": UPSTREAM_REVISION,
        "evaluator_regime": EVALUATOR_REGIME,
        "task_contract_path": str(contract),
    }
