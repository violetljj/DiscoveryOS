from __future__ import annotations

import json
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from discoveryos.benchmarks.algotune_dev import UPSTREAM_REVISION
from discoveryos.benchmarks.task_types import normalized_source
from discoveryos.util import digest_bytes, digest_json


ADAPTER_ID = "discoveryos.algotune_p2v4_contract_dev.v1"
EVALUATOR_REGIME = "DISCOVERYOS_STDLIB_ALGOTUNE_P2V4_CONTRACT_DEV_V1"
UPSTREAM_BINDINGS = {
    "affine_transform_2d": (
        "0389e5138c597eec863a56cf2569cab77abb611543ba595f8e97df1cbe2c942a",
        "52d69436acff84eac9ba5e43fb86e7cc730fa87114dccb3cb86d08e5332ad636",
    ),
    "eigenvalues_real": (
        "a116e91af7999fa65a57124f8f3bb7bc3d41b3af353e999c844f6153e538fcad",
        "939651ec2a2fbb636a33e74d19894c3f9e16768e6470b41016c264b0d7f958c3",
    ),
    "minimum_spanning_tree": (
        "39eb67083c6b1352934f4f99bb066748332aab90a54d5e358f436e9ea0e2a191",
        "827e0563e5cacdd489469baa49cdf1e917feb079335b08586add4aa01243f35b",
    ),
    "least_squares": (
        "a47729ffd18fe1054f867b0d1947c247c649ca1652dd49b5281f5b02e8f5bf64",
        "96df24b83b0ec2ed360879fac04175ac89183c5ec4c3dabbdd156cd10a647a1f",
    ),
    "fft_convolution": (
        "bcc2e9064e7bbcda0cf77e34307347c51e8aaa5ca2429202ee4b3b8651939a1f",
        "b7a752d14c9b48ada07941c748ac846dc16dd659d92ca29469b72a51c20c2c92",
    ),
    "min_weight_assignment": (
        "4f61ea137f2261cfa3a3005e35a3b0a293afeb9a4b1a82fb8ddd106cd4d79b6d",
        "7a31179814e8cc033fbcfa33ce4aa9a3238bddda5765e60651f880717078be89",
    ),
    "vertex_cover": (
        "edd7269b888d95f7e071af9260baefca89830a14e0ea578bc631895e04745a01",
        "a386a127893aa5bff7e0aae9b38c932b98fc3c9addda23ecae36f839e871a60e",
    ),
    "tsp": (
        "e12407b6cd3351e54d1ff31b09a88491e4e0a2331fd2e1b559ac24bc64aa1522",
        "35013aca79eb9a085a0eaf3009dc1f32c51ec460ae58202e8bf6ce5aba4dc92f",
    ),
}


@dataclass(frozen=True, slots=True)
class P2V4DevSpec:
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


AFFINE = _source(
    """
    def solve(problem):
        image = problem["image"]
        matrix = problem["matrix"]
        rows = len(image)
        columns = len(image[0]) if rows else 0
        output = [[0.0] * columns for _ in range(rows)]
        for row in range(rows):
            for column in range(columns):
                source_row = matrix[0][0] * row + matrix[0][1] * column + matrix[0][2]
                source_column = matrix[1][0] * row + matrix[1][1] * column + matrix[1][2]
                nearest_row, nearest_column = round(source_row), round(source_column)
                if (
                    abs(source_row - nearest_row) <= 1e-12
                    and abs(source_column - nearest_column) <= 1e-12
                    and 0 <= nearest_row < rows
                    and 0 <= nearest_column < columns
                ):
                    output[row][column] = float(image[nearest_row][nearest_column])
        return {"transformed_image": output}
    """
)
AFFINE_PUBLIC = _source(
    """
    from algorithm import solve
    image = [[1.0, 2.0], [3.0, 4.0]]
    assert solve({"image": image, "matrix": [[1, 0, 0], [0, 1, 0]]}) == {"transformed_image": image}
    assert solve({"image": image, "matrix": [[-1, 0, 1], [0, 1, 0]]}) == {"transformed_image": [[3.0, 4.0], [1.0, 2.0]]}
    """
)
AFFINE_EVAL = _source(
    """
    def make_cases(seed, scale):
        rng = random.Random(seed)
        image = [[float(rng.randrange(256)) for _ in range(scale)] for _ in range(scale)]
        return [
            {"image": image, "matrix": [[1, 0, 0], [0, 1, 0]]},
            {"image": image, "matrix": [[-1, 0, scale - 1], [0, 1, 0]]},
            {"image": image, "matrix": [[1, 0, 1], [0, 1, -1]]},
        ]
    def reference(problem):
        image, matrix = problem["image"], problem["matrix"]
        rows, columns = len(image), len(image[0])
        expected = [[0.0] * columns for _ in range(rows)]
        for row in range(rows):
            for column in range(columns):
                source_row = int(matrix[0][0] * row + matrix[0][1] * column + matrix[0][2])
                source_column = int(matrix[1][0] * row + matrix[1][1] * column + matrix[1][2])
                if 0 <= source_row < rows and 0 <= source_column < columns:
                    expected[row][column] = float(image[source_row][source_column])
        return expected
    def valid_solution(problem, actual, expected):
        observed = actual.get("transformed_image") if isinstance(actual, dict) else None
        return (
            isinstance(observed, list)
            and len(observed) == len(expected)
            and all(isinstance(row, list) and len(row) == len(expected[0]) for row in observed)
            and all(abs(observed[i][j] - expected[i][j]) <= 1e-9 for i in range(len(expected)) for j in range(len(expected[0])))
        )
    """
)


EIGENVALUES = _source(
    """
    import math
    def solve(problem):
        matrix = [list(map(float, row)) for row in problem]
        n = len(matrix)
        for _ in range(max(1, 80 * n * n)):
            p, q, largest = 0, 0, 0.0
            for row in range(n):
                for column in range(row + 1, n):
                    value = abs(matrix[row][column])
                    if value > largest:
                        p, q, largest = row, column, value
            if largest <= 1e-12:
                break
            angle = 0.5 * math.atan2(2.0 * matrix[p][q], matrix[q][q] - matrix[p][p])
            cosine, sine = math.cos(angle), math.sin(angle)
            app, aqq, apq = matrix[p][p], matrix[q][q], matrix[p][q]
            for index in range(n):
                if index in (p, q):
                    continue
                aip, aiq = matrix[index][p], matrix[index][q]
                matrix[index][p] = matrix[p][index] = cosine * aip - sine * aiq
                matrix[index][q] = matrix[q][index] = sine * aip + cosine * aiq
            matrix[p][p] = cosine * cosine * app - 2.0 * sine * cosine * apq + sine * sine * aqq
            matrix[q][q] = sine * sine * app + 2.0 * sine * cosine * apq + cosine * cosine * aqq
            matrix[p][q] = matrix[q][p] = 0.0
        return sorted((matrix[index][index] for index in range(n)), reverse=True)
    """
)
EIGENVALUES_PUBLIC = _source(
    """
    from algorithm import solve
    values = solve([[2.0, -1.0], [-1.0, 2.0]])
    assert abs(values[0] - 3.0) < 1e-9 and abs(values[1] - 1.0) < 1e-9
    """
)
EIGENVALUES_EVAL = _source(
    """
    def make_cases(seed, scale):
        rng = random.Random(seed)
        cases = []
        for offset in range(3):
            n = scale + 2 * offset
            matrix = [[0.0] * n for _ in range(n)]
            for index in range(0, n - 1, 2):
                left, right = rng.uniform(-5, 1), rng.uniform(2, 8)
                cosine, sine = 0.8, 0.6
                matrix[index][index] = cosine * cosine * left + sine * sine * right
                matrix[index + 1][index + 1] = sine * sine * left + cosine * cosine * right
                matrix[index][index + 1] = matrix[index + 1][index] = cosine * sine * (right - left)
            if n % 2:
                matrix[-1][-1] = rng.uniform(-3, 6)
            cases.append(matrix)
        return cases
    def reference(problem):
        values = []
        index = 0
        while index + 1 < len(problem):
            a, b, d = problem[index][index], problem[index][index + 1], problem[index + 1][index + 1]
            center = (a + d) / 2.0
            radius = math.sqrt(((a - d) / 2.0) ** 2 + b * b)
            values.extend((center + radius, center - radius))
            index += 2
        if index < len(problem):
            values.append(problem[index][index])
        return sorted(values, reverse=True)
    def valid_solution(problem, actual, expected):
        return (
            isinstance(actual, list)
            and len(actual) == len(expected)
            and all(isinstance(value, (int, float)) and math.isfinite(value) for value in actual)
            and max(abs(value - wanted) for value, wanted in zip(actual, expected)) <= 1e-8
        )
    """
)


MST = _source(
    """
    def solve(problem):
        parent = list(range(problem["num_nodes"]))
        def find(node):
            while parent[node] != node:
                parent[node] = parent[parent[node]]
                node = parent[node]
            return node
        selected = []
        for left, right, weight in sorted(problem["edges"], key=lambda edge: (edge[2], edge[0], edge[1])):
            root_left, root_right = find(left), find(right)
            if root_left != root_right:
                parent[root_right] = root_left
                selected.append([left, right, weight])
        return {"mst_edges": sorted(selected, key=lambda edge: (edge[0], edge[1]))}
    """
)
MST_PUBLIC = _source(
    """
    from algorithm import solve
    problem = {"num_nodes": 4, "edges": [[0, 1, 1.0], [1, 2, 2.0], [2, 3, 1.0], [0, 3, 8.0], [0, 2, 4.0]]}
    result = solve(problem)["mst_edges"]
    assert len(result) == 3 and abs(sum(edge[2] for edge in result) - 4.0) < 1e-12
    """
)
MST_EVAL = _source(
    """
    def make_cases(seed, scale):
        rng = random.Random(seed)
        cases = []
        for offset in range(3):
            n = scale + offset * 7
            edges = [[node, node + 1, float(1 + rng.randrange(20))] for node in range(n - 1)]
            for _ in range(n * 3):
                left, right = sorted(rng.sample(range(n), 2))
                edges.append([left, right, float(1 + rng.randrange(50))])
            cases.append({"num_nodes": n, "edges": edges})
        return cases
    def reference(problem):
        n = problem["num_nodes"]
        adjacency = [[] for _ in range(n)]
        for left, right, weight in problem["edges"]:
            adjacency[left].append((weight, right)); adjacency[right].append((weight, left))
        reached, total = {0}, 0.0
        while len(reached) < n:
            weight, node = min((weight, node) for source in reached for weight, node in adjacency[source] if node not in reached)
            reached.add(node); total += weight
        return total
    def valid_solution(problem, actual, optimum):
        edges = actual.get("mst_edges") if isinstance(actual, dict) else None
        n = problem["num_nodes"]
        available = {(min(left, right), max(left, right), float(weight)) for left, right, weight in problem["edges"]}
        if not isinstance(edges, list) or len(edges) != n - 1:
            return False
        parent = list(range(n))
        def find(node):
            while parent[node] != node:
                node = parent[node]
            return node
        total = 0.0
        for edge in edges:
            if not isinstance(edge, list) or len(edge) != 3:
                return False
            left, right, weight = edge
            if (min(left, right), max(left, right), float(weight)) not in available:
                return False
            root_left, root_right = find(left), find(right)
            if root_left == root_right:
                return False
            parent[root_right] = root_left; total += weight
        return len({find(node) for node in range(n)}) == 1 and abs(total - optimum) <= 1e-9
    """
)


LEAST_SQUARES = _source(
    """
    def solve(problem):
        degree = problem.get("degree", 1)
        if problem.get("model_type") != "polynomial":
            raise ValueError("this DEV contract supports polynomial models")
        width = degree + 1
        matrix = [[sum(x ** (row + column) for x in problem["x_data"]) for column in range(width)] for row in range(width)]
        vector = [sum(y * x ** row for x, y in zip(problem["x_data"], problem["y_data"])) for row in range(width)]
        for pivot in range(width):
            best = max(range(pivot, width), key=lambda row: abs(matrix[row][pivot]))
            matrix[pivot], matrix[best] = matrix[best], matrix[pivot]
            vector[pivot], vector[best] = vector[best], vector[pivot]
            divisor = matrix[pivot][pivot]
            for column in range(pivot, width): matrix[pivot][column] /= divisor
            vector[pivot] /= divisor
            for row in range(width):
                if row == pivot: continue
                factor = matrix[row][pivot]
                for column in range(pivot, width): matrix[row][column] -= factor * matrix[pivot][column]
                vector[row] -= factor * vector[pivot]
        return {"params": vector}
    """
)
LEAST_SQUARES_PUBLIC = _source(
    """
    from algorithm import solve
    result = solve({"n": 4, "x_data": [0.0, 1.0, 2.0, 3.0], "y_data": [2.0, 6.0, 12.0, 20.0], "model_type": "polynomial", "degree": 2})["params"]
    assert max(abs(a - b) for a, b in zip(result, [2.0, 3.0, 1.0])) < 1e-9
    """
)
LEAST_SQUARES_EVAL = _source(
    """
    def make_cases(seed, scale):
        rng = random.Random(seed)
        cases = []
        for degree in (1, 2, 3):
            params = [rng.uniform(-3.0, 3.0) for _ in range(degree + 1)]
            x_data = [(-2.0 + 4.0 * index / (scale - 1)) for index in range(scale)]
            y_data = [sum(value * x ** power for power, value in enumerate(params)) for x in x_data]
            cases.append({"n": scale, "x_data": x_data, "y_data": y_data, "model_type": "polynomial", "degree": degree})
        return cases
    def reference(problem):
        return problem["degree"] + 1
    def valid_solution(problem, actual, width):
        params = actual.get("params") if isinstance(actual, dict) else None
        if not isinstance(params, list) or len(params) != width or not all(isinstance(value, (int, float)) and math.isfinite(value) for value in params):
            return False
        residual = max(abs(sum(value * x ** power for power, value in enumerate(params)) - y) for x, y in zip(problem["x_data"], problem["y_data"]))
        return residual <= 1e-7
    """
)


CONVOLUTION = _source(
    """
    def solve(problem):
        left, right = problem["signal_x"], problem["signal_y"]
        full = [0.0] * (len(left) + len(right) - 1)
        for i, left_value in enumerate(left):
            for j, right_value in enumerate(right):
                full[i + j] += left_value * right_value
        mode = problem["mode"]
        if mode == "full": result = full
        elif mode == "same":
            length = max(len(left), len(right)); start = (len(full) - length) // 2; result = full[start:start + length]
        elif mode == "valid":
            length = abs(len(left) - len(right)) + 1; start = min(len(left), len(right)) - 1; result = full[start:start + length]
        else: raise ValueError("unknown convolution mode")
        return {"result": result}
    """
)
CONVOLUTION_PUBLIC = _source(
    """
    from algorithm import solve
    problem = {"signal_x": [1.0, 2.0, 3.0, 4.0], "signal_y": [5.0, 6.0, 7.0], "mode": "full"}
    assert solve(problem) == {"result": [5.0, 16.0, 34.0, 52.0, 45.0, 28.0]}
    """
)
CONVOLUTION_EVAL = _source(
    """
    def make_cases(seed, scale):
        rng = random.Random(seed)
        left = [rng.uniform(-2, 2) for _ in range(scale)]
        right = [rng.uniform(-1, 1) for _ in range(scale // 2 + 1)]
        return [{"signal_x": left, "signal_y": right, "mode": mode} for mode in ("full", "same", "valid")]
    def reference(problem):
        left, right = problem["signal_x"], problem["signal_y"]
        full = [sum(left[i] * right[index - i] for i in range(len(left)) if 0 <= index - i < len(right)) for index in range(len(left) + len(right) - 1)]
        if problem["mode"] == "full": return full
        if problem["mode"] == "same":
            length = max(len(left), len(right)); start = (len(full) - length) // 2; return full[start:start + length]
        length = abs(len(left) - len(right)) + 1; start = min(len(left), len(right)) - 1; return full[start:start + length]
    def valid_solution(problem, actual, expected):
        observed = actual.get("result") if isinstance(actual, dict) else None
        return isinstance(observed, list) and len(observed) == len(expected) and all(isinstance(value, (int, float)) and math.isfinite(value) for value in observed) and max(abs(value - wanted) for value, wanted in zip(observed, expected)) <= 1e-8
    """
)


ASSIGNMENT = _source(
    """
    def solve(problem):
        n = problem["shape"][0]
        costs = [[float("inf")] * n for _ in range(n)]
        for row in range(n):
            for cursor in range(problem["indptr"][row], problem["indptr"][row + 1]):
                costs[row][problem["indices"][cursor]] = problem["data"][cursor]
        states = {0: (0.0, ())}
        for row in range(n):
            updated = {}
            for mask, (cost, chosen) in states.items():
                for column in range(n):
                    if not mask & (1 << column) and costs[row][column] != float("inf"):
                        next_mask = mask | (1 << column); candidate = (cost + costs[row][column], chosen + (column,))
                        if next_mask not in updated or candidate[0] < updated[next_mask][0]: updated[next_mask] = candidate
            states = updated
        columns = states[(1 << n) - 1][1]
        return {"assignment": {"row_ind": list(range(n)), "col_ind": list(columns)}}
    """
)
ASSIGNMENT_PUBLIC = _source(
    """
    from algorithm import solve
    problem = {"data": [10, 2, 8, 3, 7, 5, 6, 4, 9], "indices": [0, 1, 2] * 3, "indptr": [0, 3, 6, 9], "shape": [3, 3]}
    result = solve(problem)["assignment"]
    assert result["row_ind"] == [0, 1, 2] and result["col_ind"] == [1, 2, 0]
    """
)
ASSIGNMENT_EVAL = _source(
    """
    def make_cases(seed, scale):
        rng = random.Random(seed)
        cases = []
        for offset in range(2):
            n = scale + offset
            data = [float(1 + rng.randrange(80)) for _ in range(n * n)]
            cases.append({"data": data, "indices": list(range(n)) * n, "indptr": [row * n for row in range(n + 1)], "shape": [n, n]})
        return cases
    def reference(problem):
        n = problem["shape"][0]; costs = [problem["data"][row * n:(row + 1) * n] for row in range(n)]
        states = {0: 0.0}
        for row in range(n):
            updated = {}
            for mask, cost in states.items():
                for column in range(n):
                    if not mask & (1 << column):
                        next_mask = mask | (1 << column); updated[next_mask] = min(updated.get(next_mask, float("inf")), cost + costs[row][column])
            states = updated
        return states[(1 << n) - 1]
    def valid_solution(problem, actual, optimum):
        assignment = actual.get("assignment") if isinstance(actual, dict) else None
        if not isinstance(assignment, dict): return False
        rows, columns = assignment.get("row_ind"), assignment.get("col_ind"); n = problem["shape"][0]
        if sorted(rows or []) != list(range(n)) or sorted(columns or []) != list(range(n)): return False
        lookup = [{problem["indices"][cursor]: problem["data"][cursor] for cursor in range(problem["indptr"][row], problem["indptr"][row + 1])} for row in range(n)]
        return abs(sum(lookup[row][column] for row, column in zip(rows, columns)) - optimum) <= 1e-9
    """
)


VERTEX_COVER = _source(
    """
    import itertools
    def solve(problem):
        edges = [(left, right) for left in range(len(problem)) for right in range(left + 1, len(problem)) if problem[left][right]]
        for size in range(len(problem) + 1):
            for chosen in itertools.combinations(range(len(problem)), size):
                selected = set(chosen)
                if all(left in selected or right in selected for left, right in edges): return list(chosen)
        return []
    """
)
VERTEX_COVER_PUBLIC = _source(
    """
    from algorithm import solve
    graph = [[0, 1, 0, 1], [1, 0, 1, 0], [0, 1, 0, 1], [1, 0, 1, 0]]
    assert len(solve(graph)) == 2
    """
)
VERTEX_COVER_EVAL = _source(
    """
    def make_cases(seed, scale):
        rng = random.Random(seed); cases = []
        for offset in range(2):
            n = scale + offset; graph = [[0] * n for _ in range(n)]
            for node in range(n - 1): graph[node][node + 1] = graph[node + 1][node] = 1
            for left in range(n):
                for right in range(left + 2, n):
                    if rng.random() < 0.18: graph[left][right] = graph[right][left] = 1
            cases.append(graph)
        return cases
    def reference(problem):
        edges = [(left, right) for left in range(len(problem)) for right in range(left + 1, len(problem)) if problem[left][right]]
        for size in range(len(problem) + 1):
            if any(all(left in chosen or right in chosen for left, right in edges) for chosen in itertools.combinations(range(len(problem)), size)): return size
        return 0
    def valid_solution(problem, actual, optimum):
        return isinstance(actual, list) and len(actual) == len(set(actual)) == optimum and all(isinstance(node, int) and 0 <= node < len(problem) for node in actual) and all(left in actual or right in actual for left in range(len(problem)) for right in range(left + 1, len(problem)) if problem[left][right])
    """
)


TSP = _source(
    """
    def solve(problem):
        n = len(problem); states = {(1, 0): (0.0, (0,))}
        for _ in range(1, n):
            updated = {}
            for (mask, last), (cost, path) in states.items():
                for city in range(1, n):
                    if mask & (1 << city): continue
                    key = (mask | (1 << city), city); candidate = (cost + problem[last][city], path + (city,))
                    if key not in updated or candidate[0] < updated[key][0]: updated[key] = candidate
            states = updated
        cost, path = min((cost + problem[last][0], path) for (mask, last), (cost, path) in states.items())
        return list(path) + [0]
    """
)
TSP_PUBLIC = _source(
    """
    from algorithm import solve
    matrix = [[0, 10, 15, 20], [10, 0, 35, 25], [15, 35, 0, 30], [20, 25, 30, 0]]
    route = solve(matrix)
    assert route[0] == route[-1] == 0 and set(route[:-1]) == {0, 1, 2, 3}
    assert sum(matrix[route[i]][route[i + 1]] for i in range(len(route) - 1)) == 80
    """
)
TSP_EVAL = _source(
    """
    def make_cases(seed, scale):
        rng = random.Random(seed); cases = []
        for offset in range(2):
            n = scale + offset; points = [(rng.randrange(100), rng.randrange(100)) for _ in range(n)]
            cases.append([[0 if i == j else abs(points[i][0] - points[j][0]) + abs(points[i][1] - points[j][1]) for j in range(n)] for i in range(n)])
        return cases
    def reference(problem):
        return min(sum(problem[path[index]][path[index + 1]] for index in range(len(path) - 1)) + problem[path[-1]][0] for path in ((0,) + tail for tail in itertools.permutations(range(1, len(problem)))))
    def valid_solution(problem, actual, optimum):
        return isinstance(actual, list) and len(actual) == len(problem) + 1 and actual[0] == actual[-1] == 0 and sorted(actual[:-1]) == list(range(len(problem))) and sum(problem[actual[index]][actual[index + 1]] for index in range(len(problem))) == optimum
    """
)


_FAMILIES = {
    "affine_transform_2d": ("affine_transform_2d", AFFINE, AFFINE_PUBLIC, AFFINE_EVAL, 18),
    "eigenvalues_real": ("eigenvalues_real", EIGENVALUES, EIGENVALUES_PUBLIC, EIGENVALUES_EVAL, 7),
    "minimum_spanning_tree": ("minimum_spanning_tree", MST, MST_PUBLIC, MST_EVAL, 35),
    "least_squares": ("least_squares", LEAST_SQUARES, LEAST_SQUARES_PUBLIC, LEAST_SQUARES_EVAL, 28),
    "fft_convolution": ("fft_convolution", CONVOLUTION, CONVOLUTION_PUBLIC, CONVOLUTION_EVAL, 90),
    "min_weight_assignment": ("min_weight_assignment", ASSIGNMENT, ASSIGNMENT_PUBLIC, ASSIGNMENT_EVAL, 9),
    "vertex_cover": ("vertex_cover", VERTEX_COVER, VERTEX_COVER_PUBLIC, VERTEX_COVER_EVAL, 11),
    "tsp": ("tsp", TSP, TSP_PUBLIC, TSP_EVAL, 8),
}


def _evaluator_source(body: str, *, seed: int, scale: int) -> str:
    return _source(
        f"""
        import copy
        import itertools
        import json
        import math
        import random
        import statistics
        import time
        from algorithm import solve
        SEED = {seed}
        SCALE = {scale}
        EVALUATOR_REGIME = {EVALUATOR_REGIME!r}
        """
    ) + "\n" + body + "\n" + _source(
        """
        cases = make_cases(SEED, SCALE)
        expected = [reference(copy.deepcopy(problem)) for problem in cases]
        valid, error = True, None
        try:
            for problem, wanted in zip(cases, expected):
                frozen = copy.deepcopy(problem)
                actual = solve(problem)
                valid = valid and problem == frozen and valid_solution(frozen, actual, wanted)
        except Exception as exc:
            valid, error = False, type(exc).__name__
        timings = []
        if valid:
            for _ in range(3):
                started = time.perf_counter()
                for problem in cases:
                    solve(copy.deepcopy(problem))
                timings.append(time.perf_counter() - started)
        median_runtime_ms = statistics.median(timings) * 1000.0 if timings else None
        score = 1.0 / (1.0 + median_runtime_ms) if valid and median_runtime_ms is not None else 0.0
        print(json.dumps({"metrics": {"score": score, "valid": float(valid), "median_runtime_ms": median_runtime_ms, "case_count": len(cases)}, "evaluator_regime": EVALUATOR_REGIME, "error": error}, sort_keys=True))
        """
    )


def p2v4_dev_specs() -> dict[tuple[str, str], P2V4DevSpec]:
    specs = {}
    for family_id, (upstream_task, initial, public, evaluator, scale) in _FAMILIES.items():
        for suffix, seed, offset in (("alpha", 5501, 0), ("beta", 6607, 1)):
            instance_id = f"{family_id}_dev_{suffix}"
            specs[(family_id, instance_id)] = P2V4DevSpec(
                family_id, upstream_task, instance_id, seed, scale + offset, initial, public, evaluator
            )
    return specs


def materialize_p2v4_dev(family: dict[str, Any], instance_id: str, output_dir: Path) -> dict[str, Any]:
    spec = p2v4_dev_specs().get((family["family_id"], instance_id))
    if spec is None or instance_id not in family.get("instance_ids", []):
        raise ValueError(f"instance is not registered for family: {instance_id}")
    if family.get("upstream_task") != spec.upstream_task:
        raise RuntimeError("registered AlgoTune P2 V4 upstream task binding drift")
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    initial = output_dir / "algorithm.py"
    public = output_dir / "public_tests.py"
    evaluator = output_dir / "evaluate.py"
    contract = output_dir / "task-contract.json"
    initial.write_text(spec.initial_source, encoding="utf-8")
    public.write_text(spec.public_tests_source, encoding="utf-8")
    evaluator.write_text(_evaluator_source(spec.evaluator_body, seed=spec.seed, scale=spec.scale), encoding="utf-8")
    binding = family["development_binding"]
    contract_payload = {
        "schema_version": 1,
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
        "dependency_profile": "PYTHON_3_11_STANDARD_LIBRARY_ONLY",
        "partition_role": "DEV",
        "seed": spec.seed,
        "scale": spec.scale,
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
