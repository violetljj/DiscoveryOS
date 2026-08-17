from __future__ import annotations

import json
import math
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

from discoveryos.runtime.artifacts import ArtifactStore
from discoveryos.util import digest_bytes, digest_json, jsonable


PROTOCOL_ID = "CAUSAL_MECHANISM_INTELLIGENCE_R0"
MANIFEST_RECORD = "cmi-r0-synthetic-manifest.json"
REPORT_RECORD = "cmi-r0-synthetic-report.json"


class DiagnosisPhase(str, Enum):
    OBSERVED_FAILURE = "OBSERVED_FAILURE"
    HYPOTHESES_FROZEN = "HYPOTHESES_FROZEN"
    PROBES_FROZEN = "PROBES_FROZEN"
    DIAGNOSED = "DIAGNOSED"
    MECHANISM_BRIEF_ALLOWED = "MECHANISM_BRIEF_ALLOWED"
    NO_ACTIONABLE_BOTTLENECK = "NO_ACTIONABLE_BOTTLENECK"


class HypothesisVerdict(str, Enum):
    SUPPORTED = "SUPPORTED"
    REFUTED = "REFUTED"
    UNRESOLVED = "UNRESOLVED"
    NOT_EVALUABLE = "NOT_EVALUABLE"


class ProbeValidity(str, Enum):
    VALID = "VALID"
    NOT_EVALUABLE = "NOT_EVALUABLE"


class Comparison(str, Enum):
    LESS_THAN_OR_EQUAL = "LE"
    GREATER_THAN_OR_EQUAL = "GE"


@dataclass(frozen=True, slots=True)
class PhenotypeMetrics:
    headroom: float
    validity_rate: float
    replacement_rate: float
    behavioral_diversity: float
    structural_basin_diversity: float
    parent_entropy: float
    lineage_improvement: float
    budget_concentration: float
    evaluator_sensitivity: float

    def __post_init__(self) -> None:
        values = tuple(getattr(self, name) for name in self.__dataclass_fields__)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("phenotype metrics must be finite")
        if self.headroom < 0:
            raise ValueError("phenotype headroom cannot be negative")
        unit_interval = (
            self.validity_rate,
            self.replacement_rate,
            self.behavioral_diversity,
            self.structural_basin_diversity,
            self.parent_entropy,
            self.budget_concentration,
            self.evaluator_sensitivity,
        )
        if any(not 0.0 <= value <= 1.0 for value in unit_interval):
            raise ValueError("normalized phenotype metrics must be in [0, 1]")


@dataclass(frozen=True, slots=True)
class FailurePhenotypeReceipt:
    episode_id: str
    source_digest: str
    contract_digest: str
    observed_failure: str
    metrics: PhenotypeMetrics

    def __post_init__(self) -> None:
        if not self.episode_id or not self.observed_failure:
            raise ValueError("failure phenotype identity and observation are required")
        if any(len(value) != 64 for value in (self.source_digest, self.contract_digest)):
            raise ValueError("failure phenotype bindings must be SHA-256 digests")

    @property
    def receipt_id(self) -> str:
        return f"phenotype_{digest_json(self)[:20]}"


@dataclass(frozen=True, slots=True)
class BottleneckHypothesis:
    hypothesis_id: str
    statement: str
    causal_target: str
    preconditions: tuple[str, ...]
    expected_observations: tuple[str, ...]
    falsifiers: tuple[str, ...]
    required_probe_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.hypothesis_id or not self.statement or not self.causal_target:
            raise ValueError("hypothesis identity, statement, and causal target are required")
        if not self.preconditions or not self.expected_observations or not self.falsifiers:
            raise ValueError("hypotheses must be falsifiable and state their applicability")
        if not self.required_probe_ids or len(set(self.required_probe_ids)) != len(self.required_probe_ids):
            raise ValueError("hypotheses require unique diagnostic probes")

    @property
    def spec_digest(self) -> str:
        return digest_json(self)


@dataclass(frozen=True, slots=True)
class ThresholdRule:
    comparison: Comparison
    threshold: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.threshold):
            raise ValueError("probe thresholds must be finite")

    def matches(self, value: float) -> bool:
        if self.comparison is Comparison.LESS_THAN_OR_EQUAL:
            return value <= self.threshold
        return value >= self.threshold


@dataclass(frozen=True, slots=True)
class DiagnosticProbeSpec:
    probe_id: str
    target_hypothesis_id: str
    measurement: str
    support_when: ThresholdRule
    refute_when: ThresholdRule
    max_model_calls: int = 0
    max_evaluator_calls: int = 0
    fresh_task_budget: int = 0

    def __post_init__(self) -> None:
        if not self.probe_id or not self.target_hypothesis_id or not self.measurement:
            raise ValueError("probe identity, target, and measurement are required")
        if min(self.max_model_calls, self.max_evaluator_calls, self.fresh_task_budget) < 0:
            raise ValueError("probe resource limits cannot be negative")
        same_direction = self.support_when.comparison is self.refute_when.comparison
        inward_overlap = (
            self.support_when.comparison is Comparison.LESS_THAN_OR_EQUAL
            and self.refute_when.comparison is Comparison.GREATER_THAN_OR_EQUAL
            and self.support_when.threshold >= self.refute_when.threshold
        ) or (
            self.support_when.comparison is Comparison.GREATER_THAN_OR_EQUAL
            and self.refute_when.comparison is Comparison.LESS_THAN_OR_EQUAL
            and self.support_when.threshold <= self.refute_when.threshold
        )
        if same_direction or inward_overlap:
            raise ValueError("probe support and refutation regions must not overlap")

    @property
    def spec_digest(self) -> str:
        return digest_json(self)


@dataclass(frozen=True, slots=True)
class DiagnosticProbeResult:
    probe_id: str
    probe_spec_digest: str
    phenotype_receipt_id: str
    observed_value: float | None
    validity: ProbeValidity
    reason: str
    model_calls: int = 0
    evaluator_calls: int = 0
    fresh_task_budget_consumed: int = 0

    def __post_init__(self) -> None:
        if not self.probe_id or not self.probe_spec_digest or not self.phenotype_receipt_id:
            raise ValueError("probe results must bind probe and phenotype identities")
        if len(self.probe_spec_digest) != 64:
            raise ValueError("probe result must bind a SHA-256 spec digest")
        if self.validity is ProbeValidity.VALID:
            if self.observed_value is None or not math.isfinite(self.observed_value):
                raise ValueError("valid probe results require a finite observation")
        if min(self.model_calls, self.evaluator_calls, self.fresh_task_budget_consumed) < 0:
            raise ValueError("probe usage cannot be negative")

    @property
    def receipt_id(self) -> str:
        return f"probe_{digest_json(self)[:20]}"


@dataclass(frozen=True, slots=True)
class HypothesisAssessment:
    hypothesis_id: str
    verdict: HypothesisVerdict
    probe_receipt_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DiagnosisReport:
    phenotype_receipt_id: str
    assessments: tuple[HypothesisAssessment, ...]
    terminal_phase: DiagnosisPhase
    mechanism_brief_hypothesis_id: str | None
    scientific_verdict_authority: bool = False
    fresh_search_value_budget_authorized: bool = False


class MechanismDiagnosisSession:
    """Fail-closed research-plane state machine; it never owns scientific verdicts."""

    def __init__(self, phenotype: FailurePhenotypeReceipt) -> None:
        self.phenotype = phenotype
        self.phase = DiagnosisPhase.OBSERVED_FAILURE
        self.hypotheses: tuple[BottleneckHypothesis, ...] = ()
        self.probes: tuple[DiagnosticProbeSpec, ...] = ()
        self.assessments: tuple[HypothesisAssessment, ...] = ()

    def freeze_hypotheses(self, hypotheses: Iterable[BottleneckHypothesis]) -> None:
        self._require_phase(DiagnosisPhase.OBSERVED_FAILURE)
        frozen = tuple(hypotheses)
        if len(frozen) < 2:
            raise ValueError("diagnosis requires at least two competing hypotheses")
        if len({item.hypothesis_id for item in frozen}) != len(frozen):
            raise ValueError("hypothesis ids must be unique")
        self.hypotheses = frozen
        self.phase = DiagnosisPhase.HYPOTHESES_FROZEN

    def freeze_probes(self, probes: Iterable[DiagnosticProbeSpec]) -> None:
        self._require_phase(DiagnosisPhase.HYPOTHESES_FROZEN)
        frozen = tuple(probes)
        if len({item.probe_id for item in frozen}) != len(frozen):
            raise ValueError("probe ids must be unique")
        by_id = {item.probe_id: item for item in frozen}
        hypothesis_ids = {item.hypothesis_id for item in self.hypotheses}
        if any(item.target_hypothesis_id not in hypothesis_ids for item in frozen):
            raise ValueError("every probe must target a frozen hypothesis")
        required = {probe_id for item in self.hypotheses for probe_id in item.required_probe_ids}
        if set(by_id) != required:
            raise ValueError("probe set must exactly cover frozen hypothesis requirements")
        for hypothesis in self.hypotheses:
            if any(by_id[probe_id].target_hypothesis_id != hypothesis.hypothesis_id for probe_id in hypothesis.required_probe_ids):
                raise ValueError("required probes must target their declaring hypothesis")
        self.probes = frozen
        self.phase = DiagnosisPhase.PROBES_FROZEN

    def diagnose(self, results: Iterable[DiagnosticProbeResult]) -> tuple[HypothesisAssessment, ...]:
        self._require_phase(DiagnosisPhase.PROBES_FROZEN)
        frozen_results = tuple(results)
        by_id = {item.probe_id: item for item in frozen_results}
        if len(by_id) != len(frozen_results) or set(by_id) != {item.probe_id for item in self.probes}:
            raise ValueError("probe results must exactly cover the frozen probe set")
        specs = {item.probe_id: item for item in self.probes}
        for probe_id, result in by_id.items():
            spec = specs[probe_id]
            if result.probe_spec_digest != spec.spec_digest:
                raise ValueError("probe result does not bind the frozen probe specification")
            if result.phenotype_receipt_id != self.phenotype.receipt_id:
                raise ValueError("probe result does not bind the frozen phenotype")
            if result.model_calls > spec.max_model_calls or result.evaluator_calls > spec.max_evaluator_calls:
                raise ValueError("probe result exceeds the frozen call budget")
            if result.fresh_task_budget_consumed > spec.fresh_task_budget:
                raise ValueError("probe result exceeds the frozen fresh-task budget")

        assessments = []
        for hypothesis in self.hypotheses:
            selected = tuple(by_id[probe_id] for probe_id in hypothesis.required_probe_ids)
            verdicts = tuple(self._classify(specs[result.probe_id], result) for result in selected)
            if HypothesisVerdict.NOT_EVALUABLE in verdicts:
                verdict = HypothesisVerdict.NOT_EVALUABLE
            elif HypothesisVerdict.REFUTED in verdicts:
                verdict = HypothesisVerdict.REFUTED
            elif all(item is HypothesisVerdict.SUPPORTED for item in verdicts):
                verdict = HypothesisVerdict.SUPPORTED
            else:
                verdict = HypothesisVerdict.UNRESOLVED
            assessments.append(
                HypothesisAssessment(
                    hypothesis_id=hypothesis.hypothesis_id,
                    verdict=verdict,
                    probe_receipt_ids=tuple(item.receipt_id for item in selected),
                )
            )
        self.assessments = tuple(assessments)
        self.phase = DiagnosisPhase.DIAGNOSED
        return self.assessments

    def finalize(self) -> DiagnosisReport:
        self._require_phase(DiagnosisPhase.DIAGNOSED)
        supported = [item for item in self.assessments if item.verdict is HypothesisVerdict.SUPPORTED]
        competing_closed = all(
            item.verdict is HypothesisVerdict.REFUTED
            for item in self.assessments
            if item not in supported
        )
        if len(supported) == 1 and competing_closed:
            self.phase = DiagnosisPhase.MECHANISM_BRIEF_ALLOWED
            selected = supported[0].hypothesis_id
        else:
            self.phase = DiagnosisPhase.NO_ACTIONABLE_BOTTLENECK
            selected = None
        return DiagnosisReport(
            phenotype_receipt_id=self.phenotype.receipt_id,
            assessments=self.assessments,
            terminal_phase=self.phase,
            mechanism_brief_hypothesis_id=selected,
        )

    @staticmethod
    def _classify(spec: DiagnosticProbeSpec, result: DiagnosticProbeResult) -> HypothesisVerdict:
        if result.validity is ProbeValidity.NOT_EVALUABLE:
            return HypothesisVerdict.NOT_EVALUABLE
        assert result.observed_value is not None
        supports = spec.support_when.matches(result.observed_value)
        refutes = spec.refute_when.matches(result.observed_value)
        if supports and refutes:
            raise ValueError("probe observation matches conflicting frozen rules")
        if supports:
            return HypothesisVerdict.SUPPORTED
        if refutes:
            return HypothesisVerdict.REFUTED
        return HypothesisVerdict.UNRESOLVED

    def _require_phase(self, expected: DiagnosisPhase) -> None:
        if self.phase is not expected:
            raise RuntimeError(f"diagnosis phase must be {expected.value}, found {self.phase.value}")


def seal_cmi_r0_protocol(workspace: Path) -> dict[str, Any]:
    phenotype, hypotheses, probes, scenarios = synthetic_fixture()
    payload = {
        "protocol_id": PROTOCOL_ID,
        "status": "SEALED_PRE_EXECUTION",
        "scope": "SYNTHETIC_DIAGNOSTIC_MECHANICS_ONLY",
        "claim_ceiling": "NO_REAL_BOTTLENECK_OPERATOR_OR_SEARCH_VALUE_CLAIM",
        "phenotype": jsonable(phenotype),
        "hypotheses": [jsonable(item) for item in hypotheses],
        "probes": [jsonable(item) for item in probes],
        "synthetic_scenarios": scenarios,
        "phase_order": [item.value for item in DiagnosisPhase],
        "model_calls_before_seal": 0,
        "evaluator_calls_before_seal": 0,
        "fresh_task_budget_consumed": 0,
        "fresh_search_value_budget_authorized": False,
        "scientific_verdict_authority": "ProblemContract + GateEngine only",
        "protocol_implementation_sha256": digest_bytes(Path(__file__).read_bytes()),
    }
    manifest = {**payload, "manifest_digest": digest_json(payload)}
    path = ArtifactStore(workspace.resolve() / "protocol-artifacts").write_record(MANIFEST_RECORD, manifest)
    return {
        "status": manifest["status"],
        "manifest_digest": manifest["manifest_digest"],
        "manifest_path": str(path),
        "model_calls": 0,
        "evaluator_calls": 0,
        "fresh_task_budget_consumed": 0,
    }


def run_cmi_r0_synthetic(workspace: Path, *, manifest_digest: str) -> dict[str, Any]:
    workspace = workspace.resolve()
    manifest_path = workspace / "protocol-artifacts" / "records" / MANIFEST_RECORD
    manifest = _load_manifest(manifest_path, manifest_digest)
    phenotype = _phenotype_from_json(manifest["phenotype"])
    hypotheses = tuple(BottleneckHypothesis(**item) for item in manifest["hypotheses"])
    probes = tuple(_probe_from_json(item) for item in manifest["probes"])
    result_store = ArtifactStore(workspace / "result-artifacts")
    scenario_reports: dict[str, Any] = {}
    for scenario_name, values in manifest["synthetic_scenarios"].items():
        session = MechanismDiagnosisSession(phenotype)
        session.freeze_hypotheses(hypotheses)
        session.freeze_probes(probes)
        results = tuple(
            DiagnosticProbeResult(
                probe_id=probe.probe_id,
                probe_spec_digest=probe.spec_digest,
                phenotype_receipt_id=phenotype.receipt_id,
                observed_value=float(values[probe.probe_id]),
                validity=ProbeValidity.VALID,
                reason="frozen synthetic observation",
            )
            for probe in probes
        )
        session.diagnose(results)
        diagnosis = session.finalize()
        scenario_payload = {
            "scenario": scenario_name,
            "probe_results": [jsonable(item) for item in results],
            "diagnosis": jsonable(diagnosis),
        }
        path = result_store.write_record(f"scenarios/{scenario_name}.json", scenario_payload)
        scenario_reports[scenario_name] = {
            **scenario_payload,
            "receipt_path": str(path),
            "receipt_sha256": digest_bytes(path.read_bytes()),
        }

    null_terminal = scenario_reports["null_control"]["diagnosis"]["terminal_phase"]
    positive = scenario_reports["positive_control"]["diagnosis"]
    sensitivity_passed = (
        null_terminal == DiagnosisPhase.NO_ACTIONABLE_BOTTLENECK.value
        and positive["terminal_phase"] == DiagnosisPhase.MECHANISM_BRIEF_ALLOWED.value
        and positive["mechanism_brief_hypothesis_id"] == "H5_STRUCTURAL_BASIN_LOCK"
    )
    report = {
        "protocol_id": PROTOCOL_ID,
        "manifest_digest": manifest_digest,
        "status": (
            "CMI_R0_SYNTHETIC_DIAGNOSTIC_SENSITIVITY_PASSED"
            if sensitivity_passed
            else "CMI_R0_SYNTHETIC_DIAGNOSTIC_SENSITIVITY_FAILED"
        ),
        "claim_ceiling": manifest["claim_ceiling"],
        "synthetic_sensitivity_passed": sensitivity_passed,
        "scenarios": scenario_reports,
        "real_bottleneck_established": False,
        "real_mechanism_brief_authorized": False,
        "fresh_search_value_budget_authorized": False,
        "model_calls": 0,
        "evaluator_calls": 0,
        "fresh_task_budget_consumed": 0,
        "source_bindings": [
            {"role": "manifest", "path": str(manifest_path), "sha256": digest_bytes(manifest_path.read_bytes())},
            {"role": "implementation", "path": str(Path(__file__).resolve()), "sha256": digest_bytes(Path(__file__).read_bytes())},
        ],
    }
    path = result_store.write_record(REPORT_RECORD, report)
    return {**report, "report_path": str(path), "report_sha256": digest_bytes(path.read_bytes())}


def synthetic_fixture() -> tuple[
    FailurePhenotypeReceipt,
    tuple[BottleneckHypothesis, ...],
    tuple[DiagnosticProbeSpec, ...],
    dict[str, dict[str, float]],
]:
    phenotype = FailurePhenotypeReceipt(
        episode_id="synthetic-valid-stagnation",
        source_digest=digest_json({"fixture": "synthetic-source-v1"}),
        contract_digest=digest_json({"fixture": "synthetic-contract-v1"}),
        observed_failure="valid candidates and stable execution without utility improvement",
        metrics=PhenotypeMetrics(
            headroom=0.25,
            validity_rate=1.0,
            replacement_rate=0.0,
            behavioral_diversity=0.05,
            structural_basin_diversity=0.03,
            parent_entropy=0.7,
            lineage_improvement=0.0,
            budget_concentration=0.5,
            evaluator_sensitivity=0.95,
        ),
    )
    hypotheses = (
        BottleneckHypothesis(
            hypothesis_id="H3_EVALUATOR_INSENSITIVITY",
            statement="the evaluator cannot distinguish value-bearing candidate changes",
            causal_target="evaluator sensitivity",
            preconditions=("known-order controls can be constructed",),
            expected_observations=("known ordering is not recovered",),
            falsifiers=("known ordering is recovered with high accuracy",),
            required_probe_ids=("P3_RANKED_CONTROL_RECOVERY",),
        ),
        BottleneckHypothesis(
            hypothesis_id="H4_IMPLEMENTATION_BOTTLENECK",
            statement="implementation failures prevent proposals from reaching evaluation",
            causal_target="evaluation eligibility",
            preconditions=("a perfect-implementation control is available",),
            expected_observations=("control materially increases eligibility",),
            falsifiers=("control leaves eligibility unchanged",),
            required_probe_ids=("P4_PERFECT_IMPLEMENTATION_DELTA",),
        ),
        BottleneckHypothesis(
            hypothesis_id="H5_STRUCTURAL_BASIN_LOCK",
            statement="valid generations remain in one functional structural basin",
            causal_target="functional basin diversity",
            preconditions=("functional basin probe is frozen",),
            expected_observations=("independent candidates have very low basin diversity",),
            falsifiers=("independent candidates span multiple functional basins",),
            required_probe_ids=("P5_FUNCTIONAL_BASIN_DIVERSITY",),
        ),
    )
    probes = (
        DiagnosticProbeSpec(
            probe_id="P3_RANKED_CONTROL_RECOVERY",
            target_hypothesis_id="H3_EVALUATOR_INSENSITIVITY",
            measurement="fraction of frozen known-order pairs recovered",
            support_when=ThresholdRule(Comparison.LESS_THAN_OR_EQUAL, 0.2),
            refute_when=ThresholdRule(Comparison.GREATER_THAN_OR_EQUAL, 0.8),
        ),
        DiagnosticProbeSpec(
            probe_id="P4_PERFECT_IMPLEMENTATION_DELTA",
            target_hypothesis_id="H4_IMPLEMENTATION_BOTTLENECK",
            measurement="evaluation eligibility delta under perfect implementation control",
            support_when=ThresholdRule(Comparison.GREATER_THAN_OR_EQUAL, 0.2),
            refute_when=ThresholdRule(Comparison.LESS_THAN_OR_EQUAL, 0.01),
        ),
        DiagnosticProbeSpec(
            probe_id="P5_FUNCTIONAL_BASIN_DIVERSITY",
            target_hypothesis_id="H5_STRUCTURAL_BASIN_LOCK",
            measurement="normalized functional basin diversity",
            support_when=ThresholdRule(Comparison.LESS_THAN_OR_EQUAL, 0.1),
            refute_when=ThresholdRule(Comparison.GREATER_THAN_OR_EQUAL, 0.5),
        ),
    )
    scenarios = {
        "null_control": {
            "P3_RANKED_CONTROL_RECOVERY": 0.5,
            "P4_PERFECT_IMPLEMENTATION_DELTA": 0.1,
            "P5_FUNCTIONAL_BASIN_DIVERSITY": 0.3,
        },
        "positive_control": {
            "P3_RANKED_CONTROL_RECOVERY": 0.9,
            "P4_PERFECT_IMPLEMENTATION_DELTA": 0.0,
            "P5_FUNCTIONAL_BASIN_DIVERSITY": 0.02,
        },
    }
    return phenotype, hypotheses, probes, scenarios


def _load_manifest(path: Path, expected_digest: str) -> dict[str, Any]:
    if not path.is_file():
        raise RuntimeError("sealed CMI-R0 manifest is missing")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    actual = manifest.get("manifest_digest")
    payload = {key: value for key, value in manifest.items() if key != "manifest_digest"}
    if actual != digest_json(payload) or actual != expected_digest:
        raise RuntimeError("sealed CMI-R0 manifest digest mismatch")
    if manifest.get("protocol_id") != PROTOCOL_ID:
        raise RuntimeError("sealed CMI-R0 protocol identity mismatch")
    return manifest


def _phenotype_from_json(value: dict[str, Any]) -> FailurePhenotypeReceipt:
    return FailurePhenotypeReceipt(
        episode_id=value["episode_id"],
        source_digest=value["source_digest"],
        contract_digest=value["contract_digest"],
        observed_failure=value["observed_failure"],
        metrics=PhenotypeMetrics(**value["metrics"]),
    )


def _probe_from_json(value: dict[str, Any]) -> DiagnosticProbeSpec:
    return DiagnosticProbeSpec(
        probe_id=value["probe_id"],
        target_hypothesis_id=value["target_hypothesis_id"],
        measurement=value["measurement"],
        support_when=ThresholdRule(
            comparison=Comparison(value["support_when"]["comparison"]),
            threshold=value["support_when"]["threshold"],
        ),
        refute_when=ThresholdRule(
            comparison=Comparison(value["refute_when"]["comparison"]),
            threshold=value["refute_when"]["threshold"],
        ),
        max_model_calls=value["max_model_calls"],
        max_evaluator_calls=value["max_evaluator_calls"],
        fresh_task_budget=value["fresh_task_budget"],
    )
