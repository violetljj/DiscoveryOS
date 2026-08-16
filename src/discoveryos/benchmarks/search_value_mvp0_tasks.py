from __future__ import annotations

import textwrap
from dataclasses import dataclass

from discoveryos.benchmarks.real_code_tasks import RealCodeTask
from discoveryos.util import digest_json


@dataclass(frozen=True, slots=True)
class SearchValueTask:
    task: RealCodeTask
    reference_source: str
    intermediate_sources: tuple[str, ...]
    score_resolution: float
    baseline_basin_id: str
    trajectory_classes: tuple[str, ...]

    @property
    def payload_digest(self) -> str:
        return digest_json(self)


def search_value_mvp0_tasks() -> tuple[SearchValueTask, ...]:
    """Eight pre-model optimization tasks from three independent families."""

    return (
        _knapsack_task("bounded_knapsack_alpha", _KNAPSACK_ALPHA),
        _knapsack_task("bounded_knapsack_beta", _KNAPSACK_BETA),
        _knapsack_task("bounded_knapsack_gamma", _KNAPSACK_GAMMA),
        _coloring_task("conflict_coloring_alpha", _COLOR_ALPHA),
        _coloring_task("conflict_coloring_beta", _COLOR_BETA),
        _coloring_task("conflict_coloring_gamma", _COLOR_GAMMA),
        _balance_task("load_balance_alpha", _BALANCE_ALPHA),
        _balance_task("load_balance_beta", _BALANCE_BETA),
    )


def _knapsack_task(task_id: str, cases: tuple[tuple[tuple[tuple[int, int], ...], int], ...]) -> SearchValueTask:
    task = RealCodeTask(
        task_id=task_id,
        category="combinatorial_subset_optimization",
        question=(
            "Improve select_items(items, capacity). items is a sequence of positive (weight, value) pairs. "
            "Return unique zero-based indices whose total weight does not exceed capacity. The evaluator rewards "
            "the selected value relative to the exact optimum across a frozen distribution. Do not mutate inputs; "
            "invalid indices, duplicates, overweight selections, or exceptions receive zero quality."
        ),
        algorithm_source="""
            def select_items(items, capacity):
                chosen = []
                used = 0
                for index, (weight, value) in enumerate(items):
                    if used + weight <= capacity:
                        chosen.append(index)
                        used += weight
                return chosen
        """,
        public_tests_source="""
            from algorithm import select_items

            items = [(2, 3), (3, 5), (4, 7)]
            original = list(items)
            result = select_items(items, 5)
            assert isinstance(result, list)
            assert len(result) == len(set(result))
            assert all(isinstance(index, int) and 0 <= index < len(items) for index in result)
            assert sum(items[index][0] for index in result) <= 5
            assert items == original
        """,
        evaluator_source=_knapsack_evaluator(cases),
    )
    return SearchValueTask(
        task=task,
        reference_source=_KNAPSACK_REFERENCE,
        intermediate_sources=(_KNAPSACK_LIGHTEST, _KNAPSACK_VALUE, _KNAPSACK_DENSITY),
        score_resolution=0.025,
        baseline_basin_id="input_order_first_fit",
        trajectory_classes=("heuristic_order_refinement", "exact_or_dynamic_subset_search"),
    )


def _coloring_task(task_id: str, cases: tuple[tuple[int, tuple[tuple[int, int], ...], int], ...]) -> SearchValueTask:
    task = RealCodeTask(
        task_id=task_id,
        category="graph_conflict_optimization",
        question=(
            "Improve color_graph(node_count, edges, color_count). Return one integer color per node in "
            "[0, color_count). The evaluator rewards the fraction of edges whose endpoints receive different "
            "colors over a frozen graph distribution. Preserve inputs and return a valid complete coloring even "
            "when a conflict-free coloring is not found."
        ),
        algorithm_source="""
            def color_graph(node_count, edges, color_count):
                return [index % color_count for index in range(node_count)]
        """,
        public_tests_source="""
            from algorithm import color_graph

            edges = [(0, 1), (1, 2)]
            original = list(edges)
            colors = color_graph(3, edges, 2)
            assert len(colors) == 3
            assert all(isinstance(color, int) and 0 <= color < 2 for color in colors)
            assert edges == original
        """,
        evaluator_source=_color_evaluator(cases),
    )
    return SearchValueTask(
        task=task,
        reference_source=_COLOR_REFERENCE,
        intermediate_sources=(_COLOR_BLOCKS, _COLOR_GREEDY, _COLOR_DEGREE_GREEDY),
        score_resolution=0.02,
        baseline_basin_id="index_modulo_coloring",
        trajectory_classes=("local_greedy_reordering", "constraint_backtracking_or_dsatur"),
    )


def _balance_task(task_id: str, cases: tuple[tuple[tuple[int, ...], int], ...]) -> SearchValueTask:
    task = RealCodeTask(
        task_id=task_id,
        category="parallel_load_optimization",
        question=(
            "Improve assign_loads(weights, machine_count). Return one machine index per non-negative job weight. "
            "Every index must be in [0, machine_count), inputs must remain unchanged, and every job must be "
            "assigned exactly once. The evaluator rewards exact-optimum makespan divided by the produced "
            "makespan across a frozen distribution."
        ),
        algorithm_source="""
            def assign_loads(weights, machine_count):
                return [0 for _ in weights]
        """,
        public_tests_source="""
            from algorithm import assign_loads

            weights = [4, 3, 2]
            original = list(weights)
            assignment = assign_loads(weights, 2)
            assert len(assignment) == len(weights)
            assert all(isinstance(machine, int) and 0 <= machine < 2 for machine in assignment)
            assert weights == original
        """,
        evaluator_source=_balance_evaluator(cases),
    )
    return SearchValueTask(
        task=task,
        reference_source=_BALANCE_REFERENCE,
        intermediate_sources=(_BALANCE_ROUND_ROBIN, _BALANCE_LPT, _BALANCE_LPT_REPAIR),
        score_resolution=0.025,
        baseline_basin_id="single_machine_assignment",
        trajectory_classes=("local_load_reallocation", "branch_and_bound_partitioning"),
    )


def _knapsack_evaluator(cases) -> str:
    return f"""
        import json
        from algorithm import select_items

        CASES = {cases!r}

        def optimum(items, capacity):
            best = 0
            for mask in range(1 << len(items)):
                weight = sum(items[i][0] for i in range(len(items)) if mask >> i & 1)
                if weight <= capacity:
                    best = max(best, sum(items[i][1] for i in range(len(items)) if mask >> i & 1))
            return best

        scores = []
        valid = True
        for frozen_items, capacity in CASES:
            items = list(frozen_items)
            original = list(items)
            try:
                chosen = select_items(items, capacity)
                ok = isinstance(chosen, list) and len(chosen) == len(set(chosen))
                ok = ok and all(isinstance(i, int) and 0 <= i < len(items) for i in chosen)
                ok = ok and sum(items[i][0] for i in chosen) <= capacity and items == original
                value = sum(items[i][1] for i in chosen) if ok else 0
                scores.append(value / optimum(items, capacity) if ok else 0.0)
                valid = valid and ok
            except Exception:
                scores.append(0.0); valid = False
        print(json.dumps({{"metrics": {{"score": sum(scores) / len(scores), "valid": float(valid)}}}}))
    """


def _color_evaluator(cases) -> str:
    return f"""
        import json
        from algorithm import color_graph

        CASES = {cases!r}
        scores = []
        valid = True
        for node_count, frozen_edges, color_count in CASES:
            edges = list(frozen_edges)
            original = list(edges)
            try:
                colors = color_graph(node_count, edges, color_count)
                ok = isinstance(colors, list) and len(colors) == node_count and edges == original
                ok = ok and all(isinstance(c, int) and 0 <= c < color_count for c in colors)
                good = sum(colors[a] != colors[b] for a, b in edges) if ok else 0
                scores.append(good / len(edges) if edges and ok else float(ok))
                valid = valid and ok
            except Exception:
                scores.append(0.0); valid = False
        print(json.dumps({{"metrics": {{"score": sum(scores) / len(scores), "valid": float(valid)}}}}))
    """


def _balance_evaluator(cases) -> str:
    return f"""
        import itertools, json
        from algorithm import assign_loads

        CASES = {cases!r}

        def makespan(weights, assignment, machine_count):
            loads = [0] * machine_count
            for weight, machine in zip(weights, assignment): loads[machine] += weight
            return max(loads, default=0)

        def optimum(weights, machine_count):
            return min(makespan(weights, assignment, machine_count) for assignment in itertools.product(range(machine_count), repeat=len(weights)))

        scores = []
        valid = True
        for frozen_weights, machine_count in CASES:
            weights = list(frozen_weights)
            original = list(weights)
            try:
                assignment = assign_loads(weights, machine_count)
                ok = isinstance(assignment, list) and len(assignment) == len(weights) and weights == original
                ok = ok and all(isinstance(m, int) and 0 <= m < machine_count for m in assignment)
                actual = makespan(weights, assignment, machine_count) if ok else 0
                best = optimum(weights, machine_count)
                scores.append(best / actual if ok and actual else float(ok and best == 0))
                valid = valid and ok
            except Exception:
                scores.append(0.0); valid = False
        print(json.dumps({{"metrics": {{"score": sum(scores) / len(scores), "valid": float(valid)}}}}))
    """


_KNAPSACK_REFERENCE = """
def select_items(items, capacity):
    best_value, best = -1, []
    for mask in range(1 << len(items)):
        chosen = [i for i in range(len(items)) if mask >> i & 1]
        weight = sum(items[i][0] for i in chosen)
        value = sum(items[i][1] for i in chosen)
        if weight <= capacity and value > best_value:
            best_value, best = value, chosen
    return best
"""

_KNAPSACK_LIGHTEST = """
def select_items(items, capacity):
    order = sorted(range(len(items)), key=lambda i: (items[i][0], i))
    chosen, used = [], 0
    for i in order:
        if used + items[i][0] <= capacity: chosen.append(i); used += items[i][0]
    return chosen
"""

_KNAPSACK_VALUE = """
def select_items(items, capacity):
    order = sorted(range(len(items)), key=lambda i: (-items[i][1], items[i][0], i))
    chosen, used = [], 0
    for i in order:
        if used + items[i][0] <= capacity: chosen.append(i); used += items[i][0]
    return chosen
"""

_KNAPSACK_DENSITY = """
def select_items(items, capacity):
    order = sorted(range(len(items)), key=lambda i: (-items[i][1] / items[i][0], items[i][0], i))
    chosen, used = [], 0
    for i in order:
        if used + items[i][0] <= capacity: chosen.append(i); used += items[i][0]
    return chosen
"""

_COLOR_BLOCKS = """
def color_graph(node_count, edges, color_count):
    return [(index // 2) % color_count for index in range(node_count)]
"""

_COLOR_GREEDY = """
def color_graph(node_count, edges, color_count):
    adjacent = [set() for _ in range(node_count)]
    for a, b in edges: adjacent[a].add(b); adjacent[b].add(a)
    colors = [-1] * node_count
    for node in range(node_count):
        used = {colors[n] for n in adjacent[node] if colors[n] >= 0}
        colors[node] = next((c for c in range(color_count) if c not in used), 0)
    return colors
"""

_COLOR_DEGREE_GREEDY = """
def color_graph(node_count, edges, color_count):
    adjacent = [set() for _ in range(node_count)]
    for a, b in edges: adjacent[a].add(b); adjacent[b].add(a)
    colors = [-1] * node_count
    for node in sorted(range(node_count), key=lambda n: (-len(adjacent[n]), n)):
        used = {colors[n] for n in adjacent[node] if colors[n] >= 0}
        colors[node] = next((c for c in range(color_count) if c not in used), min(range(color_count), key=lambda c: sum(colors[n] == c for n in adjacent[node])))
    return colors
"""

_COLOR_REFERENCE = """
def color_graph(node_count, edges, color_count):
    adjacent = [set() for _ in range(node_count)]
    for a, b in edges: adjacent[a].add(b); adjacent[b].add(a)
    colors = [-1] * node_count
    def search():
        uncolored = [n for n in range(node_count) if colors[n] < 0]
        if not uncolored: return True
        node = max(uncolored, key=lambda n: (len({colors[x] for x in adjacent[n] if colors[x] >= 0}), len(adjacent[n])))
        used = {colors[x] for x in adjacent[node] if colors[x] >= 0}
        for color in range(color_count):
            if color not in used:
                colors[node] = color
                if search(): return True
                colors[node] = -1
        return False
    if search(): return colors
    return [index % color_count for index in range(node_count)]
"""

_BALANCE_ROUND_ROBIN = """
def assign_loads(weights, machine_count):
    return [index % machine_count for index in range(len(weights))]
"""

_BALANCE_LPT = """
def assign_loads(weights, machine_count):
    loads = [0] * machine_count; result = [0] * len(weights)
    for index in sorted(range(len(weights)), key=lambda i: (-weights[i], i)):
        machine = min(range(machine_count), key=lambda m: (loads[m], m))
        result[index] = machine; loads[machine] += weights[index]
    return result
"""

_BALANCE_LPT_REPAIR = """
def assign_loads(weights, machine_count):
    loads = [0] * machine_count; result = [0] * len(weights)
    for index in sorted(range(len(weights)), key=lambda i: (-weights[i], i)):
        machine = min(range(machine_count), key=lambda m: (loads[m], m))
        result[index] = machine; loads[machine] += weights[index]
    improved = True
    while improved:
        improved = False; current = max(loads)
        for i, weight in enumerate(weights):
            source = result[i]
            for target in range(machine_count):
                trial = list(loads); trial[source] -= weight; trial[target] += weight
                if max(trial) < current:
                    result[i] = target; loads = trial; improved = True; break
            if improved: break
    return result
"""

_BALANCE_REFERENCE = """
def assign_loads(weights, machine_count):
    best_span = float('inf'); best = None; loads = [0] * machine_count; assignment = [0] * len(weights)
    order = sorted(range(len(weights)), key=lambda i: -weights[i])
    def search(position):
        nonlocal best_span, best
        if position == len(order):
            span = max(loads, default=0)
            if span < best_span: best_span = span; best = list(assignment)
            return
        index = order[position]; seen = set()
        for machine in range(machine_count):
            if loads[machine] in seen: continue
            seen.add(loads[machine]); loads[machine] += weights[index]; assignment[index] = machine
            if max(loads) < best_span: search(position + 1)
            loads[machine] -= weights[index]
    search(0)
    return best or [0] * len(weights)
"""


_KNAPSACK_ALPHA = (
    (((6, 6), (5, 7), (4, 12), (3, 8)), 10),
    (((8, 8), (7, 9), (5, 13), (4, 11), (3, 7)), 12),
    (((9, 10), (6, 8), (5, 15), (4, 13), (3, 9)), 11),
    (((10, 9), (8, 10), (6, 18), (5, 16), (4, 12)), 14),
    (((7, 7), (6, 8), (5, 14), (3, 10), (2, 6)), 10),
    (((12, 11), (9, 12), (7, 21), (5, 16), (4, 13)), 16),
)
_KNAPSACK_BETA = (
    (((5, 4), (4, 5), (3, 10), (2, 7), (2, 6)), 7),
    (((11, 10), (8, 11), (6, 20), (5, 18), (3, 9)), 14),
    (((7, 5), (6, 8), (4, 14), (3, 11), (2, 7)), 9),
    (((13, 12), (10, 14), (8, 25), (6, 20), (5, 16)), 18),
    (((9, 7), (7, 10), (5, 17), (4, 14), (3, 10)), 12),
    (((6, 5), (5, 7), (4, 13), (3, 11), (2, 8)), 8),
)
_KNAPSACK_GAMMA = (
    (((10, 8), (7, 9), (6, 19), (4, 14), (3, 10), (2, 6)), 13),
    (((14, 13), (9, 12), (7, 24), (6, 21), (4, 13)), 19),
    (((8, 6), (6, 9), (5, 17), (3, 11), (2, 7)), 10),
    (((12, 10), (8, 13), (6, 22), (5, 18), (3, 11)), 16),
    (((9, 8), (8, 10), (5, 18), (4, 15), (2, 7)), 11),
    (((7, 6), (5, 8), (4, 15), (3, 12), (2, 7)), 9),
)


def _planted_edges(groups: tuple[tuple[int, ...], ...]) -> tuple[tuple[int, int], ...]:
    edges = set()
    for left in range(len(groups)):
        for right in range(left + 1, len(groups)):
            for a in groups[left]:
                for b in groups[right]:
                    if (a * 7 + b * 11 + left + right) % 3 != 0:
                        edges.add((min(a, b), max(a, b)))
    return tuple(sorted(edges))


_COLOR_ALPHA = (
    (9, _planted_edges(((0, 3, 6), (1, 4, 7), (2, 5, 8))), 3),
    (10, _planted_edges(((0, 4, 8), (1, 5, 9), (2, 6), (3, 7))), 4),
    (8, _planted_edges(((0, 2, 6), (1, 4, 7), (3, 5))), 3),
    (11, _planted_edges(((0, 5, 9), (1, 6, 10), (2, 4, 8), (3, 7))), 4),
)
_COLOR_BETA = (
    (9, _planted_edges(((0, 1, 7), (2, 5, 8), (3, 4, 6))), 3),
    (10, _planted_edges(((0, 2, 9), (1, 6), (3, 7), (4, 5, 8))), 4),
    (8, _planted_edges(((0, 5), (1, 3, 7), (2, 4, 6))), 3),
    (12, _planted_edges(((0, 6, 11), (1, 4, 9), (2, 7, 10), (3, 5, 8))), 4),
)
_COLOR_GAMMA = (
    (9, _planted_edges(((0, 4, 5), (1, 6, 8), (2, 3, 7))), 3),
    (10, _planted_edges(((0, 5), (1, 3, 8), (2, 6, 9), (4, 7))), 4),
    (8, _planted_edges(((0, 3, 7), (1, 5), (2, 4, 6))), 3),
    (11, _planted_edges(((0, 7, 10), (1, 5, 8), (2, 6, 9), (3, 4))), 4),
)

_BALANCE_ALPHA = (
    ((10, 9, 8, 7, 6, 5), 3), ((12, 11, 7, 6, 5, 4), 3), ((9, 8, 7, 6, 5), 2),
    ((15, 13, 11, 9, 7, 5), 3), ((8, 8, 7, 7, 6, 6), 3), ((14, 10, 9, 8, 6, 5), 4),
)
_BALANCE_BETA = (
    ((16, 14, 12, 10, 8, 6), 3), ((11, 10, 9, 8, 7, 6, 5), 3), ((13, 12, 8, 7, 5), 2),
    ((18, 15, 12, 9, 6, 3), 3), ((10, 10, 9, 9, 8, 8, 7), 4), ((17, 13, 11, 8, 7, 5), 3),
)


def normalized_source(source: str) -> str:
    return textwrap.dedent(source).strip() + "\n"
