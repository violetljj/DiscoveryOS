from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from discoveryos.benchmarks.p2_v4_fast_close import (
    QUOTAS,
    _materialize_and_probe,
    run_full_cohort_gate,
    select_cohort,
)
from discoveryos.runtime.executability_gate import PowerLeaseReceipt


REGISTRY = Path(__file__).parents[1] / "benchmarks" / "bank" / "v1" / "registry.json"


class _Lease:
    def __init__(self, _reason: str, *, fail: bool = False) -> None:
        self.fail = fail
        self.acquired = False
        self.released = False

    def acquire(self) -> None:
        if self.fail:
            raise OSError("injected lease failure")
        self.acquired = True

    def release(self) -> None:
        self.released = True

    @property
    def receipt(self) -> PowerLeaseReceipt:
        return PowerLeaseReceipt(
            acquired=self.acquired,
            provider="FAKE",
            request_types=("SYSTEM_REQUIRED", "EXECUTION_REQUIRED") if self.acquired else (),
            acquired_at_utc="2026-08-18T00:00:00+00:00" if self.acquired else None,
            released_at_utc="2026-08-18T00:01:00+00:00" if self.released else None,
        )


class _Events:
    def query(self, _start, _end):
        return ()


class P2V4FastCloseTests(unittest.TestCase):
    def test_selector_is_deterministic_balanced_and_one_instance_per_family(self) -> None:
        first = select_cohort(REGISTRY)
        second = select_cohort(REGISTRY)
        self.assertEqual(first["cohort_plan_digest"], second["cohort_plan_digest"])
        self.assertEqual(24, len(first["units"]))
        self.assertEqual(
            QUOTAS,
            {
                tier: sum(unit["difficulty_tier"] == tier for unit in first["units"])
                for tier in QUOTAS
            },
        )
        self.assertEqual(24, len({unit["family_id"] for unit in first["units"]}))
        self.assertTrue(all(len(set(unit["primary_arm_order"])) == 4 for unit in first["units"]))

    def test_one_real_selected_unit_passes_exact_materialization_and_baseline_replay(self) -> None:
        unit = select_cohort(REGISTRY)["units"][0]
        with tempfile.TemporaryDirectory() as directory:
            probe, receipt = _materialize_and_probe(REGISTRY, unit, Path(directory) / "unit")
        self.assertTrue(receipt["admitted"], receipt)
        self.assertEqual(2, len(probe.scores))
        self.assertEqual(probe.scores[0], probe.scores[1])
        self.assertTrue(probe.materialization_replayed)
        self.assertTrue(probe.task_tree_digest_match)

    def test_full_gate_holds_one_lease_and_requires_all_24_units(self) -> None:
        calls = []

        def fake_probe(_registry, unit, _root):
            calls.append(unit["block_id"])
            return None, {
                "status": "EXECUTABILITY_GATE_PASS",
                "admitted": True,
                "failure_class": None,
                "failure_detail": None,
                "probe": {},
            }

        lease = _Lease("test")
        with tempfile.TemporaryDirectory() as directory, patch(
            "discoveryos.benchmarks.p2_v4_fast_close._materialize_and_probe", fake_probe
        ):
            receipt = run_full_cohort_gate(
                Path(directory) / "gate",
                registry_path=REGISTRY,
                lease_factory=lambda _reason: lease,
                event_source=_Events(),
            )
        self.assertTrue(receipt["admitted"])
        self.assertEqual(24, len(calls))
        self.assertTrue(lease.acquired)
        self.assertTrue(lease.released)

    def test_power_lease_failure_is_classified_before_any_unit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            receipt = run_full_cohort_gate(
                Path(directory) / "gate",
                registry_path=REGISTRY,
                lease_factory=lambda reason: _Lease(reason, fail=True),
                event_source=_Events(),
            )
        self.assertFalse(receipt["admitted"])
        self.assertEqual("INFRA_FAILURE_POWER_INHIBITION_UNAVAILABLE", receipt["failure_class"])
        self.assertEqual(0, receipt["passed_units"])


if __name__ == "__main__":
    unittest.main()
