from __future__ import annotations

import textwrap

from discoveryos.benchmarks.real_code_tasks import RealCodeTask
from discoveryos.benchmarks.search_value_mvp0_tasks import SearchValueTask


DISCOVERY_TASK_IDS = (
    "budgeted_coverage_delta",
    "budgeted_coverage_epsilon",
    "budgeted_coverage_eta",
    "capacitated_assignment_delta",
    "capacitated_assignment_epsilon",
    "capacitated_assignment_eta",
    "balanced_cut_delta",
    "balanced_cut_epsilon",
    "balanced_cut_eta",
)
CONFIRMATION_TASK_IDS = (
    "budgeted_coverage_zeta_confirmation",
    "capacitated_assignment_zeta_confirmation",
    "balanced_cut_zeta_confirmation",
)


def si2_discovery_tasks() -> tuple[SearchValueTask, ...]:
    return (
        _coverage_task(DISCOVERY_TASK_IDS[0], (2101, 2117, 2141, 2161, 2179, 2203)),
        _coverage_task(DISCOVERY_TASK_IDS[1], (3109, 3121, 3137, 3163, 3181, 3203)),
        _coverage_task(DISCOVERY_TASK_IDS[2], (3503, 3527, 3557, 3571, 3593, 3617)),
        _assignment_task(DISCOVERY_TASK_IDS[3], (4109, 4127, 4153, 4177, 4201, 4219)),
        _assignment_task(DISCOVERY_TASK_IDS[4], (5101, 5119, 5147, 5171, 5197, 5227)),
        _assignment_task(DISCOVERY_TASK_IDS[5], (5501, 5521, 5539, 5563, 5581, 5623)),
        _balanced_cut_task(DISCOVERY_TASK_IDS[6], (6101, 6121, 6151, 6173, 6199, 6221)),
        _balanced_cut_task(DISCOVERY_TASK_IDS[7], (7103, 7121, 7151, 7177, 7193, 7219)),
        _balanced_cut_task(DISCOVERY_TASK_IDS[8], (7507, 7523, 7547, 7561, 7583, 7607)),
    )


def si2_confirmation_tasks() -> tuple[SearchValueTask, ...]:
    return (
        _coverage_task(CONFIRMATION_TASK_IDS[0], (8101, 8117, 8147, 8167, 8191, 8219)),
        _assignment_task(CONFIRMATION_TASK_IDS[1], (9103, 9127, 9151, 9181, 9209, 9227)),
        _balanced_cut_task(CONFIRMATION_TASK_IDS[2], (10103, 10133, 10159, 10181, 10211, 10243)),
    )


def _coverage_task(task_id: str, seeds: tuple[int, ...]) -> SearchValueTask:
    task = RealCodeTask(
        task_id=task_id,
        category="budgeted_weighted_coverage",
        question=(
            "Improve choose_sets(sets, weights, limit). sets is a sequence of sequences of zero-based element "
            "indices, weights contains positive element weights, and limit is the maximum number of unique set "
            "indices that may be returned. Maximize the total weight of the union. Return a list of unique valid "
            "indices, do not mutate inputs, and remain practical for roughly 50 elements and 24 candidate sets."
        ),
        algorithm_source="""
            def choose_sets(sets, weights, limit):
                return list(range(min(limit, len(sets))))
        """,
        public_tests_source="""
            from algorithm import choose_sets

            sets = [(0, 1), (1, 2), (2, 3)]
            weights = [1, 2, 3, 4]
            frozen_sets, frozen_weights = list(sets), list(weights)
            result = choose_sets(sets, weights, 2)
            assert isinstance(result, list)
            assert len(result) <= 2 and len(result) == len(set(result))
            assert all(isinstance(i, int) and 0 <= i < len(sets) for i in result)
            assert sets == frozen_sets and weights == frozen_weights
        """,
        evaluator_source=_coverage_evaluator(seeds),
    )
    return SearchValueTask(
        task=task,
        reference_source=_COVERAGE_REFERENCE,
        intermediate_sources=(_COVERAGE_LARGEST, _COVERAGE_UNWEIGHTED, _COVERAGE_WEIGHTED),
        score_resolution=0.005,
        baseline_basin_id="coverage_input_prefix",
        trajectory_classes=("marginal_coverage_greedy", "swap_or_multistart_coverage_search"),
    )


def _assignment_task(task_id: str, seeds: tuple[int, ...]) -> SearchValueTask:
    task = RealCodeTask(
        task_id=task_id,
        category="capacitated_cost_assignment",
        question=(
            "Improve assign_clients(costs, capacities). costs[c][f] is the non-negative cost of assigning client c "
            "to facility f, and capacities gives the maximum clients per facility. Return one valid facility index "
            "per client, respect every capacity, minimize total cost, and do not mutate inputs. Instances contain "
            "about 48 clients and 7 facilities, so avoid exponential search."
        ),
        algorithm_source="""
            def assign_clients(costs, capacities):
                remaining = list(capacities)
                result = []
                for _ in costs:
                    facility = next(i for i, space in enumerate(remaining) if space > 0)
                    result.append(facility)
                    remaining[facility] -= 1
                return result
        """,
        public_tests_source="""
            from algorithm import assign_clients

            costs = [[4, 1], [2, 5], [3, 2]]
            capacities = [2, 2]
            frozen_costs = [list(row) for row in costs]
            frozen_capacities = list(capacities)
            result = assign_clients(costs, capacities)
            assert isinstance(result, list) and len(result) == len(costs)
            assert all(isinstance(f, int) and 0 <= f < len(capacities) for f in result)
            assert all(result.count(f) <= capacities[f] for f in range(len(capacities)))
            assert costs == frozen_costs and capacities == frozen_capacities
        """,
        evaluator_source=_assignment_evaluator(seeds),
    )
    return SearchValueTask(
        task=task,
        reference_source=_ASSIGNMENT_REFERENCE,
        intermediate_sources=(_ASSIGNMENT_CHEAPEST, _ASSIGNMENT_REGRET, _ASSIGNMENT_REGRET_SWAP),
        score_resolution=0.003,
        baseline_basin_id="assignment_capacity_fill",
        trajectory_classes=("capacity_aware_greedy", "regret_ordered_local_reassignment"),
    )


def _balanced_cut_task(task_id: str, seeds: tuple[int, ...]) -> SearchValueTask:
    task = RealCodeTask(
        task_id=task_id,
        category="balanced_graph_cut",
        question=(
            "Improve balanced_cut(node_count, edges). Return a list of 0/1 labels of length node_count with group "
            "sizes differing by at most one. Maximize the fraction of undirected edges crossing the groups, preserve "
            "inputs, and remain practical for graphs with about 44 nodes. Self-loops are absent and duplicate edges "
            "need not be handled."
        ),
        algorithm_source="""
            def balanced_cut(node_count, edges):
                return [index % 2 for index in range(node_count)]
        """,
        public_tests_source="""
            from algorithm import balanced_cut

            edges = [(0, 1), (1, 2), (2, 3)]
            frozen = list(edges)
            labels = balanced_cut(4, edges)
            assert isinstance(labels, list) and len(labels) == 4
            assert all(label in (0, 1) for label in labels)
            assert abs(labels.count(0) - labels.count(1)) <= 1
            assert edges == frozen
        """,
        evaluator_source=_balanced_cut_evaluator(seeds),
    )
    return SearchValueTask(
        task=task,
        reference_source=_CUT_REFERENCE,
        intermediate_sources=(_CUT_DEGREE, _CUT_GREEDY, _CUT_SINGLE_START),
        score_resolution=0.004,
        baseline_basin_id="cut_index_parity",
        trajectory_classes=("balanced_greedy_partition", "pair_swap_multistart_cut_search"),
    )


def _coverage_evaluator(seeds: tuple[int, ...]) -> str:
    return f"""
        import json, random
        from algorithm import choose_sets

        SEEDS = {seeds!r}

        def make_case(seed):
            rng = random.Random(seed)
            element_count, set_count, limit = 52, 24, 6
            weights = [rng.randint(1, 11) for _ in range(element_count)]
            sets = []
            for index in range(set_count):
                anchor = (index * 7 + seed) % element_count
                members = {{(anchor + step * (3 + index % 5)) % element_count for step in range(7 + index % 6)}}
                members.update(rng.sample(range(element_count), 4 + index % 4))
                sets.append(tuple(sorted(members)))
            return sets, weights, limit

        scores, valid = [], True
        for seed in SEEDS:
            sets, weights, limit = make_case(seed)
            frozen_sets, frozen_weights = list(sets), list(weights)
            try:
                chosen = choose_sets(sets, weights, limit)
                ok = isinstance(chosen, list) and len(chosen) <= limit and len(chosen) == len(set(chosen))
                ok = ok and all(isinstance(i, int) and 0 <= i < len(sets) for i in chosen)
                ok = ok and sets == frozen_sets and weights == frozen_weights
                covered = set().union(*(sets[i] for i in chosen)) if ok and chosen else set()
                score = sum(weights[i] for i in covered) / sum(weights) if ok else 0.0
                scores.append(score); valid = valid and ok
            except Exception:
                scores.append(0.0); valid = False
        print(json.dumps({{"metrics": {{"score": sum(scores) / len(scores), "valid": float(valid)}}}}))
    """


def _assignment_evaluator(seeds: tuple[int, ...]) -> str:
    return f"""
        import json, random
        from algorithm import assign_clients

        SEEDS = {seeds!r}

        def make_case(seed):
            rng = random.Random(seed)
            client_count, facility_count = 48, 7
            capacities = [7, 7, 7, 7, 7, 7, 6]
            costs = []
            for client in range(client_count):
                preferred = rng.randrange(facility_count)
                second = (preferred + 1 + rng.randrange(facility_count - 1)) % facility_count
                row = []
                for facility in range(facility_count):
                    base = 2 if facility == preferred else 7 if facility == second else 18
                    row.append(base + abs((client * 3 + facility * 5) % 11 - 5) + rng.randrange(6))
                costs.append(row)
            return costs, capacities

        scores, valid = [], True
        for seed in SEEDS:
            costs, capacities = make_case(seed)
            frozen_costs, frozen_capacities = [list(row) for row in costs], list(capacities)
            try:
                assignment = assign_clients(costs, capacities)
                ok = isinstance(assignment, list) and len(assignment) == len(costs)
                ok = ok and all(isinstance(f, int) and 0 <= f < len(capacities) for f in assignment)
                ok = ok and all(assignment.count(f) <= capacities[f] for f in range(len(capacities)))
                ok = ok and costs == frozen_costs and capacities == frozen_capacities
                total = sum(costs[c][facility] for c, facility in enumerate(assignment)) if ok else 10**9
                scores.append(1.0 / (1.0 + total / (len(costs) * 10.0)) if ok else 0.0)
                valid = valid and ok
            except Exception:
                scores.append(0.0); valid = False
        print(json.dumps({{"metrics": {{"score": sum(scores) / len(scores), "valid": float(valid)}}}}))
    """


def _balanced_cut_evaluator(seeds: tuple[int, ...]) -> str:
    return f"""
        import json, random
        from algorithm import balanced_cut

        SEEDS = {seeds!r}

        def make_case(seed):
            rng = random.Random(seed)
            node_count = 44
            hidden = [0] * (node_count // 2) + [1] * (node_count // 2)
            rng.shuffle(hidden)
            edges = []
            for left in range(node_count):
                for right in range(left + 1, node_count):
                    probability = 0.48 if hidden[left] != hidden[right] else 0.09
                    if rng.random() < probability:
                        edges.append((left, right))
            return node_count, edges

        scores, valid = [], True
        for seed in SEEDS:
            node_count, edges = make_case(seed)
            frozen = list(edges)
            try:
                labels = balanced_cut(node_count, edges)
                ok = isinstance(labels, list) and len(labels) == node_count
                ok = ok and all(label in (0, 1) for label in labels)
                ok = ok and abs(labels.count(0) - labels.count(1)) <= 1 and edges == frozen
                crossing = sum(labels[a] != labels[b] for a, b in edges) if ok else 0
                scores.append(crossing / len(edges) if ok and edges else 0.0)
                valid = valid and ok
            except Exception:
                scores.append(0.0); valid = False
        print(json.dumps({{"metrics": {{"score": sum(scores) / len(scores), "valid": float(valid)}}}}))
    """


_COVERAGE_LARGEST = """
def choose_sets(sets, weights, limit):
    return sorted(range(len(sets)), key=lambda i: (-len(set(sets[i])), i))[:limit]
"""

_COVERAGE_UNWEIGHTED = """
def choose_sets(sets, weights, limit):
    chosen, covered = [], set()
    while len(chosen) < min(limit, len(sets)):
        best = max((i for i in range(len(sets)) if i not in chosen), key=lambda i: (len(set(sets[i]) - covered), -i))
        chosen.append(best); covered.update(sets[best])
    return chosen
"""

_COVERAGE_WEIGHTED = """
def choose_sets(sets, weights, limit):
    chosen, covered = [], set()
    while len(chosen) < min(limit, len(sets)):
        best = max((i for i in range(len(sets)) if i not in chosen), key=lambda i: (sum(weights[x] for x in set(sets[i]) - covered), -i))
        chosen.append(best); covered.update(sets[best])
    return chosen
"""

_COVERAGE_REFERENCE = """
def choose_sets(sets, weights, limit):
    chosen, covered = [], set()
    while len(chosen) < min(limit, len(sets)):
        best = max((i for i in range(len(sets)) if i not in chosen), key=lambda i: (sum(weights[x] for x in set(sets[i]) - covered), -i))
        chosen.append(best); covered.update(sets[best])
    def value(indices):
        union = set().union(*(set(sets[i]) for i in indices)) if indices else set()
        return sum(weights[x] for x in union)
    improved = True
    while improved:
        improved = False; current = value(chosen)
        for position in range(len(chosen)):
            for candidate in range(len(sets)):
                if candidate in chosen: continue
                trial = list(chosen); trial[position] = candidate
                if value(trial) > current:
                    chosen = trial; improved = True; break
            if improved: break
    return chosen
"""

_ASSIGNMENT_CHEAPEST = """
def assign_clients(costs, capacities):
    remaining = list(capacities); result = []
    for row in costs:
        facility = min((f for f in range(len(remaining)) if remaining[f]), key=lambda f: (row[f], f))
        result.append(facility); remaining[facility] -= 1
    return result
"""

_ASSIGNMENT_REGRET = """
def assign_clients(costs, capacities):
    remaining = list(capacities); result = [-1] * len(costs); pending = set(range(len(costs)))
    while pending:
        available = [f for f, space in enumerate(remaining) if space]
        client = max(pending, key=lambda c: (sorted(costs[c][f] for f in available)[1] - min(costs[c][f] for f in available) if len(available) > 1 else 10**9, -c))
        facility = min(available, key=lambda f: (costs[client][f], f))
        result[client] = facility; remaining[facility] -= 1; pending.remove(client)
    return result
"""

_ASSIGNMENT_REGRET_SWAP = """
def assign_clients(costs, capacities):
    remaining = list(capacities); result = [-1] * len(costs); pending = set(range(len(costs)))
    while pending:
        available = [f for f, space in enumerate(remaining) if space]
        client = max(pending, key=lambda c: (sorted(costs[c][f] for f in available)[1] - min(costs[c][f] for f in available) if len(available) > 1 else 10**9, -c))
        facility = min(available, key=lambda f: (costs[client][f], f))
        result[client] = facility; remaining[facility] -= 1; pending.remove(client)
    improved = True
    while improved:
        improved = False
        for left in range(len(result)):
            for right in range(left + 1, len(result)):
                a, b = result[left], result[right]
                if costs[left][b] + costs[right][a] < costs[left][a] + costs[right][b]:
                    result[left], result[right] = b, a; improved = True; break
            if improved: break
    return result
"""

_ASSIGNMENT_REFERENCE = """
def assign_clients(costs, capacities):
    remaining = list(capacities); result = [-1] * len(costs); pending = set(range(len(costs)))
    while pending:
        available = [f for f, space in enumerate(remaining) if space]
        def regret(client):
            ordered = sorted(costs[client][f] for f in available)
            return ordered[1] - ordered[0] if len(ordered) > 1 else 10**9
        client = max(pending, key=lambda c: (regret(c), -min(costs[c][f] for f in available), -c))
        facility = min(available, key=lambda f: (costs[client][f], f))
        result[client] = facility; remaining[facility] -= 1; pending.remove(client)
    changed = True
    while changed:
        changed = False
        for left in range(len(result)):
            for right in range(left + 1, len(result)):
                a, b = result[left], result[right]
                before = costs[left][a] + costs[right][b]
                after = costs[left][b] + costs[right][a]
                if after < before:
                    result[left], result[right] = b, a; changed = True; break
            if changed: break
    return result
"""

_CUT_DEGREE = """
def balanced_cut(node_count, edges):
    degree = [0] * node_count
    for a, b in edges: degree[a] += 1; degree[b] += 1
    left = set(sorted(range(node_count), key=lambda n: (-degree[n], n))[:node_count // 2])
    return [0 if n in left else 1 for n in range(node_count)]
"""

_CUT_GREEDY = """
def balanced_cut(node_count, edges):
    adjacent = [set() for _ in range(node_count)]
    for a, b in edges: adjacent[a].add(b); adjacent[b].add(a)
    labels = [-1] * node_count; counts = [0, 0]; target = [(node_count + 1) // 2, node_count // 2]
    for node in sorted(range(node_count), key=lambda n: (-len(adjacent[n]), n)):
        choices = [g for g in (0, 1) if counts[g] < target[g]]
        group = max(choices, key=lambda g: (sum(labels[x] == 1 - g for x in adjacent[node]), -g))
        labels[node] = group; counts[group] += 1
    return labels
"""

_CUT_SINGLE_START = """
def balanced_cut(node_count, edges):
    labels = [i % 2 for i in range(node_count)]
    def cut(): return sum(labels[a] != labels[b] for a, b in edges)
    changed = True
    while changed:
        changed = False; before = cut()
        for a in range(node_count):
            for b in range(a + 1, node_count):
                if labels[a] == labels[b]: continue
                labels[a], labels[b] = labels[b], labels[a]
                if cut() > before: changed = True; break
                labels[a], labels[b] = labels[b], labels[a]
            if changed: break
    return labels
"""

_CUT_REFERENCE = """
def balanced_cut(node_count, edges):
    def improve(labels):
        def cut(): return sum(labels[a] != labels[b] for a, b in edges)
        changed = True
        while changed:
            changed = False; before = cut()
            for a in range(node_count):
                for b in range(a + 1, node_count):
                    if labels[a] == labels[b]: continue
                    labels[a], labels[b] = labels[b], labels[a]
                    if cut() > before: changed = True; break
                    labels[a], labels[b] = labels[b], labels[a]
                if changed: break
        return labels, cut()
    starts = []
    starts.append([i % 2 for i in range(node_count)])
    starts.append([0 if i < node_count // 2 else 1 for i in range(node_count)])
    degree = [0] * node_count
    for a, b in edges: degree[a] += 1; degree[b] += 1
    left = set(sorted(range(node_count), key=lambda n: (-degree[n], n))[:node_count // 2])
    starts.append([0 if n in left else 1 for n in range(node_count)])
    return max((improve(list(labels)) for labels in starts), key=lambda item: item[1])[0]
"""


def normalized_source(source: str) -> str:
    return textwrap.dedent(source).strip() + "\n"
