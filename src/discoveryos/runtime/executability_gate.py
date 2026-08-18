from __future__ import annotations

import ctypes
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Callable, Protocol


class ExecutabilityFailure(str, Enum):
    POWER_INHIBITION_UNAVAILABLE = "INFRA_FAILURE_POWER_INHIBITION_UNAVAILABLE"
    POWER_INHIBITION_RELEASE = "INFRA_FAILURE_POWER_INHIBITION_RELEASE_FAILED"
    POWER_PROVENANCE = "INFRA_FAILURE_POWER_STATE_PROVENANCE_UNAVAILABLE"
    HOST_LOW_POWER_CONTAMINATION = "INFRA_FAILURE_HOST_LOW_POWER_STATE_CONTAMINATION"
    EXECUTION_TIMEOUT = "INFRA_FAILURE_EXECUTION_TIMEOUT"
    TIMING_RECONCILIATION = "INFRA_FAILURE_TIMING_RECONCILIATION"
    PROVIDER_PROVENANCE = "INFRA_FAILURE_PROVIDER_PROVENANCE_INCOMPLETE"
    PROVIDER_PATH = "INFRA_FAILURE_PROVIDER_PATH"
    MATERIALIZATION = "MATERIALIZATION_DEFECT"
    BASELINE = "TASK_NOT_BASELINE_EVALUABLE"
    BASELINE_EXECUTION = "INFRA_FAILURE_BASELINE_EXECUTION_EXCEPTION"
    SCIENTIFIC_EXECUTION = "INFRA_FAILURE_SCIENTIFIC_EXECUTION_EXCEPTION"


@dataclass(frozen=True, slots=True)
class PowerEvent:
    record_id: int
    provider: str
    event_id: int
    timestamp_utc: str
    kind: str
    message_sha256: str


@dataclass(frozen=True, slots=True)
class PowerLeaseReceipt:
    acquired: bool
    provider: str
    request_types: tuple[str, ...]
    acquired_at_utc: str | None
    released_at_utc: str | None
    failure: str | None = None


@dataclass(frozen=True, slots=True)
class TimingBreakdown:
    provider_wait_seconds: float = 0.0
    repository_setup_seconds: float = 0.0
    build_test_seconds: float = 0.0
    evaluator_seconds: float = 0.0
    harness_overhead_seconds: float = 0.0
    cpu_seconds: float = 0.0
    total_wall_seconds: float = 0.0
    provider_call_count: int = 0
    provider_terminal_count: int = 0
    provider_timing_count: int = 0
    provider_retry_count: int = 0
    provider_timeout_count: int = 0
    provider_transport_error_count: int = 0

    @property
    def accounted_wall_seconds(self) -> float:
        return sum(
            (
                self.provider_wait_seconds,
                self.repository_setup_seconds,
                self.build_test_seconds,
                self.evaluator_seconds,
                self.harness_overhead_seconds,
            )
        )

    @property
    def unexplained_wall_seconds(self) -> float:
        return self.total_wall_seconds - self.accounted_wall_seconds


@dataclass(frozen=True, slots=True)
class BaselineProbeResult:
    materialization_replayed: bool
    task_tree_digest_match: bool
    evaluator_validities: tuple[str, ...]
    scores: tuple[float, ...]
    parser_contract_satisfied: bool
    failure_signatures: tuple[str | None, ...]
    timing: TimingBreakdown
    provenance: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ScientificBlockResult:
    timing: TimingBreakdown
    generation_calls_executed: int
    provenance: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ExecutabilityPolicy:
    baseline_replays: int = 2
    score_tolerance: float = 1e-12
    unexplained_wall_seconds: float = 2.0
    unexplained_wall_fraction: float = 0.20
    power_event_lookback_seconds: float = 86_400.0


@dataclass(frozen=True, slots=True)
class ExecutabilityGateReceipt:
    version: str
    block_id: str
    status: str
    admitted: bool
    failure_class: str | None
    failure_detail: str | None
    generation_calls_executed: int | None
    session_started_utc: str
    session_finished_utc: str
    power_lease: PowerLeaseReceipt
    power_events: tuple[PowerEvent, ...]
    baseline: BaselineProbeResult | None
    scientific_block_executed: bool
    scientific_block: ScientificBlockResult | None


class PowerLease(Protocol):
    def acquire(self) -> None: ...

    def release(self) -> None: ...

    @property
    def receipt(self) -> PowerLeaseReceipt: ...


class PowerEventSource(Protocol):
    def query(self, start_utc: datetime, end_utc: datetime) -> tuple[PowerEvent, ...]: ...


class PowerLeaseError(RuntimeError):
    pass


class WindowsPowerInhibitionLease:
    """Process-scoped Windows power request held through post-run reconciliation."""

    _REQUESTS = (
        (0, "DISPLAY_REQUIRED"),
        (1, "SYSTEM_REQUIRED"),
        (3, "EXECUTION_REQUIRED"),
    )
    _ES_CONTINUOUS = 0x80000000
    _ES_SYSTEM_REQUIRED = 0x00000001
    _ES_DISPLAY_REQUIRED = 0x00000002

    def __init__(self, reason: str) -> None:
        self.reason = reason
        self._handle: int | None = None
        self._set: list[tuple[int, str]] = []
        self._reason_buffer = None
        self._acquired_at: str | None = None
        self._released_at: str | None = None
        self._failure: str | None = None
        self._thread_execution_state_set = False

    def acquire(self) -> None:
        if sys.platform != "win32":
            self._failure = "Windows power requests are unavailable on this host"
            raise PowerLeaseError(self._failure)

        class ReasonContext(ctypes.Structure):
            _fields_ = (("Version", ctypes.c_ulong), ("Flags", ctypes.c_ulong), ("Reason", ctypes.c_void_p))

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.PowerCreateRequest.argtypes = (ctypes.POINTER(ReasonContext),)
        kernel32.PowerCreateRequest.restype = ctypes.c_void_p
        kernel32.PowerSetRequest.argtypes = (ctypes.c_void_p, ctypes.c_int)
        kernel32.PowerSetRequest.restype = ctypes.c_bool
        kernel32.PowerClearRequest.argtypes = (ctypes.c_void_p, ctypes.c_int)
        kernel32.PowerClearRequest.restype = ctypes.c_bool
        kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
        kernel32.CloseHandle.restype = ctypes.c_bool
        kernel32.SetThreadExecutionState.argtypes = (ctypes.c_ulong,)
        kernel32.SetThreadExecutionState.restype = ctypes.c_ulong

        self._reason_buffer = ctypes.create_unicode_buffer(self.reason)
        context = ReasonContext(0, 1, ctypes.cast(self._reason_buffer, ctypes.c_void_p))
        handle = kernel32.PowerCreateRequest(ctypes.byref(context))
        invalid = ctypes.c_void_p(-1).value
        if not handle or handle == invalid:
            self._failure = f"PowerCreateRequest failed: winerror={ctypes.get_last_error()}"
            raise PowerLeaseError(self._failure)
        self._handle = int(handle)
        try:
            for request_type, name in self._REQUESTS:
                if not kernel32.PowerSetRequest(ctypes.c_void_p(self._handle), request_type):
                    raise PowerLeaseError(f"PowerSetRequest({name}) failed: winerror={ctypes.get_last_error()}")
                self._set.append((request_type, name))
            state = self._ES_CONTINUOUS | self._ES_SYSTEM_REQUIRED | self._ES_DISPLAY_REQUIRED
            if not kernel32.SetThreadExecutionState(state):
                raise PowerLeaseError(
                    f"SetThreadExecutionState(DISPLAY+SYSTEM) failed: winerror={ctypes.get_last_error()}"
                )
            self._thread_execution_state_set = True
        except BaseException as error:
            self._failure = str(error)
            self.release()
            raise
        self._acquired_at = _utc_now()

    def release(self) -> None:
        if self._handle is None:
            return
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.PowerClearRequest.argtypes = (ctypes.c_void_p, ctypes.c_int)
        kernel32.PowerClearRequest.restype = ctypes.c_bool
        kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
        kernel32.CloseHandle.restype = ctypes.c_bool
        kernel32.SetThreadExecutionState.argtypes = (ctypes.c_ulong,)
        kernel32.SetThreadExecutionState.restype = ctypes.c_ulong
        failures: list[str] = []
        if self._thread_execution_state_set:
            if not kernel32.SetThreadExecutionState(self._ES_CONTINUOUS):
                failures.append(f"SetThreadExecutionState(clear):winerror={ctypes.get_last_error()}")
            self._thread_execution_state_set = False
        for request_type, name in reversed(self._set):
            if not kernel32.PowerClearRequest(ctypes.c_void_p(self._handle), request_type):
                failures.append(f"PowerClearRequest({name}):winerror={ctypes.get_last_error()}")
        if not kernel32.CloseHandle(ctypes.c_void_p(self._handle)):
            failures.append(f"CloseHandle:winerror={ctypes.get_last_error()}")
        self._released_at = _utc_now()
        self._handle = None
        if failures:
            self._failure = ";".join(failures)
            raise PowerLeaseError(self._failure)

    @property
    def receipt(self) -> PowerLeaseReceipt:
        return PowerLeaseReceipt(
            acquired=self._acquired_at is not None,
            provider="WINDOWS_POWER_REQUEST_API+SET_THREAD_EXECUTION_STATE",
            request_types=tuple(name for _, name in self._set),
            acquired_at_utc=self._acquired_at,
            released_at_utc=self._released_at,
            failure=self._failure,
        )


class WindowsPowerEventSource:
    _SCRIPT = r"""
$start = [DateTimeOffset]::Parse($env:DISCOVERYOS_POWER_QUERY_START).LocalDateTime
$end = [DateTimeOffset]::Parse($env:DISCOVERYOS_POWER_QUERY_END).LocalDateTime
$null = Get-WinEvent -ListLog System -ErrorAction Stop
$events = Get-WinEvent -FilterHashtable @{LogName='System'; StartTime=$start; EndTime=$end} -ErrorAction SilentlyContinue |
    Where-Object {
        ($_.ProviderName -eq 'Microsoft-Windows-Kernel-Power' -and $_.Id -in 42,107,506,507) -or
        ($_.ProviderName -eq 'Microsoft-Windows-Power-Troubleshooter' -and $_.Id -eq 1) -or
        ($_.ProviderName -eq 'Microsoft-Windows-Kernel-General' -and $_.Id -eq 1)
    } |
    Sort-Object TimeCreated |
    ForEach-Object {
        [pscustomobject]@{
            record_id = [int64]$_.RecordId
            provider = $_.ProviderName
            event_id = [int]$_.Id
            timestamp_utc = $_.TimeCreated.ToUniversalTime().ToString('o')
            message = $_.Message
        }
    }
ConvertTo-Json -Compress -Depth 3 -InputObject @($events)
"""

    def __init__(self, executable: str | None = None) -> None:
        self.executable = executable or shutil.which("pwsh") or shutil.which("powershell") or ""

    def query(self, start_utc: datetime, end_utc: datetime) -> tuple[PowerEvent, ...]:
        if sys.platform != "win32" or not self.executable:
            raise RuntimeError("Windows System event query is unavailable")
        environment = os.environ.copy()
        environment["DISCOVERYOS_POWER_QUERY_START"] = start_utc.isoformat()
        environment["DISCOVERYOS_POWER_QUERY_END"] = end_utc.isoformat()
        result = subprocess.run(
            (self.executable, "-NoProfile", "-NonInteractive", "-Command", self._SCRIPT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=environment,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError("power event query failed: " + result.stderr.strip())
        raw = result.stdout.strip()
        values = json.loads(raw) if raw else []
        if isinstance(values, dict):
            values = [values]
        return tuple(
            PowerEvent(
                record_id=int(item["record_id"]),
                provider=str(item["provider"]),
                event_id=int(item["event_id"]),
                timestamp_utc=str(item["timestamp_utc"]),
                kind=_power_event_kind(str(item["provider"]), int(item["event_id"])),
                message_sha256=hashlib.sha256(str(item.get("message", "")).encode("utf-8")).hexdigest(),
            )
            for item in values
        )


class ExecutabilityGate:
    def __init__(
        self,
        *,
        lease_factory: Callable[[str], PowerLease],
        event_source: PowerEventSource,
        policy: ExecutabilityPolicy = ExecutabilityPolicy(),
    ) -> None:
        self.lease_factory = lease_factory
        self.event_source = event_source
        self.policy = policy

    def execute(
        self,
        block_id: str,
        baseline_probe: Callable[[], BaselineProbeResult],
        scientific_block: Callable[[], ScientificBlockResult] | None = None,
    ) -> ExecutabilityGateReceipt:
        session_started = datetime.now(timezone.utc)
        lease = self.lease_factory(f"DiscoveryOS executability session: {block_id}")
        baseline: BaselineProbeResult | None = None
        events: tuple[PowerEvent, ...] = ()
        failure: ExecutabilityFailure | None = None
        detail: str | None = None
        scientific_executed = False
        scientific_result: ScientificBlockResult | None = None
        try:
            lease.acquire()
        except BaseException as error:
            failure = ExecutabilityFailure.POWER_INHIBITION_UNAVAILABLE
            detail = f"{type(error).__name__}:{error}"
        else:
            try:
                preflight_finished = datetime.now(timezone.utc)
                lookback = timedelta(seconds=self.policy.power_event_lookback_seconds)
                queried = self.event_source.query(session_started - lookback, preflight_finished)
                events = _overlapping_power_events(queried, session_started, preflight_finished)
                if events:
                    failure = ExecutabilityFailure.HOST_LOW_POWER_CONTAMINATION
                    detail = "host was already in a low-power state when the inhibition lease was acquired"
            except BaseException as error:
                failure = ExecutabilityFailure.POWER_PROVENANCE
                detail = f"power preflight provenance unavailable:{type(error).__name__}:{error}"
            try:
                if failure is None:
                    baseline = baseline_probe()
                    failure, detail = self._validate_baseline(baseline)
                if failure is None and scientific_block is not None:
                    scientific_executed = True
                    try:
                        scientific_result = scientific_block()
                        failure, detail = self._validate_timing(scientific_result.timing)
                    except BaseException as error:
                        failure = ExecutabilityFailure.SCIENTIFIC_EXECUTION
                        detail = f"{type(error).__name__}:{error}"
            except BaseException as error:
                failure = ExecutabilityFailure.BASELINE_EXECUTION
                detail = f"{type(error).__name__}:{error}"
            finally:
                finished_for_query = datetime.now(timezone.utc)
                try:
                    queried = self.event_source.query(session_started - lookback, finished_for_query)
                    reconciled_events = _overlapping_power_events(queried, session_started, finished_for_query)
                    events = tuple(dict.fromkeys((*events, *reconciled_events)))
                    if reconciled_events:
                        failure = ExecutabilityFailure.HOST_LOW_POWER_CONTAMINATION
                        detail = "host low-power state overlaps the execution window"
                except BaseException as error:
                    failure = ExecutabilityFailure.POWER_PROVENANCE
                    detail = f"power provenance unavailable:{type(error).__name__}:{error}"
                try:
                    lease.release()
                except BaseException as error:
                    if failure is None:
                        failure = ExecutabilityFailure.POWER_INHIBITION_RELEASE
                        detail = f"{type(error).__name__}:{error}"
        session_finished = datetime.now(timezone.utc)
        admitted = failure is None
        return ExecutabilityGateReceipt(
            version="DISCOVERYOS_EXECUTABILITY_GATE_V1",
            block_id=block_id,
            status="EXECUTABILITY_GATE_PASS" if admitted else "EXECUTABILITY_GATE_FAIL_CLOSED",
            admitted=admitted,
            failure_class=failure.value if failure else None,
            failure_detail=detail,
            generation_calls_executed=(
                scientific_result.generation_calls_executed
                if scientific_result
                else None if scientific_executed else 0
            ),
            session_started_utc=session_started.isoformat(),
            session_finished_utc=session_finished.isoformat(),
            power_lease=lease.receipt,
            power_events=events,
            baseline=baseline,
            scientific_block_executed=scientific_executed,
            scientific_block=scientific_result,
        )

    def _validate_baseline(
        self, baseline: BaselineProbeResult
    ) -> tuple[ExecutabilityFailure | None, str | None]:
        if not baseline.materialization_replayed or not baseline.task_tree_digest_match:
            return ExecutabilityFailure.MATERIALIZATION, "materialized task bytes/tree did not replay"
        if len(baseline.scores) < self.policy.baseline_replays:
            return ExecutabilityFailure.BASELINE, "insufficient independent baseline replays"
        if (
            not baseline.parser_contract_satisfied
            or len(baseline.evaluator_validities) != len(baseline.scores)
            or len(baseline.failure_signatures) != len(baseline.scores)
            or any(value != "VALID" for value in baseline.evaluator_validities)
            or any(not math.isfinite(value) for value in baseline.scores)
            or any(signature for signature in baseline.failure_signatures)
        ):
            if any(signature and "TIMEOUT" in signature for signature in baseline.failure_signatures):
                return ExecutabilityFailure.EXECUTION_TIMEOUT, "baseline execution timed out"
            return ExecutabilityFailure.BASELINE, "baseline evaluator/parser did not produce finite VALID evidence"
        anchor = baseline.scores[0]
        if any(abs(score - anchor) > self.policy.score_tolerance for score in baseline.scores[1:]):
            return ExecutabilityFailure.BASELINE, "baseline replay score is nondeterministic"

        return self._validate_timing(baseline.timing)

    def _validate_timing(
        self, timing: TimingBreakdown
    ) -> tuple[ExecutabilityFailure | None, str | None]:
        numbers = (
            timing.provider_wait_seconds,
            timing.repository_setup_seconds,
            timing.build_test_seconds,
            timing.evaluator_seconds,
            timing.harness_overhead_seconds,
            timing.cpu_seconds,
            timing.total_wall_seconds,
        )
        if any(not math.isfinite(value) or value < 0 for value in numbers):
            return ExecutabilityFailure.TIMING_RECONCILIATION, "timing contains negative or non-finite values"
        allowance = max(
            self.policy.unexplained_wall_seconds,
            timing.total_wall_seconds * self.policy.unexplained_wall_fraction,
        )
        if abs(timing.unexplained_wall_seconds) > allowance:
            return ExecutabilityFailure.TIMING_RECONCILIATION, (
                f"unexplained_wall_seconds={timing.unexplained_wall_seconds:.6f} allowance={allowance:.6f}"
            )
        if not (
            timing.provider_call_count == timing.provider_terminal_count == timing.provider_timing_count
        ):
            return ExecutabilityFailure.PROVIDER_PROVENANCE, "provider call/terminal/timing counts differ"
        counts = (
            timing.provider_call_count,
            timing.provider_terminal_count,
            timing.provider_timing_count,
            timing.provider_retry_count,
            timing.provider_timeout_count,
            timing.provider_transport_error_count,
        )
        if any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in counts):
            return ExecutabilityFailure.PROVIDER_PROVENANCE, "provider provenance counts are invalid"
        if timing.provider_retry_count or timing.provider_timeout_count or timing.provider_transport_error_count:
            return ExecutabilityFailure.PROVIDER_PATH, (
                f"retry={timing.provider_retry_count} timeout={timing.provider_timeout_count} "
                f"transport_error={timing.provider_transport_error_count}"
            )
        return None, None


def _power_event_kind(provider: str, event_id: int) -> str:
    mapping = {
        ("Microsoft-Windows-Kernel-Power", 42): "ENTER_SLEEP_OR_HIBERNATE",
        ("Microsoft-Windows-Kernel-Power", 107): "RESUME_FROM_SLEEP",
        ("Microsoft-Windows-Kernel-Power", 506): "ENTER_MODERN_STANDBY",
        ("Microsoft-Windows-Kernel-Power", 507): "EXIT_MODERN_STANDBY",
        ("Microsoft-Windows-Power-Troubleshooter", 1): "POWER_TROUBLESHOOTER_RESUME",
        ("Microsoft-Windows-Kernel-General", 1): "SYSTEM_CLOCK_CHANGE",
    }
    return mapping.get((provider, event_id), "OTHER_POWER_EVENT")


def _overlapping_power_events(
    events: tuple[PowerEvent, ...], start_utc: datetime, end_utc: datetime
) -> tuple[PowerEvent, ...]:
    """Return transitions in-window plus an unmatched prior low-power entry."""

    ordered = tuple(sorted(events, key=lambda event: event.timestamp_utc))
    in_window = [
        event
        for event in ordered
        if start_utc <= datetime.fromisoformat(event.timestamp_utc.replace("Z", "+00:00")) <= end_utc
    ]
    before = [
        event
        for event in ordered
        if datetime.fromisoformat(event.timestamp_utc.replace("Z", "+00:00")) < start_utc
        and event.kind in {
            "ENTER_SLEEP_OR_HIBERNATE",
            "RESUME_FROM_SLEEP",
            "ENTER_MODERN_STANDBY",
            "EXIT_MODERN_STANDBY",
            "POWER_TROUBLESHOOTER_RESUME",
        }
    ]
    if before and before[-1].kind in {"ENTER_SLEEP_OR_HIBERNATE", "ENTER_MODERN_STANDBY"}:
        in_window.insert(0, before[-1])
    return tuple(dict.fromkeys(in_window))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
