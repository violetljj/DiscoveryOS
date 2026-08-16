from __future__ import annotations

from discoveryos.benchmarks.real_code_tasks import RealCodeTask


def br_a_tasks() -> tuple[RealCodeTask, ...]:
    """Return the sealed R1.0-BR-A corpus.

    These task families and target files are disjoint from the consumed R1.0-B
    corpus.  The task payload is hashed before any provider call by the BR-A
    sealing workflow.
    """

    return (
        RealCodeTask(
            task_id="retry_delay",
            category="bounded_schedule",
            question=(
                "Repair retry_delay(attempt, base=1.0, cap=30.0). Attempts are one-based; non-positive attempts "
                "return 0.0. Positive attempts use capped exponential backoff base * 2**(attempt-1). The result "
                "must never exceed a non-negative cap, and non-positive base values produce 0.0."
            ),
            entrypoint="retry_policy.py",
            algorithm_source="""
                def retry_delay(attempt, base=1.0, cap=30.0):
                    return min(cap, base * attempt)
            """,
            public_tests_source="""
                from retry_policy import retry_delay

                assert retry_delay(1) == 1.0
                assert retry_delay(2, base=2.0) >= 0.0
            """,
            evaluator_source="""
                import json, os
                from retry_policy import retry_delay

                proxy = [(1, 1.0, 30.0, 1.0), (3, 1.0, 30.0, 4.0), (8, 1.0, 30.0, 30.0)]
                hidden = proxy + [(0, 1.0, 30.0, 0.0), (-2, 3.0, 30.0, 0.0), (4, 2.5, 12.0, 12.0), (3, 0.0, 9.0, 0.0), (2, 4.0, -1.0, 0.0)]
                cases = proxy if os.environ.get("DISCOVERYOS_FIDELITY") == "G1_PROXY" else hidden
                score = sum(abs(retry_delay(a, b, c) - expected) < 1e-12 for a, b, c, expected in cases) / len(cases)
                print(json.dumps({"metrics": {"score": score, "valid": 1.0}}))
            """,
        ),
        RealCodeTask(
            task_id="header_fields",
            category="text_protocol",
            question=(
                "Repair parse_fields(text). Parse semicolon-separated key=value fields, trim surrounding "
                "whitespace, lowercase keys, ignore empty or malformed fields, keep values after the first '=', "
                "and let the last occurrence of a key win."
            ),
            entrypoint="header_fields.py",
            algorithm_source="""
                def parse_fields(text):
                    result = {}
                    for field in text.split(";"):
                        key, value = field.split("=")
                        result[key] = value
                    return result
            """,
            public_tests_source="""
                from header_fields import parse_fields

                assert parse_fields("a=1;b=2") == {"a": "1", "b": "2"}
            """,
            evaluator_source="""
                import json, os
                from header_fields import parse_fields

                proxy = [("a=1;b=2", {"a": "1", "b": "2"}), (" A = x ; b=y ", {"a": "x", "b": "y"}), ("", {})]
                hidden = proxy + [("broken;a=1;;b=2=3", {"a": "1", "b": "2=3"}), ("X=1;x=2", {"x": "2"}), (" =bad;ok=yes", {"ok": "yes"}), ("k=; lone ", {"k": ""})]
                cases = proxy if os.environ.get("DISCOVERYOS_FIDELITY") == "G1_PROXY" else hidden
                passed = 0
                for text, expected in cases:
                    try:
                        passed += parse_fields(text) == expected
                    except Exception:
                        pass
                print(json.dumps({"metrics": {"score": passed / len(cases), "valid": 1.0}}))
            """,
        ),
        RealCodeTask(
            task_id="stable_priority_queue",
            category="ordered_container",
            question=(
                "Repair StablePriorityQueue. pop() returns the value with the smallest numeric priority, preserves "
                "insertion order for ties, raises IndexError when empty, and len(queue) reports pending items."
            ),
            entrypoint="priority_queue.py",
            algorithm_source="""
                class StablePriorityQueue:
                    def __init__(self):
                        self.items = []

                    def push(self, value, priority):
                        self.items.append((value, priority))

                    def pop(self):
                        self.items.sort(key=lambda item: item[0])
                        return self.items.pop(0)[0]

                    def __len__(self):
                        return len(self.items)
            """,
            public_tests_source="""
                from priority_queue import StablePriorityQueue

                queue = StablePriorityQueue(); queue.push("a", 1)
                assert queue.pop() == "a" and len(queue) == 0
            """,
            evaluator_source="""
                import json, os
                from priority_queue import StablePriorityQueue

                def order_case(items, expected):
                    queue = StablePriorityQueue()
                    for value, priority in items: queue.push(value, priority)
                    return [queue.pop() for _ in items] == expected and len(queue) == 0

                def empty_case():
                    try: StablePriorityQueue().pop()
                    except IndexError: return True
                    return False

                proxy = [(lambda: order_case([("low", 5), ("high", 1)], ["high", "low"])), (lambda: order_case([("b", 2), ("a", 2)], ["b", "a"]))]
                hidden = proxy + [(lambda: order_case([("z", -1), ("a", 0), ("b", -1)], ["z", "b", "a"])), empty_case, (lambda: order_case([], []))]
                cases = proxy if os.environ.get("DISCOVERYOS_FIDELITY") == "G1_PROXY" else hidden
                score = sum(bool(case()) for case in cases) / len(cases)
                print(json.dumps({"metrics": {"score": score, "valid": 1.0}}))
            """,
        ),
        RealCodeTask(
            task_id="rolling_average",
            category="windowed_numeric",
            question=(
                "Repair rolling_average(values, window). Return one float per input position using the available "
                "suffix of at most window values. Return [] for empty input and raise ValueError when window is "
                "not a positive integer. Do not mutate the input."
            ),
            entrypoint="rolling_average.py",
            algorithm_source="""
                def rolling_average(values, window):
                    result = []
                    for index in range(len(values)):
                        chunk = values[max(0, index - window + 1):index + 1]
                        result.append(sum(chunk) / window)
                    return result
            """,
            public_tests_source="""
                from rolling_average import rolling_average

                assert rolling_average([2.0, 4.0], 1) == [2.0, 4.0]
            """,
            evaluator_source="""
                import json, os
                from rolling_average import rolling_average

                def close(actual, expected):
                    return len(actual) == len(expected) and all(abs(a-b) < 1e-12 for a,b in zip(actual, expected))

                def invalid(window):
                    try: rolling_average([1.0], window)
                    except Exception as error: return isinstance(error, ValueError)
                    return False

                proxy = [(lambda: close(rolling_average([1.0, 2.0, 3.0], 2), [1.0, 1.5, 2.5])), (lambda: rolling_average([], 3) == [])]
                hidden = proxy + [(lambda: close(rolling_average([4.0, -2.0, 8.0], 5), [4.0, 1.0, 10.0/3.0])), (lambda: (lambda v: close(rolling_average(v, 2), [3.0, 2.0, 3.0]) and v == [3.0, 1.0, 5.0])([3.0, 1.0, 5.0])), (lambda: invalid(0)), (lambda: invalid(1.5))]
                cases = proxy if os.environ.get("DISCOVERYOS_FIDELITY") == "G1_PROXY" else hidden
                score = sum(bool(case()) for case in cases) / len(cases)
                print(json.dumps({"metrics": {"score": score, "valid": 1.0}}))
            """,
        ),
        RealCodeTask(
            task_id="circuit_breaker",
            category="state_machine",
            question=(
                "Repair CircuitBreaker(threshold). allow() is initially true. record_failure() opens the breaker "
                "after threshold consecutive failures; record_success() resets the failure streak and closes it. "
                "A threshold less than one behaves as one."
            ),
            entrypoint="circuit_breaker.py",
            algorithm_source="""
                class CircuitBreaker:
                    def __init__(self, threshold):
                        self.threshold = threshold
                        self.failures = 0

                    def allow(self):
                        return True

                    def record_failure(self):
                        self.failures += 1

                    def record_success(self):
                        pass
            """,
            public_tests_source="""
                from circuit_breaker import CircuitBreaker

                breaker = CircuitBreaker(2)
                assert breaker.allow() is True
                breaker.record_failure(); assert breaker.allow() is True
            """,
            evaluator_source="""
                import json, os
                from circuit_breaker import CircuitBreaker

                def run(threshold, events, expected):
                    breaker = CircuitBreaker(threshold); observed = [breaker.allow()]
                    for event in events:
                        getattr(breaker, event)(); observed.append(breaker.allow())
                    return observed == expected

                proxy = [(2, ["record_failure", "record_failure"], [True, True, False]), (3, ["record_failure", "record_success", "record_failure", "record_failure"], [True, True, True, True, True])]
                hidden = proxy + [(1, ["record_failure", "record_success"], [True, False, True]), (0, ["record_failure"], [True, False]), (2, ["record_failure", "record_failure", "record_success"], [True, True, False, True])]
                cases = proxy if os.environ.get("DISCOVERYOS_FIDELITY") == "G1_PROXY" else hidden
                score = sum(run(*case) for case in cases) / len(cases)
                print(json.dumps({"metrics": {"score": score, "valid": 1.0}}))
            """,
        ),
        RealCodeTask(
            task_id="dependency_order",
            category="directed_graph",
            question=(
                "Repair dependency_order(dependencies). The mapping is node -> prerequisites. Return a "
                "deterministic topological order containing keys and prerequisite-only nodes, choosing the "
                "lexicographically smallest available node, and raise ValueError on a cycle."
            ),
            entrypoint="dependency_order.py",
            algorithm_source="""
                def dependency_order(dependencies):
                    return sorted(dependencies)
            """,
            public_tests_source="""
                from dependency_order import dependency_order

                assert dependency_order({"a": [], "b": []}) == ["a", "b"]
            """,
            evaluator_source="""
                import json, os
                from dependency_order import dependency_order

                def ordered(graph, expected):
                    try: return dependency_order(graph) == expected
                    except Exception: return False

                def cycle():
                    try: dependency_order({"a": ["b"], "b": ["a"]})
                    except ValueError: return True
                    return False

                proxy = [(lambda: ordered({"build": ["compile"], "compile": ["fetch"]}, ["fetch", "compile", "build"])), (lambda: ordered({"b": [], "a": []}, ["a", "b"]))]
                hidden = proxy + [(lambda: ordered({"deploy": ["test"], "test": ["build"], "lint": ["build"]}, ["build", "lint", "test", "deploy"])), (lambda: ordered({"b": ["a"], "c": ["a"]}, ["a", "b", "c"])), cycle, (lambda: ordered({}, []))]
                cases = proxy if os.environ.get("DISCOVERYOS_FIDELITY") == "G1_PROXY" else hidden
                score = sum(bool(case()) for case in cases) / len(cases)
                print(json.dumps({"metrics": {"score": score, "valid": 1.0}}))
            """,
        ),
        RealCodeTask(
            task_id="session_windows",
            category="event_segmentation",
            question=(
                "Repair session_windows(timestamps, gap). Return inclusive (start, end) windows in chronological "
                "order. Sort without mutating input; a new window starts only when the next timestamp is more "
                "than gap after the current end. Negative gaps raise ValueError."
            ),
            entrypoint="session_windows.py",
            algorithm_source="""
                def session_windows(timestamps, gap):
                    if not timestamps:
                        return []
                    return [(timestamps[0], timestamps[-1])]
            """,
            public_tests_source="""
                from session_windows import session_windows

                assert session_windows([], 3) == []
                assert session_windows([1, 2], 2) == [(1, 2)]
            """,
            evaluator_source="""
                import json, os
                from session_windows import session_windows

                def run(values, gap, expected):
                    original = list(values)
                    try: actual = session_windows(values, gap)
                    except Exception: return False
                    return actual == expected and values == original

                def negative():
                    try: session_windows([1], -1)
                    except ValueError: return True
                    return False

                proxy = [([1, 2, 10], 3, [(1, 2), (10, 10)]), ([5, 1, 3], 2, [(1, 5)]), ([], 1, [])]
                hidden = proxy + [([0, 3, 6], 3, [(0, 6)]), ([1, 1, 8], 2, [(1, 1), (8, 8)]), ([9], 0, [(9, 9)])]
                cases = proxy if os.environ.get("DISCOVERYOS_FIDELITY") == "G1_PROXY" else hidden
                checks = [run(*case) for case in cases]
                if os.environ.get("DISCOVERYOS_FIDELITY") != "G1_PROXY": checks.append(negative())
                print(json.dumps({"metrics": {"score": sum(checks) / len(checks), "valid": 1.0}}))
            """,
        ),
        RealCodeTask(
            task_id="largest_remainder",
            category="integer_apportionment",
            question=(
                "Repair allocate(total, weights). Return non-negative integer allocations summing to total using "
                "the largest-remainder method. Negative total or weights raise ValueError; all-zero weights split "
                "as evenly as possible from the first index; ties preserve input order."
            ),
            entrypoint="allocator.py",
            algorithm_source="""
                def allocate(total, weights):
                    weight_sum = sum(weights)
                    return [int(total * weight / weight_sum) for weight in weights]
            """,
            public_tests_source="""
                from allocator import allocate

                assert allocate(4, [1, 1]) == [2, 2]
            """,
            evaluator_source="""
                import json, os
                from allocator import allocate

                def run(total, weights, expected):
                    original = list(weights)
                    try: actual = allocate(total, weights)
                    except Exception: return False
                    return actual == expected and sum(actual) == total and weights == original and all(isinstance(v, int) and v >= 0 for v in actual)

                def invalid(total, weights):
                    try: allocate(total, weights)
                    except Exception as error: return isinstance(error, ValueError)
                    return False

                proxy = [(5, [1, 1], [3, 2]), (10, [1, 2, 1], [3, 5, 2]), (0, [2, 3], [0, 0])]
                hidden = proxy + [(7, [0, 0, 0], [3, 2, 2]), (3, [1, 1, 1, 1], [1, 1, 1, 0]), (0, [], [])]
                cases = proxy if os.environ.get("DISCOVERYOS_FIDELITY") == "G1_PROXY" else hidden
                checks = [run(*case) for case in cases]
                if os.environ.get("DISCOVERYOS_FIDELITY") != "G1_PROXY": checks.extend([invalid(-1, [1]), invalid(2, [1, -1])])
                print(json.dumps({"metrics": {"score": sum(checks) / len(checks), "valid": 1.0}}))
            """,
        ),
    )
