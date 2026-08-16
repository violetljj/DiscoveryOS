from __future__ import annotations

import subprocess
import textwrap
from dataclasses import dataclass
from pathlib import Path

from discoveryos.util import digest_bytes


LOCK_PAYLOAD = b"python-stdlib-only\n"


@dataclass(frozen=True, slots=True)
class RealCodeTask:
    task_id: str
    category: str
    question: str
    algorithm_source: str
    public_tests_source: str
    evaluator_source: str
    entrypoint: str = "algorithm.py"

    def initialize_repository(self, root: Path) -> tuple[Path, str]:
        repository = (root / self.task_id / "repo").resolve()
        if repository.exists():
            raise RuntimeError(f"real-code task repository already exists: {repository}")
        repository.mkdir(parents=True)
        (repository / self.entrypoint).write_text(_source(self.algorithm_source), encoding="utf-8")
        (repository / "public_tests.py").write_text(_source(self.public_tests_source), encoding="utf-8")
        (repository / "evaluate.py").write_text(_source(self.evaluator_source), encoding="utf-8")
        (repository / "requirements.lock").write_bytes(LOCK_PAYLOAD)
        _git(repository, "init", "--quiet")
        _git(repository, "config", "user.email", "discoveryos@example.invalid")
        _git(repository, "config", "user.name", "DiscoveryOS Admission")
        _git(repository, "config", "core.autocrlf", "false")
        _git(repository, "add", "--", self.entrypoint, "public_tests.py", "evaluate.py", "requirements.lock")
        _git(repository, "commit", "--quiet", "-m", f"Freeze {self.task_id} baseline")
        return repository, _git(repository, "rev-parse", "HEAD").strip()

    @property
    def environment_digest(self) -> str:
        return digest_bytes(LOCK_PAYLOAD)


def admission_tasks() -> tuple[RealCodeTask, ...]:
    return (
        RealCodeTask(
            task_id="adaptive_step",
            category="parameter_logic",
            question=(
                "Improve choose_step(error). It must return a non-negative integer, return zero for zero error, "
                "remain conservative for small error, and use progressively larger bounded steps as error grows."
            ),
            algorithm_source="""
                def choose_step(error):
                    return 1
            """,
            public_tests_source="""
                from algorithm import choose_step

                assert choose_step(0.25) == 1
                assert isinstance(choose_step(3.0), int)
                assert choose_step(3.0) >= 0
            """,
            evaluator_source="""
                import json, os
                from algorithm import choose_step

                proxy = [(0.0, 0), (0.5, 1), (3.0, 2), (8.0, 4)]
                hidden = proxy + [(0.1, 1), (1.0, 1), (1.01, 2), (5.0, 2), (5.01, 4), (100.0, 4)]
                cases = proxy if os.environ.get("DISCOVERYOS_FIDELITY") == "G1_PROXY" else hidden
                score = sum(choose_step(value) == expected for value, expected in cases) / len(cases)
                print(json.dumps({"metrics": {"score": score, "valid": 1.0}}))
            """,
        ),
        RealCodeTask(
            task_id="stable_topk",
            category="local_algorithm",
            question=(
                "Improve top_k_unique(values, k) so it returns at most k distinct largest values in descending "
                "order, handles empty input and non-positive k, and does not mutate the caller's list."
            ),
            algorithm_source="""
                def top_k_unique(values, k):
                    return sorted(values, reverse=True)[:k]
            """,
            public_tests_source="""
                from algorithm import top_k_unique

                values = [3, 1, 2]
                assert top_k_unique(values, 2) == [3, 2]
                assert values == [3, 1, 2]
            """,
            evaluator_source="""
                import json, os
                from algorithm import top_k_unique

                proxy = [([3, 3, 2, 1], 3, [3, 2, 1]), ([], 4, []), ([2, 1], 0, [])]
                hidden = proxy + [([5, 5, 5], 2, [5]), ([-1, -2, -1], 5, [-1, -2]), ([4, 2, 4, 3, 2], 2, [4, 3])]
                cases = proxy if os.environ.get("DISCOVERYOS_FIDELITY") == "G1_PROXY" else hidden
                passed = 0
                for values, k, expected in cases:
                    original = list(values)
                    passed += top_k_unique(values, k) == expected and values == original
                print(json.dumps({"metrics": {"score": passed / len(cases), "valid": 1.0}}))
            """,
        ),
        RealCodeTask(
            task_id="lru_cache",
            category="data_structure",
            question=(
                "Repair the bounded LRUCache implementation. get must refresh recency, put must update existing "
                "keys without growing the cache, and overflow must evict exactly the least-recently-used key."
            ),
            algorithm_source="""
                from collections import OrderedDict

                class LRUCache:
                    def __init__(self, capacity):
                        self.capacity = capacity
                        self.data = OrderedDict()

                    def get(self, key, default=None):
                        return self.data.get(key, default)

                    def put(self, key, value):
                        self.data[key] = value
                        if len(self.data) > self.capacity:
                            self.data.popitem(last=True)
            """,
            public_tests_source="""
                from algorithm import LRUCache

                cache = LRUCache(2)
                cache.put("a", 1)
                assert cache.get("a") == 1
                assert cache.get("missing") is None
            """,
            evaluator_source="""
                import json, os
                from algorithm import LRUCache

                def scenario_one():
                    cache = LRUCache(2); cache.put("a", 1); cache.put("b", 2); cache.get("a"); cache.put("c", 3)
                    return cache.get("a") == 1 and cache.get("b") is None and cache.get("c") == 3

                def scenario_two():
                    cache = LRUCache(2); cache.put("a", 1); cache.put("a", 9); cache.put("b", 2); cache.put("c", 3)
                    return cache.get("a") is None and cache.get("b") == 2 and cache.get("c") == 3

                def scenario_zero():
                    cache = LRUCache(0); cache.put("a", 1); return cache.get("a") is None

                cases = [scenario_one, scenario_two] if os.environ.get("DISCOVERYOS_FIDELITY") == "G1_PROXY" else [scenario_one, scenario_two, scenario_zero]
                score = sum(bool(case()) for case in cases) / len(cases)
                print(json.dumps({"metrics": {"score": score, "valid": 1.0}}))
            """,
        ),
        RealCodeTask(
            task_id="stable_softmax",
            category="numerical_algorithm",
            question=(
                "Improve softmax(values). It must be numerically stable for very large magnitudes, return finite "
                "probabilities summing to one, preserve ordering, and return an empty list for empty input."
            ),
            algorithm_source="""
                import math

                def softmax(values):
                    if not values:
                        return []
                    try:
                        weights = [math.exp(value) for value in values]
                    except OverflowError:
                        return [0.0 for _ in values]
                    total = sum(weights)
                    if total == 0:
                        return [0.0 for _ in values]
                    return [weight / total for weight in weights]
            """,
            public_tests_source="""
                from algorithm import softmax

                assert softmax([]) == []
                values = softmax([0.0, 0.0])
                assert values == [0.5, 0.5]
            """,
            evaluator_source="""
                import json, math, os
                from algorithm import softmax

                proxy = [[1000.0, 1001.0], [-1000.0, -999.0], [0.0, 0.0, 0.0]]
                hidden = proxy + [[1e6, 1e6 + 1, 1e6 - 1], [-1e6, -1e6 - 2], [3.0], []]
                cases = proxy if os.environ.get("DISCOVERYOS_FIDELITY") == "G1_PROXY" else hidden
                passed = 0
                for case in cases:
                    result = softmax(case)
                    finite = all(math.isfinite(value) and 0 <= value <= 1 for value in result)
                    normalized = (not case and result == []) or (len(result) == len(case) and abs(sum(result) - 1.0) < 1e-9)
                    ordered = all((case[i] <= case[j]) == (result[i] <= result[j]) for i in range(len(case)) for j in range(len(case)))
                    passed += finite and normalized and ordered
                print(json.dumps({"metrics": {"score": passed / len(cases), "valid": 1.0}}))
            """,
        ),
        RealCodeTask(
            task_id="debounce_state",
            category="state_timing_algorithm",
            question=(
                "Improve Debouncer.accept(timestamp). The first event must be accepted, later events are accepted "
                "only when the interval has elapsed since the last accepted event, rejected events must not move "
                "the boundary, and non-monotonic timestamps must be rejected."
            ),
            algorithm_source="""
                class Debouncer:
                    def __init__(self, interval):
                        self.interval = interval
                        self.last_seen = 0.0

                    def accept(self, timestamp):
                        allowed = timestamp - self.last_seen >= self.interval
                        self.last_seen = timestamp
                        return allowed
            """,
            public_tests_source="""
                from algorithm import Debouncer

                gate = Debouncer(1.0)
                assert gate.accept(5.0) is True
                assert gate.accept(5.2) is False
            """,
            evaluator_source="""
                import json, os
                from algorithm import Debouncer

                def run(times, expected):
                    gate = Debouncer(1.0)
                    return [gate.accept(value) for value in times] == expected

                proxy = [([0.0, 0.5, 1.0], [True, False, True]), ([5.0, 5.2, 6.0], [True, False, True])]
                hidden = proxy + [([2.0, 1.0, 3.0], [True, False, True]), ([0.0, 0.9, 1.1], [True, False, True])]
                cases = proxy if os.environ.get("DISCOVERYOS_FIDELITY") == "G1_PROXY" else hidden
                score = sum(run(times, expected) for times, expected in cases) / len(cases)
                print(json.dumps({"metrics": {"score": score, "valid": 1.0}}))
            """,
        ),
        RealCodeTask(
            task_id="merge_intervals",
            category="sequence_algorithm",
            question=(
                "Improve merge_intervals(intervals). Normalize reversed endpoints, sort without mutating the input, "
                "and merge both overlapping and directly touching closed intervals."
            ),
            algorithm_source="""
                def merge_intervals(intervals):
                    ordered = sorted(intervals)
                    if not ordered:
                        return []
                    merged = [list(ordered[0])]
                    for start, end in ordered[1:]:
                        if start < merged[-1][1]:
                            merged[-1][1] = max(merged[-1][1], end)
                        else:
                            merged.append([start, end])
                    return [tuple(item) for item in merged]
            """,
            public_tests_source="""
                from algorithm import merge_intervals

                values = [(1, 3), (2, 4)]
                assert merge_intervals(values) == [(1, 4)]
                assert values == [(1, 3), (2, 4)]
            """,
            evaluator_source="""
                import json, os
                from algorithm import merge_intervals

                proxy = [([], []), ([(1, 2), (2, 3)], [(1, 3)]), ([(4, 5), (1, 2)], [(1, 2), (4, 5)])]
                hidden = proxy + [([(5, 1), (2, 6)], [(1, 6)]), ([(1, 1), (1, 2)], [(1, 2)]), ([(3, 4), (1, 2), (2, 3)], [(1, 4)])]
                cases = proxy if os.environ.get("DISCOVERYOS_FIDELITY") == "G1_PROXY" else hidden
                passed = 0
                for values, expected in cases:
                    original = list(values)
                    passed += merge_intervals(values) == expected and values == original
                print(json.dumps({"metrics": {"score": passed / len(cases), "valid": 1.0}}))
            """,
        ),
    )


def _source(value: str) -> str:
    return textwrap.dedent(value).strip() + "\n"


def _git(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ("git", "-C", str(repository), *arguments),
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git command failed")
    return result.stdout
