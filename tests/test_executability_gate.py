from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from discoveryos.runtime.executability_gate import (
    BaselineProbeResult,
    ExecutabilityFailure,
    ExecutabilityGate,
    PowerEvent,
    PowerLeaseError,
    PowerLeaseReceipt,
    ScientificBlockResult,
    TimingBreakdown,
)
from discoveryos.benchmarks.executability_gate_qualification import _adversarial_qualification


class _Lease:
    def __init__(self, *, acquire_error: bool = False, release_error: bool = False) -> None:
        self.acquire_error = acquire_error
        self.release_error = release_error
        self.acquired = False
        self.released = False

    def acquire(self) -> None:
        if self.acquire_error:
            raise PowerLeaseError("injected acquisition failure")
        self.acquired = True

    def release(self) -> None:
        self.released = True
        if self.release_error:
            raise PowerLeaseError("injected release failure")

    @property
    def receipt(self) -> PowerLeaseReceipt:
        return PowerLeaseReceipt(
            acquired=self.acquired,
            provider="FAKE_POWER_LEASE",
            request_types=("SYSTEM_REQUIRED", "EXECUTION_REQUIRED") if self.acquired else (),
            acquired_at_utc="2026-08-18T00:00:00+00:00" if self.acquired else None,
            released_at_utc="2026-08-18T00:00:01+00:00" if self.released else None,
            failure=(
                "injected acquisition failure"
                if self.acquire_error
                else "injected release failure" if self.release_error and self.released else None
            ),
        )


class _Events:
    def __init__(self, kind: str | None = None, *, error: bool = False) -> None:
        self.kind = kind
        self.error = error

    def query(self, start_utc: datetime, end_utc: datetime) -> tuple[PowerEvent, ...]:
        if self.error:
            raise RuntimeError("injected event source failure")
        if self.kind is None:
            return ()
        event_id = {
            "ENTER_MODERN_STANDBY": 506,
            "ENTER_SLEEP_OR_HIBERNATE": 42,
        }[self.kind]
        return (
            PowerEvent(
                record_id=1,
                provider="Microsoft-Windows-Kernel-Power",
                event_id=event_id,
                timestamp_utc=(end_utc - timedelta(microseconds=1)).isoformat(),
                kind=self.kind,
                message_sha256="0" * 64,
            ),
        )


def _timing(**changes: object) -> TimingBreakdown:
    return replace(
        TimingBreakdown(
            repository_setup_seconds=1.0,
            build_test_seconds=1.0,
            evaluator_seconds=1.0,
            harness_overhead_seconds=1.0,
            cpu_seconds=0.5,
            total_wall_seconds=4.0,
        ),
        **changes,
    )


def _baseline(**changes: object) -> BaselineProbeResult:
    return replace(
        BaselineProbeResult(
            materialization_replayed=True,
            task_tree_digest_match=True,
            evaluator_validities=("VALID", "VALID"),
            scores=(0.5, 0.5),
            parser_contract_satisfied=True,
            failure_signatures=(None, None),
            timing=_timing(),
        ),
        **changes,
    )


class ExecutabilityGateTests(unittest.TestCase):
    def _execute(
        self,
        baseline: BaselineProbeResult | None = None,
        *,
        events: _Events | None = None,
        lease: _Lease | None = None,
        scientific_block=None,
    ):
        selected_lease = lease or _Lease()
        receipt = ExecutabilityGate(
            lease_factory=lambda _reason: selected_lease,
            event_source=events or _Events(),
        ).execute("fixture-block", lambda: baseline or _baseline(), scientific_block)
        return receipt, selected_lease

    def test_awake_deterministic_baseline_passes_and_releases_lease(self) -> None:
        receipt, lease = self._execute()
        self.assertTrue(receipt.admitted)
        self.assertEqual(receipt.status, "EXECUTABILITY_GATE_PASS")
        self.assertEqual(receipt.generation_calls_executed, 0)
        self.assertTrue(lease.acquired)
        self.assertTrue(lease.released)

    def test_suspend_and_hibernate_are_low_power_contamination(self) -> None:
        for kind in ("ENTER_MODERN_STANDBY", "ENTER_SLEEP_OR_HIBERNATE"):
            with self.subTest(kind=kind):
                receipt, _ = self._execute(events=_Events(kind))
                self.assertEqual(receipt.failure_class, ExecutabilityFailure.HOST_LOW_POWER_CONTAMINATION.value)

    def test_baseline_timeout_is_infrastructure_timeout(self) -> None:
        receipt, _ = self._execute(
            _baseline(
                evaluator_validities=("NOT_EVALUABLE", "NOT_EVALUABLE"),
                failure_signatures=("TIMEOUT:test", "TIMEOUT:repository_setup"),
            )
        )
        self.assertEqual(receipt.failure_class, ExecutabilityFailure.EXECUTION_TIMEOUT.value)

    def test_unexplained_wall_fails_timing_reconciliation(self) -> None:
        receipt, _ = self._execute(_baseline(timing=_timing(total_wall_seconds=100.0)))
        self.assertEqual(receipt.failure_class, ExecutabilityFailure.TIMING_RECONCILIATION.value)

    def test_provider_provenance_count_mismatch_fails(self) -> None:
        receipt, _ = self._execute(
            _baseline(timing=_timing(provider_call_count=1, provider_terminal_count=1))
        )
        self.assertEqual(receipt.failure_class, ExecutabilityFailure.PROVIDER_PROVENANCE.value)

    def test_provider_timeout_retry_or_transport_error_fails(self) -> None:
        for field in ("provider_retry_count", "provider_timeout_count", "provider_transport_error_count"):
            with self.subTest(field=field):
                receipt, _ = self._execute(_baseline(timing=_timing(**{field: 1})))
                self.assertEqual(receipt.failure_class, ExecutabilityFailure.PROVIDER_PATH.value)

    def test_materialization_drift_fails_before_scientific_block(self) -> None:
        called = False

        def scientific() -> ScientificBlockResult:
            nonlocal called
            called = True
            return ScientificBlockResult(_timing(), 1)

        receipt, _ = self._execute(
            _baseline(task_tree_digest_match=False), scientific_block=scientific
        )
        self.assertEqual(receipt.failure_class, ExecutabilityFailure.MATERIALIZATION.value)
        self.assertFalse(called)
        self.assertFalse(receipt.scientific_block_executed)

    def test_invalid_nonfinite_and_nondeterministic_baselines_fail(self) -> None:
        cases = (
            _baseline(evaluator_validities=("VALID", "INVALID")),
            _baseline(scores=(0.5, float("nan"))),
            _baseline(scores=(0.5, 0.6)),
            _baseline(parser_contract_satisfied=False),
        )
        for baseline in cases:
            with self.subTest(baseline=baseline):
                receipt, _ = self._execute(baseline)
                self.assertEqual(receipt.failure_class, ExecutabilityFailure.BASELINE.value)

    def test_power_acquisition_and_provenance_fail_closed(self) -> None:
        receipt, _ = self._execute(lease=_Lease(acquire_error=True))
        self.assertEqual(receipt.failure_class, ExecutabilityFailure.POWER_INHIBITION_UNAVAILABLE.value)
        receipt, _ = self._execute(events=_Events(error=True))
        self.assertEqual(receipt.failure_class, ExecutabilityFailure.POWER_PROVENANCE.value)

    def test_release_failure_prevents_admission(self) -> None:
        receipt, _ = self._execute(lease=_Lease(release_error=True))
        self.assertEqual(receipt.failure_class, ExecutabilityFailure.POWER_INHIBITION_RELEASE.value)

    def test_scientific_block_runs_only_after_preflight_and_is_reconciled(self) -> None:
        receipt, _ = self._execute(
            scientific_block=lambda: ScientificBlockResult(
                timing=_timing(
                    provider_wait_seconds=2.0,
                    total_wall_seconds=6.0,
                    provider_call_count=2,
                    provider_terminal_count=2,
                    provider_timing_count=2,
                ),
                generation_calls_executed=2,
            )
        )
        self.assertTrue(receipt.admitted)
        self.assertTrue(receipt.scientific_block_executed)
        self.assertEqual(receipt.generation_calls_executed, 2)

    def test_scientific_exception_has_distinct_failure_class(self) -> None:
        def fail() -> ScientificBlockResult:
            raise RuntimeError("injected scientific failure")

        receipt, _ = self._execute(scientific_block=fail)
        self.assertEqual(receipt.failure_class, ExecutabilityFailure.SCIENTIFIC_EXECUTION.value)
        self.assertTrue(receipt.scientific_block_executed)
        self.assertIsNone(receipt.generation_calls_executed)

    def test_consumed_qualification_adversarial_matrix_matches(self) -> None:
        results = _adversarial_qualification()
        self.assertEqual(len(results), 7)
        self.assertTrue(all(result["matched_expected"] for result in results))
        self.assertTrue(all(result["generation_calls_executed"] == 0 for result in results))


if __name__ == "__main__":
    unittest.main()
