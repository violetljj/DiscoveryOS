from __future__ import annotations

import json
import inspect
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from discoveryos.contracts.executable import CommandSpec, ExecutableCandidateBundle, path_is_within
from discoveryos.contracts.models import (
    CandidateSpec,
    EvaluationOutput,
    EvidenceValidity,
    ExperimentSpec,
    FailureKind,
    ProblemContract,
    ResourceUsage,
)
from discoveryos.runtime.artifacts import ArtifactStore
from discoveryos.runtime.processes import process_rss_bytes
from discoveryos.util import jsonable


@dataclass(frozen=True, slots=True)
class CommandResult:
    step: str
    argv: tuple[str, ...]
    exit_code: int | None
    stdout: str
    stderr: str
    wall_seconds: float
    cpu_seconds: float
    peak_rss_bytes: int
    timed_out: bool
    uses_gpu: bool
    uses_device: bool


class IsolatedRepositoryRunner:
    """Runs a frozen patch in a disposable Git worktree.

    This is process and repository isolation, not a hostile-code sandbox. Final
    blind execution still requires a separate service identity in production.
    """

    def __init__(self, artifacts: ArtifactStore, *, contract: ProblemContract | None = None) -> None:
        self.artifacts = artifacts
        self.contract = contract

    def run(
        self,
        bundle: ExecutableCandidateBundle,
        *,
        candidate_artifact_digest: str,
        experiment: ExperimentSpec,
        data: bytes | None,
    ) -> EvaluationOutput:
        started_run = time.monotonic()
        policy_issue = self._policy_issue(bundle)
        if policy_issue:
            return self._failure(
                FailureKind.PATH_VIOLATION,
                policy_issue,
                (),
                self._usage([], wall_seconds=time.monotonic() - started_run),
            )
        repository = Path(bundle.base_repository).resolve()
        deadline = time.monotonic() + experiment.resources.wall_seconds if experiment.resources.wall_seconds > 0 else None
        logs: list[CommandResult] = []
        worktree: Path | None = None
        try:
            self._verify_repository(repository, bundle.base_commit, self._remaining(deadline))
            with tempfile.TemporaryDirectory(prefix="discoveryos-worktree-") as temporary:
                worktree = Path(temporary) / "repo"
                self._git(repository, ("worktree", "add", "--detach", "--force", str(worktree), bundle.base_commit), self._remaining(deadline))
                try:
                    for patch_index, patch in enumerate(bundle.effective_patch_stack):
                        patch_failure = self._apply_patch(
                            worktree,
                            patch,
                            self._remaining(deadline),
                            patch_index=patch_index,
                            recount=bundle.patch_apply_policy == "recount_hunks",
                        )
                        if patch_failure is not None:
                            logs.append(patch_failure)
                            lowered = patch_failure.stderr.lower()
                            category = (
                                "PATCH_PARSE_FAILURE"
                                if any(marker in lowered for marker in ("corrupt patch", "patch fragment", "unrecognized input"))
                                else "PATCH_APPLY_FAILURE"
                            )
                            return self._failure(
                                FailureKind.PATCH_REJECTED,
                                f"{category}:patch_index={patch_index}:exit={patch_failure.exit_code}",
                                self._store_logs(logs),
                                self._usage(logs, wall_seconds=time.monotonic() - started_run),
                            )
                    touched = self._changed_paths(worktree, bundle.base_commit, self._remaining(deadline))
                    if touched != tuple(sorted(bundle.touched_paths)):
                        return self._failure(
                            FailureKind.PATH_VIOLATION,
                            "TOUCHED_PATH_MISMATCH:expected=" + ",".join(sorted(bundle.touched_paths)) + ":actual=" + ",".join(touched),
                            self._store_logs(logs),
                            self._usage(logs, wall_seconds=time.monotonic() - started_run),
                        )
                    if any(path_is_within(path, bundle.forbidden_paths) for path in touched):
                        return self._failure(
                            FailureKind.PATH_VIOLATION,
                            "FORBIDDEN_PATH_TOUCHED",
                            self._store_logs(logs),
                            self._usage(logs, wall_seconds=time.monotonic() - started_run),
                        )
                    if not bundle.verify_environment_lock(worktree):
                        return self._failure(
                            FailureKind.PATCH_REJECTED,
                            "ENVIRONMENT_LOCK_MISMATCH",
                            self._store_logs(logs),
                            self._usage(logs, wall_seconds=time.monotonic() - started_run),
                        )
                    entrypoint = worktree / bundle.entrypoint
                    if not entrypoint.is_file() or entrypoint.is_symlink():
                        return self._failure(
                            FailureKind.PATCH_REJECTED,
                            "ENTRYPOINT_MISSING_OR_SYMLINK",
                            self._store_logs(logs),
                            self._usage(logs, wall_seconds=time.monotonic() - started_run),
                        )
                    runtime_dir = worktree / ".discoveryos"
                    runtime_dir.mkdir(exist_ok=True)
                    data_path = runtime_dir / "evaluation-data.bin"
                    if data is not None:
                        data_path.write_bytes(data)
                    environment = os.environ.copy()
                    environment.update(
                        {
                            "DISCOVERYOS_DATA_PATH": str(data_path) if data is not None else "",
                            "DISCOVERYOS_ENTRYPOINT": bundle.entrypoint,
                            "DISCOVERYOS_FIDELITY": experiment.fidelity.value,
                            "DISCOVERYOS_SEED": str(experiment.seed),
                            "DISCOVERYOS_TRIAL_ID": experiment.trial_id,
                            "DISCOVERYOS_RUNG_ID": experiment.rung_id,
                            "PYTHONHASHSEED": str(experiment.seed),
                        }
                    )
                    for step, command, failure_kind in (
                        ("build", bundle.build_command, FailureKind.BUILD_FAILED),
                        ("test", bundle.test_command, FailureKind.TEST_FAILED),
                        ("evaluation", bundle.evaluation_command, FailureKind.EVALUATION_FAILED),
                    ):
                        result = _run_command(step, command, worktree, environment, self._remaining(deadline))
                        logs.append(result)
                        if result.timed_out:
                            return self._failure(
                                FailureKind.TIMEOUT,
                                f"TIMEOUT:{step}",
                                self._store_logs(logs),
                                self._usage(logs, wall_seconds=time.monotonic() - started_run),
                            )
                        if result.exit_code != 0:
                            kind = _classify_process_failure(result, failure_kind)
                            signature = f"{kind.value}:{step}:exit={result.exit_code}"
                            return self._failure(
                                kind,
                                signature,
                                self._store_logs(logs),
                                self._usage(logs, wall_seconds=time.monotonic() - started_run),
                            )
                    after_commands = self._changed_paths(
                        worktree,
                        bundle.base_commit,
                        self._remaining(deadline),
                        expected_untracked=bundle.touched_paths,
                    )
                    if after_commands != touched:
                        return self._failure(
                            FailureKind.PATH_VIOLATION,
                            "TRACKED_FILES_MUTATED_DURING_EXECUTION",
                            self._store_logs(logs),
                            self._usage(logs, wall_seconds=time.monotonic() - started_run),
                        )
                    result_payload = _parse_evaluation_output(logs[-1].stdout)
                    reported = ResourceUsage(**result_payload.get("usage", {}))
                    usage = self._usage(logs, reported, wall_seconds=time.monotonic() - started_run)
                    artifact_digests = self._store_logs(logs)
                    receipt_digest = self.artifacts.put_json(
                        {
                            "candidate_artifact_digest": candidate_artifact_digest,
                            "base_commit": bundle.base_commit,
                            "experiment_id": experiment.experiment_id,
                            "trial_id": experiment.trial_id,
                            "rung_id": experiment.rung_id,
                            "attempt_id": experiment.attempt_id,
                            "touched_paths": touched,
                            "command_log_artifacts": artifact_digests,
                            "resource_usage": usage,
                        },
                        metadata={"kind": "executable-candidate-run-receipt-v1"},
                    )
                    output_artifacts = tuple(dict.fromkeys((*artifact_digests, receipt_digest)))
                    validity = EvidenceValidity(result_payload.get("validity", EvidenceValidity.VALID.value))
                    failure_kind_value = result_payload.get("failure_kind")
                    return EvaluationOutput.from_metrics(
                        {name: float(value) for name, value in result_payload["metrics"].items()},
                        validity=validity,
                        failure_signature=result_payload.get("failure_signature"),
                        failure_kind=FailureKind(failure_kind_value) if failure_kind_value else None,
                        artifacts=output_artifacts,
                        reported_usage=usage,
                    )
                finally:
                    self._remove_worktree(repository, worktree)
        except TimeoutError:
            return self._failure(
                FailureKind.TIMEOUT,
                "TIMEOUT:repository_setup",
                self._store_logs(logs),
                self._usage(logs, wall_seconds=time.monotonic() - started_run),
            )
        except (ValueError, KeyError, json.JSONDecodeError) as error:
            return self._failure(
                FailureKind.EVALUATION_FAILED,
                f"EVALUATION_OUTPUT_INVALID:{type(error).__name__}",
                self._store_logs(logs),
                self._usage(logs, wall_seconds=time.monotonic() - started_run),
            )
        except OSError as error:
            return self._failure(
                FailureKind.WORKER_CRASH,
                f"WORKER_CRASH:{type(error).__name__}",
                self._store_logs(logs),
                self._usage(logs, wall_seconds=time.monotonic() - started_run),
            )
        except (subprocess.SubprocessError, RuntimeError) as error:
            return self._failure(
                FailureKind.PATCH_REJECTED,
                f"REPOSITORY_RUNNER_ERROR:{type(error).__name__}",
                self._store_logs(logs),
                self._usage(logs, wall_seconds=time.monotonic() - started_run),
            )

    def _policy_issue(self, bundle: ExecutableCandidateBundle) -> str | None:
        if self.contract is None:
            return None
        for path in bundle.touched_paths:
            if not path_is_within(path, self.contract.mutable_paths):
                return f"CONTRACT_MUTABLE_PATH_VIOLATION:{path}"
            if path_is_within(path, self.contract.forbidden_paths):
                return f"CONTRACT_FORBIDDEN_PATH_VIOLATION:{path}"
        return None

    @staticmethod
    def _verify_repository(repository: Path, commit: str, timeout: float | None) -> None:
        if not repository.is_dir():
            raise RuntimeError("base repository does not exist")
        root = IsolatedRepositoryRunner._git(repository, ("rev-parse", "--show-toplevel"), timeout).stdout.strip()
        if Path(root).resolve() != repository:
            raise RuntimeError("base repository must be the Git root")
        IsolatedRepositoryRunner._git(repository, ("cat-file", "-e", f"{commit}^{{commit}}"), timeout)

    @staticmethod
    def _apply_patch(
        worktree: Path,
        patch: str,
        timeout: float | None,
        *,
        patch_index: int,
        recount: bool,
    ) -> CommandResult | None:
        started = time.monotonic()
        recount_flag = ("--recount",) if recount else ()
        for arguments in (
            ("apply", "--check", *recount_flag, "-"),
            ("apply", "--whitespace=nowarn", *recount_flag, "-"),
        ):
            result = subprocess.run(
                ("git", "-C", str(worktree), *arguments),
                input=patch,
                text=True,
                encoding="utf-8",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                check=False,
            )
            if result.returncode != 0:
                return CommandResult(
                    step="patch",
                    argv=("git", *arguments[:-1], f"<patch-{patch_index}>"),
                    exit_code=result.returncode,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    wall_seconds=time.monotonic() - started,
                    cpu_seconds=0.0,
                    peak_rss_bytes=0,
                    timed_out=False,
                    uses_gpu=False,
                    uses_device=False,
                )
        return None

    @staticmethod
    def _changed_paths(
        worktree: Path,
        commit: str,
        timeout: float | None,
        *,
        expected_untracked: tuple[str, ...] | None = None,
    ) -> tuple[str, ...]:
        result = IsolatedRepositoryRunner._git(
            worktree,
            ("diff", "--name-only", "--no-renames", commit, "--"),
            timeout,
        )
        paths = {line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()}
        untracked_result = IsolatedRepositoryRunner._git(
            worktree,
            ("ls-files", "--others", "--exclude-standard"),
            timeout,
        )
        untracked = {line.strip().replace("\\", "/") for line in untracked_result.stdout.splitlines() if line.strip()}
        paths.update(untracked if expected_untracked is None else untracked.intersection(expected_untracked))
        ordered_paths = tuple(sorted(paths))
        if any((worktree / path).is_symlink() for path in ordered_paths):
            raise RuntimeError("symlink patches are not admitted")
        return ordered_paths

    @staticmethod
    def _git(repository: Path, arguments: tuple[str, ...], timeout: float | None) -> subprocess.CompletedProcess[str]:
        try:
            result = subprocess.run(
                ("git", "-C", str(repository), *arguments),
                text=True,
                encoding="utf-8",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise TimeoutError from error
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "git command failed")
        return result

    @staticmethod
    def _remove_worktree(repository: Path, worktree: Path) -> None:
        try:
            subprocess.run(
                ("git", "-C", str(repository), "worktree", "remove", "--force", str(worktree)),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=30,
                check=False,
            )
            subprocess.run(
                ("git", "-C", str(repository), "worktree", "prune"),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            pass

    def _store_logs(self, logs: list[CommandResult]) -> tuple[str, ...]:
        return tuple(
            self.artifacts.put_json(jsonable(result), metadata={"kind": "candidate-command-log-v1", "step": result.step})
            for result in logs
        )

    @staticmethod
    def _usage(
        logs: list[CommandResult],
        reported: ResourceUsage | None = None,
        *,
        wall_seconds: float | None = None,
    ) -> ResourceUsage:
        external = reported or ResourceUsage()
        return ResourceUsage(
            llm_input_tokens=external.llm_input_tokens,
            llm_output_tokens=external.llm_output_tokens,
            llm_cache_tokens=external.llm_cache_tokens,
            cpu_seconds=sum(result.cpu_seconds for result in logs),
            gpu_seconds=external.gpu_seconds or sum(result.wall_seconds for result in logs if result.uses_gpu),
            device_seconds=external.device_seconds or sum(result.wall_seconds for result in logs if result.uses_device),
            wall_seconds=wall_seconds if wall_seconds is not None else sum(result.wall_seconds for result in logs),
            peak_rss_bytes=max((result.peak_rss_bytes for result in logs), default=0),
            exit_code=logs[-1].exit_code if logs else external.exit_code,
        )

    @staticmethod
    def _remaining(deadline: float | None) -> float | None:
        if deadline is None:
            return None
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError
        return remaining

    @staticmethod
    def _failure(
        kind: FailureKind,
        signature: str,
        artifacts: tuple[str, ...],
        usage: ResourceUsage | None = None,
    ) -> EvaluationOutput:
        validity = EvidenceValidity.INVALID_MECHANICS if kind in {
            FailureKind.PATCH_REJECTED,
            FailureKind.PATH_VIOLATION,
            FailureKind.BUILD_FAILED,
            FailureKind.TEST_FAILED,
        } else EvidenceValidity.NOT_EVALUABLE
        return EvaluationOutput.from_metrics(
            {},
            validity=validity,
            failure_signature=signature,
            failure_kind=kind,
            artifacts=artifacts,
            reported_usage=usage,
        )


class ExecutableCandidateEvaluator:
    evaluator_id = "executable_candidate_v1"
    version = "1.0.0"
    enforces_hard_timeout = True

    def __init__(self, artifacts: ArtifactStore, *, contract: ProblemContract | None = None) -> None:
        self.artifacts = artifacts
        self.runner = IsolatedRepositoryRunner(artifacts, contract=contract)

    def digest_material(self) -> dict[str, str]:
        return {
            "runner_source": inspect.getsource(IsolatedRepositoryRunner),
            "process_source": inspect.getsource(_run_command),
            "bundle_source": inspect.getsource(ExecutableCandidateBundle),
        }

    def evaluate(
        self,
        candidate: CandidateSpec,
        experiment: ExperimentSpec,
        data: bytes | None,
    ) -> EvaluationOutput:
        try:
            bundle = ExecutableCandidateBundle.from_artifact(self.artifacts, candidate.artifact_digest)
        except (FileNotFoundError, ValueError, KeyError, json.JSONDecodeError):
            return EvaluationOutput.from_metrics(
                {},
                validity=EvidenceValidity.INVALID_MECHANICS,
                failure_signature="EXECUTABLE_CANDIDATE_BUNDLE_INVALID",
                failure_kind=FailureKind.CANDIDATE_ARTIFACT,
            )
        return self.runner.run(
            bundle,
            candidate_artifact_digest=candidate.artifact_digest,
            experiment=experiment,
            data=data,
        )


def _run_command(
    step: str,
    command: CommandSpec,
    cwd: Path,
    environment: dict[str, str],
    timeout: float | None,
) -> CommandResult:
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
    before_cpu = _children_cpu_seconds()
    started = time.perf_counter()
    process = subprocess.Popen(
        command.argv,
        cwd=cwd,
        env=environment,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=flags,
        start_new_session=sys.platform != "win32",
    )
    stop = threading.Event()
    peak = [0]

    def sample() -> None:
        while not stop.wait(0.01):
            peak[0] = max(peak[0], process_rss_bytes(process.pid))

    sampler = threading.Thread(target=sample, daemon=True)
    sampler.start()
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_process_tree(process)
        stdout, stderr = process.communicate()
    finally:
        peak[0] = max(peak[0], process_rss_bytes(process.pid))
        stop.set()
        sampler.join(timeout=1)
    return CommandResult(
        step=step,
        argv=command.argv,
        exit_code=process.returncode,
        stdout=stdout,
        stderr=stderr,
        wall_seconds=time.perf_counter() - started,
        cpu_seconds=_process_cpu_seconds(process, before_cpu),
        peak_rss_bytes=peak[0],
        timed_out=timed_out,
        uses_gpu=command.uses_gpu,
        uses_device=command.uses_device,
    )


def _kill_process_tree(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    if sys.platform == "win32":
        subprocess.run(
            ("taskkill", "/PID", str(process.pid), "/T", "/F"),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=False,
        )
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def _children_cpu_seconds() -> float:
    if sys.platform == "win32":
        return time.process_time()
    try:
        import resource

        usage = resource.getrusage(resource.RUSAGE_CHILDREN)
        return usage.ru_utime + usage.ru_stime
    except (ImportError, OSError, ValueError):
        return 0.0


def _process_cpu_seconds(process: subprocess.Popen[str], before_children_cpu: float) -> float:
    if sys.platform != "win32":
        return max(0.0, _children_cpu_seconds() - before_children_cpu)
    try:
        import ctypes
        from ctypes import wintypes

        creation = wintypes.FILETIME()
        exit_time = wintypes.FILETIME()
        kernel = wintypes.FILETIME()
        user = wintypes.FILETIME()
        if not ctypes.windll.kernel32.GetProcessTimes(
            int(process._handle),
            ctypes.byref(creation),
            ctypes.byref(exit_time),
            ctypes.byref(kernel),
            ctypes.byref(user),
        ):
            return 0.0

        def ticks(value: wintypes.FILETIME) -> int:
            return (int(value.dwHighDateTime) << 32) | int(value.dwLowDateTime)

        return (ticks(kernel) + ticks(user)) / 10_000_000.0
    except (AttributeError, OSError, TypeError, ValueError):
        return 0.0


def _classify_process_failure(result: CommandResult, default: FailureKind) -> FailureKind:
    combined = (result.stdout + "\n" + result.stderr).lower()
    if result.exit_code in {-9, 137, -1073741801} or "out of memory" in combined or "memoryerror" in combined:
        return FailureKind.OOM
    if result.exit_code is None:
        return FailureKind.WORKER_CRASH
    if result.exit_code < 0:
        return FailureKind.WORKER_CRASH
    return default


def _parse_evaluation_output(stdout: str) -> dict[str, Any]:
    lines = [line for line in stdout.splitlines() if line.strip()]
    if not lines:
        raise ValueError("evaluation command emitted no result")
    value = json.loads(lines[-1])
    if not isinstance(value, dict) or not isinstance(value.get("metrics"), dict):
        raise ValueError("evaluation result requires a metrics object")
    return value
