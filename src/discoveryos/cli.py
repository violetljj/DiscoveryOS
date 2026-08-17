from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path

from discoveryos.benchmarks import (
    audit_si2_search_causality,
    audit_si2_secondary_usage,
    audit_local_patch_invalids,
    replay_local_patch_mechanics,
    run_search_value_mvp0,
    run_asha_admission,
    run_local_patch_admission,
    run_local_patch_readmission,
    seal_local_patch_readmission,
    seal_search_value_mvp0,
    STRUCTURAL_PATCH_SCHEMA,
    run_strategy_integration_si1_pilot,
    run_si2_confirmation,
    run_si2_discovery,
    seal_si2_protocol,
    run_cmi_search_value_r1,
    seal_cmi_search_value_r1,
    run_synthetic_cib,
    seal_synthetic_cib_protocol,
    run_parent_dev_cib,
    seal_parent_dev_cib_protocol,
    calibrate_parent_real_cib,
    run_parent_real_cib,
    seal_parent_real_cib_protocol,
    parent_cib_r1_settlement,
    run_synthetic_gcf,
    seal_synthetic_gcf_protocol,
    calibrate_mechanism_brief,
    run_mechanism_brief_validation,
    seal_mechanism_brief_protocol,
    calibrate_structured_proposals,
    run_structured_provider_preflight,
    validate_structured_proposals,
    run_structured_implementation_calibration,
    seal_structured_mediation_protocol,
    run_emc_implementation_calibration,
    run_emc_implementation_validation,
    run_emc_instrumentation_sensitivity,
    run_emc_provider_preflight,
    seal_emc_protocol,
    run_emc_resource_calibration,
    seal_emc_resource_calibration,
    run_emc_r3_calibration,
    run_emc_r3_instrumentation,
    run_emc_r3_validation,
    seal_emc_r3_protocol,
    calibrate_operator_causal_value,
    run_operator_causal_value_validation,
    seal_operator_causal_value_protocol,
    run_cmi_probe_calibration,
    seal_cmi_probe_calibration,
    run_cmi_real_controls,
    run_cmi_real_diagnosis,
    seal_cmi_real_diagnosis,
    admit_cmi_escape_brief,
    seal_cmi_escape_brief,
    run_cmi_escape_operator,
    seal_cmi_escape_operator,
    run_cmi_causal_value,
    seal_cmi_causal_value,
    run_cmi_replication_admission,
    seal_cmi_replication_admission,
    run_cmi_fresh_causal_validation,
    seal_cmi_fresh_causal_validation,
    load_benchmark_bank,
    materialize_bank_instance,
    validate_benchmark_bank,
)
from discoveryos.domains.clearance_demo import demo_status, replay_demo, run_demo_certification, run_demo_discovery
from discoveryos.mechanism_intelligence import run_cmi_r0_synthetic, seal_cmi_r0_protocol
from discoveryos.providers import CodexExecProvider


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="discoveryos", description="Evidence-first algorithm discovery operating system")
    subparsers = parser.add_subparsers(dest="command", required=True)
    discovery = subparsers.add_parser("demo-discovery", help="run the deterministic G0/G1/G2 discovery example")
    discovery.add_argument("--workspace", type=Path, default=Path("runs/clearance-demo"))
    discovery.add_argument("--candidates", type=int, default=12)
    discovery.add_argument("--seed", type=int, default=7)
    certification = subparsers.add_parser("demo-certify", help="certify the already-frozen demo winner on final blind")
    certification.add_argument("--workspace", type=Path, default=Path("runs/clearance-demo"))
    certification.add_argument("--seed", type=int, default=7001)
    status = subparsers.add_parser("status", help="inspect a demo workspace without mutating it")
    status.add_argument("--workspace", type=Path, default=Path("runs/clearance-demo"))
    replay = subparsers.add_parser("demo-replay", help="re-execute and compare every frozen demo evaluation receipt")
    replay.add_argument("--workspace", type=Path, default=Path("runs/clearance-demo"))
    asha = subparsers.add_parser("asha-admission", help="run matched-budget deterministic Random vs ASHA admission")
    asha.add_argument("--workspace", type=Path, default=Path("runs/asha-admission"))
    asha.add_argument("--seeds", type=int, default=12)
    local_patch = subparsers.add_parser(
        "local-patch-admission",
        help="run matched-token Baseline vs One-shot LLM vs Iterative Local Patch real-code admission",
    )
    local_patch.add_argument("--workspace", type=Path, default=Path("runs/local-patch-admission"))
    local_patch.add_argument("--model", required=True, help="frozen Codex model identifier")
    local_patch.add_argument("--codex-command", default="codex", help="quoted command used to launch Codex CLI")
    local_patch.add_argument("--reasoning-effort", default="medium")
    local_patch.add_argument("--token-ceiling", type=int, default=90000)
    local_patch.add_argument("--iterations", type=int, default=3)
    invalid_autopsy = subparsers.add_parser(
        "local-patch-invalid-autopsy",
        help="audit frozen local-patch invalids without model calls or scientific re-evaluation",
    )
    invalid_autopsy.add_argument("--workspace", type=Path, default=Path("runs/local-patch-admission-r1"))
    mechanics_replay = subparsers.add_parser(
        "local-patch-brd-mechanics-replay",
        help="replay patch/build/public-test mechanics on the consumed corpus without model or scientific evaluation",
    )
    mechanics_replay.add_argument("--workspace", type=Path, default=Path("runs/local-patch-admission-r1"))
    br_a_seal = subparsers.add_parser(
        "local-patch-br-a-seal",
        help="freeze the eight-task BR-A manifest without making model calls",
    )
    br_a_seal.add_argument("--workspace", type=Path, default=Path("runs/local-patch-br-a-readmission-r1"))
    br_a_seal.add_argument("--model", required=True, help="frozen Codex model identifier")
    br_a_seal.add_argument("--codex-command", default="codex", help="quoted command used to launch Codex CLI")
    br_a_seal.add_argument("--reasoning-effort", default="medium")
    br_a_seal.add_argument("--token-ceiling", type=int, default=90000)
    br_a_seal.add_argument("--iterations", type=int, default=3)
    br_a_run = subparsers.add_parser(
        "local-patch-br-a-readmission",
        help="execute the already-sealed eight-task BR-A fresh readmission",
    )
    br_a_run.add_argument("--workspace", type=Path, default=Path("runs/local-patch-br-a-readmission-r1"))
    br_a_run.add_argument("--manifest-digest", required=True)
    br_a_run.add_argument("--model", required=True, help="must match the sealed Codex model identifier")
    br_a_run.add_argument("--codex-command", default="codex", help="quoted command used to launch Codex CLI")
    br_a_run.add_argument("--reasoning-effort", default="medium")
    mvp0_seal = subparsers.add_parser(
        "search-value-mvp0-seal",
        help="freeze the eight-task Vanilla vs DiscoveryOS MVP-0 protocol before model calls",
    )
    mvp0_seal.add_argument("--workspace", type=Path, default=Path("runs/search-value-mvp0-r1"))
    mvp0_seal.add_argument("--model", required=True)
    mvp0_seal.add_argument("--codex-command", default="codex")
    mvp0_seal.add_argument("--reasoning-effort", default="medium")
    mvp0_seal.add_argument("--token-ceiling", type=int, default=60000)
    mvp0_seal.add_argument("--wall-ceiling", type=float, default=1200.0)
    mvp0_seal.add_argument("--cpu-ceiling", type=float, default=300.0)
    mvp0_run = subparsers.add_parser(
        "search-value-mvp0-run",
        help="execute the already sealed Vanilla vs DiscoveryOS MVP-0",
    )
    mvp0_run.add_argument("--workspace", type=Path, default=Path("runs/search-value-mvp0-r1"))
    mvp0_run.add_argument("--manifest-digest", required=True)
    mvp0_run.add_argument("--model", required=True)
    mvp0_run.add_argument("--codex-command", default="codex")
    mvp0_run.add_argument("--reasoning-effort", default="medium")
    si1 = subparsers.add_parser(
        "strategy-integration-si1",
        help="run the four-arm consumed-task Shinka parent/novelty development pilot",
    )
    si1.add_argument("--workspace", type=Path, default=Path("runs/strategy-integration-si1"))
    si1.add_argument("--model", required=True)
    si1.add_argument("--codex-command", default="codex")
    si1.add_argument("--reasoning-effort", required=True)
    si1.add_argument("--max-workers", type=int, default=3)
    si1.add_argument(
        "--repair",
        action="store_true",
        help="run SI-1R parent-effectiveness and novelty-cost repair semantics",
    )
    si2_seal = subparsers.add_parser(
        "si2-seal",
        help="seal the SI-2 fresh four-arm protocol before candidate-model calls",
    )
    si2_seal.add_argument("--workspace", type=Path, default=Path("runs/si2-fresh-search-value-r1"))
    si2_seal.add_argument("--model", required=True)
    si2_seal.add_argument("--codex-command", default="codex")
    si2_seal.add_argument("--reasoning-effort", required=True)
    si2_seal.add_argument("--shinka-checkout", type=Path, default=Path("runs/si2-external-preflight/ShinkaEvolve"))
    si2_seal.add_argument("--shinka-python", type=Path, default=Path("runs/si2-external-preflight/.venv/Scripts/python.exe"))
    si2_seal.add_argument(
        "--headless-cli",
        type=Path,
        default=Path("runs/si2-external-preflight/headless/node_modules/@roberttlange/headless/dist/cli.js"),
    )
    si2_seal.add_argument("--node-executable", type=Path, default=Path("E:/codex-tools/tools/nodejs/node.exe"))
    si2_audit = subparsers.add_parser(
        "si2-audit-usage",
        help="append a bound correction for SI-2 secondary usage totals without changing scientific results",
    )
    si2_audit.add_argument("--workspace", type=Path, default=Path("runs/si2-fresh-search-value-r1"))
    si2_audit.add_argument("--manifest-digest", required=True)
    si2_causality = subparsers.add_parser(
        "si2-causality-autopsy",
        help="audit consumed SI-2 search divergence and intervention identifiability without model calls",
    )
    si2_causality.add_argument("--workspace", type=Path, default=Path("runs/si2-fresh-search-value-r1"))
    si2_causality.add_argument("--manifest-digest", required=True)
    si2_causality.add_argument(
        "--output-workspace", type=Path, default=Path("runs/si2-search-causality-autopsy-r3")
    )
    cib_seal = subparsers.add_parser(
        "cib-seal-synthetic",
        help="seal the no-model Causal Intervention Bench synthetic sensitivity fixture",
    )
    cib_seal.add_argument("--workspace", type=Path, default=Path("runs/cib-synthetic-r1"))
    cib_run = subparsers.add_parser(
        "cib-run-synthetic",
        help="execute an already-sealed CIB synthetic sensitivity fixture",
    )
    cib_run.add_argument("--workspace", type=Path, default=Path("runs/cib-synthetic-r1"))
    cib_run.add_argument("--manifest-digest", required=True)
    cmi_seal = subparsers.add_parser(
        "cmi-r0-seal",
        help="seal the zero-model Causal Mechanism Intelligence diagnostic fixture",
    )
    cmi_seal.add_argument("--workspace", type=Path, default=Path("runs/cmi-r0-synthetic"))
    cmi_run = subparsers.add_parser(
        "cmi-r0-run-synthetic",
        help="run the sealed CMI-R0 null and positive diagnostic controls",
    )
    cmi_run.add_argument("--workspace", type=Path, default=Path("runs/cmi-r0-synthetic"))
    cmi_run.add_argument("--manifest-digest", required=True)
    cmi_r1_seal = subparsers.add_parser(
        "cmi-r1-seal-probes",
        help="seal two fresh dev episodes for zero-model real probe calibration",
    )
    cmi_r1_seal.add_argument("--workspace", type=Path, default=Path("runs/cmi-r1-real-probe-calibration"))
    cmi_r1_run = subparsers.add_parser(
        "cmi-r1-run-probes",
        help="run the sealed evaluator, implementation, and functional probe controls",
    )
    cmi_r1_run.add_argument("--workspace", type=Path, default=Path("runs/cmi-r1-real-probe-calibration"))
    cmi_r1_run.add_argument("--manifest-digest", required=True)
    for name, help_text in (
        ("cmi-r2-seal", "seal a six-call bounded real bottleneck diagnosis"),
        ("cmi-r2-controls", "run zero-model controls before CMI-R2 provider calls"),
        ("cmi-r2-run", "run the sealed six-call CMI-R2 diagnosis"),
    ):
        command_parser = subparsers.add_parser(name, help=help_text)
        command_parser.add_argument("--workspace", type=Path, default=Path("runs/cmi-r2-bounded-real-diagnosis"))
        command_parser.add_argument("--model", required=True)
        command_parser.add_argument("--codex-command", default="codex")
        command_parser.add_argument("--reasoning-effort", required=True)
        if name == "cmi-r2-seal":
            command_parser.add_argument("--cmi-r1-workspace", type=Path, default=Path("runs/cmi-r1-real-probe-calibration"))
            command_parser.add_argument("--cmi-r1-report-sha256", required=True)
            command_parser.add_argument("--resource-workspace", type=Path, default=Path("runs/emc-resource-calibration-r1"))
            command_parser.add_argument("--resource-record-sha256", required=True)
            command_parser.add_argument("--max-workers", type=int, default=2)
        else:
            command_parser.add_argument("--manifest-digest", required=True)
    cmi_r3_seal = subparsers.add_parser("cmi-r3-seal-brief", help="seal the zero-model functional-basin escape Mechanism Brief")
    cmi_r3_seal.add_argument("--workspace", type=Path, default=Path("runs/cmi-r3-functional-basin-escape-brief"))
    cmi_r3_seal.add_argument("--cmi-r2-workspace", type=Path, default=Path("runs/cmi-r2-bounded-real-diagnosis"))
    cmi_r3_seal.add_argument("--cmi-r2-report-sha256", required=True)
    cmi_r3_seal.add_argument("--cmi-r2-controls-sha256", required=True)
    cmi_r3_admit = subparsers.add_parser("cmi-r3-admit-brief", help="admit the sealed Mechanism Brief using bound zero-model controls")
    cmi_r3_admit.add_argument("--workspace", type=Path, default=Path("runs/cmi-r3-functional-basin-escape-brief"))
    cmi_r3_admit.add_argument("--manifest-digest", required=True)
    cmi_r4_seal = subparsers.add_parser("cmi-r4-seal-operator", help="seal the zero-model functional-basin escape Operator mechanics protocol")
    cmi_r4_seal.add_argument("--workspace", type=Path, default=Path("runs/cmi-r4-functional-basin-escape-operator"))
    cmi_r4_seal.add_argument("--cmi-r3-workspace", type=Path, default=Path("runs/cmi-r3-functional-basin-escape-brief"))
    cmi_r4_seal.add_argument("--cmi-r3-report-sha256", required=True)
    cmi_r4_run = subparsers.add_parser("cmi-r4-run-operator", help="run the sealed zero-model escape Operator mechanics controls")
    cmi_r4_run.add_argument("--workspace", type=Path, default=Path("runs/cmi-r4-functional-basin-escape-operator"))
    cmi_r4_run.add_argument("--manifest-digest", required=True)
    cmi_r5_seal = subparsers.add_parser("cmi-r5-seal-causal-value", help="seal the consumed-state paired CMI causal-value protocol")
    cmi_r5_seal.add_argument("--workspace", type=Path, default=Path("runs/cmi-r5-consumed-dev-causal-value"))
    cmi_r5_seal.add_argument("--cmi-r4-workspace", type=Path, default=Path("runs/cmi-r4-functional-basin-escape-operator"))
    cmi_r5_seal.add_argument("--cmi-r4-report-sha256", required=True)
    cmi_r5_run = subparsers.add_parser("cmi-r5-run-causal-value", help="run the sealed consumed-state paired CMI causal-value bench")
    cmi_r5_run.add_argument("--workspace", type=Path, default=Path("runs/cmi-r5-consumed-dev-causal-value"))
    cmi_r5_run.add_argument("--manifest-digest", required=True)
    cmi_r6_seal = subparsers.add_parser("cmi-r6-seal-replication", help="seal all eligible consumed SI-2 states for CMI replication admission")
    cmi_r6_seal.add_argument("--workspace", type=Path, default=Path("runs/cmi-r6-consumed-distribution-replication"))
    cmi_r6_seal.add_argument("--cmi-r5-workspace", type=Path, default=Path("runs/cmi-r5-consumed-dev-causal-value"))
    cmi_r6_seal.add_argument("--cmi-r5-report-sha256", required=True)
    cmi_r6_seal.add_argument("--si2-workspace", type=Path, default=Path("runs/si2-fresh-search-value-r1"))
    cmi_r6_seal.add_argument("--si2-discovery-report-sha256", required=True)
    cmi_r6_seal.add_argument("--si2-confirmation-report-sha256", required=True)
    cmi_r6_run = subparsers.add_parser("cmi-r6-run-replication", help="run the sealed consumed-distribution CMI replication admission")
    cmi_r6_run.add_argument("--workspace", type=Path, default=Path("runs/cmi-r6-consumed-distribution-replication"))
    cmi_r6_run.add_argument("--manifest-digest", required=True)
    cmi_r7_seal = subparsers.add_parser("cmi-r7-seal-fresh", help="seal the six-state paired fresh CMI causal replication")
    cmi_r7_seal.add_argument("--workspace", type=Path, default=Path("runs/cmi-r7-fresh-causal-replication"))
    cmi_r7_seal.add_argument("--cmi-r6-workspace", type=Path, default=Path("runs/cmi-r6-consumed-distribution-replication"))
    cmi_r7_seal.add_argument("--cmi-r6-report-sha256", required=True)
    cmi_r7_seal.add_argument("--bank-registry", type=Path, default=Path("benchmarks/bank/v1/registry.json"))
    cmi_r7_run = subparsers.add_parser("cmi-r7-run-fresh", help="consume and evaluate the sealed six-state fresh CMI shard once")
    cmi_r7_run.add_argument("--workspace", type=Path, default=Path("runs/cmi-r7-fresh-causal-replication"))
    cmi_r7_run.add_argument("--manifest-digest", required=True)
    cmi_svr1_seal = subparsers.add_parser(
        "cmi-search-value-r1-seal",
        help="seal the paired fresh CMI-enabled versus CMI-disabled search protocol",
    )
    cmi_svr1_seal.add_argument("--workspace", type=Path, default=Path("runs/cmi-search-value-r1-v3"))
    cmi_svr1_seal.add_argument("--cmi-r7-workspace", type=Path, default=Path("runs/cmi-r7-fresh-causal-replication"))
    cmi_svr1_seal.add_argument("--cmi-r7-report-sha256", required=True)
    cmi_svr1_seal.add_argument("--real-provider-preflight", type=Path, required=True)
    cmi_svr1_seal.add_argument("--real-provider-preflight-sha256", required=True)
    cmi_svr1_seal.add_argument("--model", required=True)
    cmi_svr1_seal.add_argument("--codex-command", required=True)
    cmi_svr1_seal.add_argument("--reasoning-effort", required=True)
    cmi_svr1_run = subparsers.add_parser(
        "cmi-search-value-r1-run",
        help="consume the sealed fresh CMI search-value cohort once",
    )
    cmi_svr1_run.add_argument("--workspace", type=Path, default=Path("runs/cmi-search-value-r1-v3"))
    cmi_svr1_run.add_argument("--manifest-digest", required=True)
    cmi_svr1_run.add_argument("--model", required=True)
    cmi_svr1_run.add_argument("--codex-command", required=True)
    cmi_svr1_run.add_argument("--reasoning-effort", required=True)
    bank_validate = subparsers.add_parser(
        "benchmark-bank-validate",
        help="validate the pinned Benchmark Bank v1 registry without consuming any shard",
    )
    bank_validate.add_argument(
        "--registry", type=Path, default=Path("benchmarks/bank/v1/registry.json")
    )
    bank_materialize = subparsers.add_parser(
        "benchmark-bank-materialize-dev",
        help="materialize a registered internal consumed development instance",
    )
    bank_materialize.add_argument(
        "--registry", type=Path, default=Path("benchmarks/bank/v1/registry.json")
    )
    bank_materialize.add_argument("--family-id", required=True)
    bank_materialize.add_argument("--instance-id", required=True)
    bank_materialize.add_argument("--output-dir", type=Path, required=True)
    cib_parent_seal = subparsers.add_parser(
        "cib-seal-parent-dev",
        help="seal consumed development states for a real parent-policy paired trace",
    )
    cib_parent_seal.add_argument("--workspace", type=Path, default=Path("runs/cib-parent-dev-r1"))
    cib_parent_run = subparsers.add_parser(
        "cib-run-parent-dev",
        help="run the actual parent policy on frozen consumed development states",
    )
    cib_parent_run.add_argument("--workspace", type=Path, default=Path("runs/cib-parent-dev-r1"))
    cib_parent_run.add_argument("--manifest-digest", required=True)
    subparsers.add_parser(
        "parent-cib-r1-settlement",
        help="print the machine-readable narrow Parent settlement bound to CIB-R1",
    )
    gcf_seal = subparsers.add_parser(
        "gcf-seal-synthetic",
        help="seal the no-model Generator Conditioning Fidelity calibration fixture",
    )
    gcf_seal.add_argument("--workspace", type=Path, default=Path("runs/gcf-synthetic-r1"))
    gcf_run = subparsers.add_parser(
        "gcf-run-synthetic",
        help="execute an already-sealed GCF synthetic calibration fixture",
    )
    gcf_run.add_argument("--workspace", type=Path, default=Path("runs/gcf-synthetic-r1"))
    gcf_run.add_argument("--manifest-digest", required=True)
    for name, help_text in (
        ("gcf-r1-seal-mechanism-brief", "seal the first real consumed-state Mechanism Brief GCF diagnosis"),
        ("gcf-r1-calibrate-mechanism-brief", "run frozen real Mechanism Brief GCF calibration states"),
        ("gcf-r1-run-mechanism-brief", "run validation after the frozen Mechanism Brief calibration gate"),
    ):
        command_parser = subparsers.add_parser(name, help=help_text)
        command_parser.add_argument("--workspace", type=Path, default=Path("runs/gcf-r1-mechanism-brief"))
        command_parser.add_argument("--model", required=True)
        command_parser.add_argument("--codex-command", default="codex")
        command_parser.add_argument("--reasoning-effort", required=True)
        if name == "gcf-r1-seal-mechanism-brief":
            command_parser.add_argument("--source-workspace", type=Path, default=Path("runs/cib-r1-parent-real"))
            command_parser.add_argument("--source-manifest-digest", required=True)
            command_parser.add_argument("--max-workers", type=int, default=2)
        else:
            command_parser.add_argument("--manifest-digest", required=True)
    for name, help_text in (
        ("emc-resource-r1-seal", "seal the non-scientific EMC resource calibration corpus"),
        ("emc-resource-r1-run", "run the four-call non-scientific EMC resource calibration"),
    ):
        command_parser = subparsers.add_parser(name, help=help_text)
        command_parser.add_argument("--workspace", type=Path, default=Path("runs/emc-resource-calibration-r1"))
        command_parser.add_argument("--model", required=True)
        command_parser.add_argument("--codex-command", default="codex")
        command_parser.add_argument("--reasoning-effort", required=True)
        if name == "emc-resource-r1-run":
            command_parser.add_argument("--manifest-digest", required=True)
    for name, help_text in (
        ("emc-r3-seal", "seal resource-calibrated EMC confirmation on two new development states"),
        ("emc-r3-instrumentation", "run EMC-R3 no-model instrumentation sensitivity"),
        ("emc-r3-calibrate", "run EMC-R3 six-call fresh-state calibration"),
        ("emc-r3-validate", "run EMC-R3 independent six-call validation"),
    ):
        command_parser = subparsers.add_parser(name, help=help_text)
        command_parser.add_argument("--workspace", type=Path, default=Path("runs/emc-r3-resource-calibrated-confirmation"))
        command_parser.add_argument("--model", required=True)
        command_parser.add_argument("--codex-command", default="codex")
        command_parser.add_argument("--reasoning-effort", required=True)
        if name == "emc-r3-seal":
            command_parser.add_argument("--resource-workspace", type=Path, default=Path("runs/emc-resource-calibration-r1"))
            command_parser.add_argument("--resource-record-sha256", required=True)
            command_parser.add_argument("--max-workers", type=int, default=2)
        else:
            command_parser.add_argument("--manifest-digest", required=True)
    for name, help_text in (
        ("emc-ocv-r1-seal", "seal the Direct vs Repair Operator causal-value protocol"),
        ("emc-ocv-r1-calibrate", "calibrate Direct/Direct and Repair/Repair stochastic nulls"),
        ("emc-ocv-r1-validate", "run the frozen Direct vs Repair causal-value validation"),
    ):
        command_parser = subparsers.add_parser(name, help=help_text)
        command_parser.add_argument("--workspace", type=Path, default=Path("runs/emc-operator-causal-value-r1"))
        command_parser.add_argument("--model", required=True)
        command_parser.add_argument("--codex-command", default="codex")
        command_parser.add_argument("--reasoning-effort", required=True)
        if name == "emc-ocv-r1-seal":
            command_parser.add_argument(
                "--emc-r3-workspace", type=Path, default=Path("runs/emc-r3-resource-calibrated-confirmation")
            )
            command_parser.add_argument("--emc-r3-validation-record-sha256", required=True)
            command_parser.add_argument("--max-workers", type=int, default=2)
        else:
            command_parser.add_argument("--manifest-digest", required=True)
    for name, help_text in (
        ("gcf-v2-seal-structured", "seal cheap-first Structured Mechanism Mediation calibration"),
        ("gcf-v2-preflight-provider", "validate the frozen proposal schema/provider with one non-scientific call"),
        ("gcf-v2-calibrate-proposals", "run only the frozen structured-proposal calibration gate"),
        ("gcf-v2-validate-proposals", "run the independent structured-proposal validation state"),
        ("gcf-v2-run-implementation", "run isolated implementation calibration after proposal admission"),
    ):
        command_parser = subparsers.add_parser(name, help=help_text)
        command_parser.add_argument("--workspace", type=Path, default=Path("runs/gcf-v2-structured-mediation-r3"))
        command_parser.add_argument("--model", required=True)
        command_parser.add_argument("--codex-command", default="codex")
        command_parser.add_argument("--reasoning-effort", required=True)
        if name == "gcf-v2-seal-structured":
            command_parser.add_argument("--max-workers", type=int, default=2)
        else:
            command_parser.add_argument("--manifest-digest", required=True)
    for name, help_text in (
        ("emc-r2-seal", "seal the repaired Executable Mechanism Contract protocol before model calls"),
        ("emc-r2-instrumentation", "run the no-model independent instrumentation sensitivity gate"),
        ("emc-r2-preflight", "run the one-call EMC provider and resource preflight"),
        ("emc-r2-calibrate", "run the six-call executable-contract calibration state"),
        ("emc-r2-validate", "run the independent executable-contract validation state"),
    ):
        command_parser = subparsers.add_parser(name, help=help_text)
        command_parser.add_argument("--workspace", type=Path, default=Path("runs/emc-r2-executable-contract"))
        command_parser.add_argument("--model", required=True)
        command_parser.add_argument("--codex-command", default="codex")
        command_parser.add_argument("--reasoning-effort", required=True)
        if name == "emc-r2-seal":
            command_parser.add_argument("--max-workers", type=int, default=2)
        else:
            command_parser.add_argument("--manifest-digest", required=True)
    for name, help_text in (
        ("cib-r1-seal-parent-real", "seal actual consumed SI-2 parent interventions before stochastic calls"),
        ("cib-r1-calibrate-parent-real", "run outcome-blind CIB-R1 stochastic calibration states"),
        ("cib-r1-run-parent-real", "run the calibrated CIB-R1 validation states"),
    ):
        command_parser = subparsers.add_parser(name, help=help_text)
        command_parser.add_argument("--workspace", type=Path, default=Path("runs/cib-r1-parent-real"))
        command_parser.add_argument("--model", required=True)
        command_parser.add_argument("--codex-command", default="codex")
        command_parser.add_argument("--reasoning-effort", required=True)
        if name == "cib-r1-seal-parent-real":
            command_parser.add_argument("--source-workspace", type=Path, default=Path("runs/si2-fresh-search-value-r1"))
            command_parser.add_argument("--source-manifest-digest", required=True)
            command_parser.add_argument("--max-workers", type=int, default=2)
        else:
            command_parser.add_argument("--manifest-digest", required=True)
    for name, help_text in (
        ("si2-run-discovery", "execute the already-sealed SI-2 fresh discovery cohort"),
        ("si2-confirm", "run the frozen SI-2 winner on the withheld confirmation cohort"),
    ):
        command_parser = subparsers.add_parser(name, help=help_text)
        command_parser.add_argument("--workspace", type=Path, default=Path("runs/si2-fresh-search-value-r1"))
        command_parser.add_argument("--manifest-digest", required=True)
        command_parser.add_argument("--model", required=True)
        command_parser.add_argument("--codex-command", default="codex")
        command_parser.add_argument("--reasoning-effort", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "demo-discovery":
            result = run_demo_discovery(args.workspace, candidate_count=args.candidates, seed=args.seed)
        elif args.command == "demo-certify":
            result = run_demo_certification(args.workspace, seed=args.seed)
        elif args.command == "demo-replay":
            result = replay_demo(args.workspace)
        elif args.command == "asha-admission":
            result = run_asha_admission(args.workspace, seeds=args.seeds)
        elif args.command == "local-patch-admission":
            provider = CodexExecProvider(
                command=tuple(shlex.split(args.codex_command, posix=False)),
                model=args.model,
                reasoning_effort=args.reasoning_effort,
            )
            result = run_local_patch_admission(
                args.workspace,
                provider=provider,
                token_ceiling=args.token_ceiling,
                iterations=args.iterations,
                progress=lambda message: print(message, file=sys.stderr, flush=True),
            )
        elif args.command == "local-patch-invalid-autopsy":
            result = audit_local_patch_invalids(args.workspace)
        elif args.command == "local-patch-brd-mechanics-replay":
            result = replay_local_patch_mechanics(args.workspace)
        elif args.command == "local-patch-br-a-seal":
            provider = CodexExecProvider(
                command=tuple(shlex.split(args.codex_command, posix=False)),
                model=args.model,
                reasoning_effort=args.reasoning_effort,
            )
            result = seal_local_patch_readmission(
                args.workspace,
                provider=provider,
                token_ceiling=args.token_ceiling,
                iterations=args.iterations,
            )
        elif args.command == "local-patch-br-a-readmission":
            provider = CodexExecProvider(
                command=tuple(shlex.split(args.codex_command, posix=False)),
                model=args.model,
                reasoning_effort=args.reasoning_effort,
            )
            result = run_local_patch_readmission(
                args.workspace,
                provider=provider,
                manifest_digest=args.manifest_digest,
                progress=lambda message: print(message, file=sys.stderr, flush=True),
            )
        elif args.command in {"search-value-mvp0-seal", "search-value-mvp0-run"}:
            command = tuple(shlex.split(args.codex_command, posix=False))
            local_provider = CodexExecProvider(
                command=command,
                model=args.model,
                reasoning_effort=args.reasoning_effort,
            )
            structural_provider = CodexExecProvider(
                command=command,
                model=args.model,
                reasoning_effort=args.reasoning_effort,
                output_schema=STRUCTURAL_PATCH_SCHEMA,
            )
            if args.command == "search-value-mvp0-seal":
                result = seal_search_value_mvp0(
                    args.workspace,
                    local_provider=local_provider,
                    structural_provider=structural_provider,
                    token_ceiling=args.token_ceiling,
                    wall_ceiling=args.wall_ceiling,
                    cpu_ceiling=args.cpu_ceiling,
                )
            else:
                result = run_search_value_mvp0(
                    args.workspace,
                    manifest_digest=args.manifest_digest,
                    local_provider=local_provider,
                    structural_provider=structural_provider,
                    progress=lambda message: print(message, file=sys.stderr, flush=True),
                )
        elif args.command == "strategy-integration-si1":
            command = tuple(shlex.split(args.codex_command, posix=False))
            local_provider = CodexExecProvider(
                command=command,
                model=args.model,
                reasoning_effort=args.reasoning_effort,
            )
            structural_provider = CodexExecProvider(
                command=command,
                model=args.model,
                reasoning_effort=args.reasoning_effort,
                output_schema=STRUCTURAL_PATCH_SCHEMA,
            )
            result = run_strategy_integration_si1_pilot(
                args.workspace,
                local_provider=local_provider,
                structural_provider=structural_provider,
                max_workers=args.max_workers,
                repair_mode=args.repair,
                progress=lambda message: print(message, file=sys.stderr, flush=True),
            )
        elif args.command == "si2-audit-usage":
            result = audit_si2_secondary_usage(args.workspace, manifest_digest=args.manifest_digest)
        elif args.command == "si2-causality-autopsy":
            result = audit_si2_search_causality(
                args.workspace,
                manifest_digest=args.manifest_digest,
                output_workspace=args.output_workspace,
            )
        elif args.command == "cib-seal-synthetic":
            result = seal_synthetic_cib_protocol(args.workspace)
        elif args.command == "cib-run-synthetic":
            result = run_synthetic_cib(args.workspace, manifest_digest=args.manifest_digest)
        elif args.command == "cmi-r0-seal":
            result = seal_cmi_r0_protocol(args.workspace)
        elif args.command == "cmi-r0-run-synthetic":
            result = run_cmi_r0_synthetic(args.workspace, manifest_digest=args.manifest_digest)
        elif args.command == "cmi-r1-seal-probes":
            result = seal_cmi_probe_calibration(args.workspace)
        elif args.command == "cmi-r1-run-probes":
            result = run_cmi_probe_calibration(args.workspace, manifest_digest=args.manifest_digest)
        elif args.command in {"cmi-r2-seal", "cmi-r2-controls", "cmi-r2-run"}:
            provider = CodexExecProvider(
                command=tuple(shlex.split(args.codex_command, posix=False)),
                model=args.model,
                reasoning_effort=args.reasoning_effort,
                output_schema=__import__("discoveryos.benchmarks.executable_mechanism_contract", fromlist=["IMPLEMENTATION_SCHEMA"]).IMPLEMENTATION_SCHEMA,
            )
            if args.command == "cmi-r2-seal":
                result = seal_cmi_real_diagnosis(args.workspace, cmi_r1_workspace=args.cmi_r1_workspace, cmi_r1_report_sha256=args.cmi_r1_report_sha256, resource_workspace=args.resource_workspace, resource_record_sha256=args.resource_record_sha256, provider=provider, max_workers=args.max_workers)
            elif args.command == "cmi-r2-controls":
                result = run_cmi_real_controls(args.workspace, manifest_digest=args.manifest_digest, provider=provider)
            else:
                result = run_cmi_real_diagnosis(args.workspace, manifest_digest=args.manifest_digest, provider=provider, progress=lambda message: print(message, file=sys.stderr, flush=True))
        elif args.command == "cmi-r3-seal-brief":
            result = seal_cmi_escape_brief(
                args.workspace,
                cmi_r2_workspace=args.cmi_r2_workspace,
                cmi_r2_report_sha256=args.cmi_r2_report_sha256,
                cmi_r2_controls_sha256=args.cmi_r2_controls_sha256,
            )
        elif args.command == "cmi-r3-admit-brief":
            result = admit_cmi_escape_brief(args.workspace, manifest_digest=args.manifest_digest)
        elif args.command == "cmi-r4-seal-operator":
            result = seal_cmi_escape_operator(
                args.workspace,
                cmi_r3_workspace=args.cmi_r3_workspace,
                cmi_r3_report_sha256=args.cmi_r3_report_sha256,
            )
        elif args.command == "cmi-r4-run-operator":
            result = run_cmi_escape_operator(args.workspace, manifest_digest=args.manifest_digest)
        elif args.command == "cmi-r5-seal-causal-value":
            result = seal_cmi_causal_value(
                args.workspace,
                cmi_r4_workspace=args.cmi_r4_workspace,
                cmi_r4_report_sha256=args.cmi_r4_report_sha256,
            )
        elif args.command == "cmi-r5-run-causal-value":
            result = run_cmi_causal_value(args.workspace, manifest_digest=args.manifest_digest)
        elif args.command == "cmi-r6-seal-replication":
            result = seal_cmi_replication_admission(
                args.workspace,
                cmi_r5_workspace=args.cmi_r5_workspace,
                cmi_r5_report_sha256=args.cmi_r5_report_sha256,
                si2_workspace=args.si2_workspace,
                si2_discovery_report_sha256=args.si2_discovery_report_sha256,
                si2_confirmation_report_sha256=args.si2_confirmation_report_sha256,
            )
        elif args.command == "cmi-r6-run-replication":
            result = run_cmi_replication_admission(args.workspace, manifest_digest=args.manifest_digest)
        elif args.command == "cmi-r7-seal-fresh":
            result = seal_cmi_fresh_causal_validation(
                args.workspace,
                cmi_r6_workspace=args.cmi_r6_workspace,
                cmi_r6_report_sha256=args.cmi_r6_report_sha256,
                bank_registry_path=args.bank_registry,
            )
        elif args.command == "cmi-r7-run-fresh":
            result = run_cmi_fresh_causal_validation(args.workspace, manifest_digest=args.manifest_digest)
        elif args.command == "benchmark-bank-validate":
            result = validate_benchmark_bank(load_benchmark_bank(args.registry))
        elif args.command == "benchmark-bank-materialize-dev":
            result = materialize_bank_instance(
                args.registry,
                family_id=args.family_id,
                instance_id=args.instance_id,
                output_dir=args.output_dir,
            )
        elif args.command == "cib-seal-parent-dev":
            result = seal_parent_dev_cib_protocol(args.workspace)
        elif args.command == "cib-run-parent-dev":
            result = run_parent_dev_cib(args.workspace, manifest_digest=args.manifest_digest)
        elif args.command == "parent-cib-r1-settlement":
            result = parent_cib_r1_settlement()
        elif args.command == "gcf-seal-synthetic":
            result = seal_synthetic_gcf_protocol(args.workspace)
        elif args.command == "gcf-run-synthetic":
            result = run_synthetic_gcf(args.workspace, manifest_digest=args.manifest_digest)
        elif args.command in {
            "gcf-r1-seal-mechanism-brief",
            "gcf-r1-calibrate-mechanism-brief",
            "gcf-r1-run-mechanism-brief",
        }:
            provider = CodexExecProvider(
                command=tuple(shlex.split(args.codex_command, posix=False)),
                model=args.model,
                reasoning_effort=args.reasoning_effort,
                output_schema=__import__(
                    "discoveryos.benchmarks.mechanism_brief_real",
                    fromlist=["STAGED_GENERATION_SCHEMA"],
                ).STAGED_GENERATION_SCHEMA,
            )
            if args.command == "gcf-r1-seal-mechanism-brief":
                result = seal_mechanism_brief_protocol(
                    args.workspace,
                    source_workspace=args.source_workspace,
                    source_manifest_digest=args.source_manifest_digest,
                    provider=provider,
                    max_workers=args.max_workers,
                )
            elif args.command == "gcf-r1-calibrate-mechanism-brief":
                result = calibrate_mechanism_brief(
                    args.workspace,
                    manifest_digest=args.manifest_digest,
                    provider=provider,
                    progress=lambda message: print(message, file=sys.stderr, flush=True),
                )
            else:
                result = run_mechanism_brief_validation(
                    args.workspace,
                    manifest_digest=args.manifest_digest,
                    provider=provider,
                    progress=lambda message: print(message, file=sys.stderr, flush=True),
                )
        elif args.command in {
            "gcf-v2-seal-structured",
            "gcf-v2-preflight-provider",
            "gcf-v2-calibrate-proposals",
            "gcf-v2-validate-proposals",
            "gcf-v2-run-implementation",
        }:
            module = __import__(
                "discoveryos.benchmarks.structured_mechanism_mediation",
                fromlist=["MECHANISM_OBJECT_SCHEMA", "IMPLEMENTATION_SCHEMA"],
            )
            command = tuple(shlex.split(args.codex_command, posix=False))
            proposal_provider = CodexExecProvider(
                command=command,
                model=args.model,
                reasoning_effort=args.reasoning_effort,
                output_schema=module.MECHANISM_OBJECT_SCHEMA,
            )
            implementation_provider = CodexExecProvider(
                command=command,
                model=args.model,
                reasoning_effort=args.reasoning_effort,
                output_schema=module.IMPLEMENTATION_SCHEMA,
            )
            if args.command == "gcf-v2-seal-structured":
                result = seal_structured_mediation_protocol(
                    args.workspace,
                    proposal_provider=proposal_provider,
                    implementation_provider=implementation_provider,
                    max_workers=args.max_workers,
                )
            elif args.command == "gcf-v2-preflight-provider":
                result = run_structured_provider_preflight(
                    args.workspace,
                    manifest_digest=args.manifest_digest,
                    proposal_provider=proposal_provider,
                    implementation_provider=implementation_provider,
                )
            elif args.command == "gcf-v2-calibrate-proposals":
                result = calibrate_structured_proposals(
                    args.workspace,
                    manifest_digest=args.manifest_digest,
                    proposal_provider=proposal_provider,
                    implementation_provider=implementation_provider,
                    progress=lambda message: print(message, file=sys.stderr, flush=True),
                )
            elif args.command == "gcf-v2-validate-proposals":
                result = validate_structured_proposals(
                    args.workspace,
                    manifest_digest=args.manifest_digest,
                    proposal_provider=proposal_provider,
                    implementation_provider=implementation_provider,
                    progress=lambda message: print(message, file=sys.stderr, flush=True),
                )
            else:
                result = run_structured_implementation_calibration(
                    args.workspace,
                    manifest_digest=args.manifest_digest,
                    proposal_provider=proposal_provider,
                    implementation_provider=implementation_provider,
                    progress=lambda message: print(message, file=sys.stderr, flush=True),
                )
        elif args.command in {
            "emc-r2-seal",
            "emc-r2-instrumentation",
            "emc-r2-preflight",
            "emc-r2-calibrate",
            "emc-r2-validate",
        }:
            module = __import__(
                "discoveryos.benchmarks.executable_mechanism_contract",
                fromlist=["IMPLEMENTATION_SCHEMA"],
            )
            provider = CodexExecProvider(
                command=tuple(shlex.split(args.codex_command, posix=False)),
                model=args.model,
                reasoning_effort=args.reasoning_effort,
                output_schema=module.IMPLEMENTATION_SCHEMA,
            )
            if args.command == "emc-r2-seal":
                result = seal_emc_protocol(args.workspace, implementation_provider=provider, max_workers=args.max_workers)
            elif args.command == "emc-r2-instrumentation":
                result = run_emc_instrumentation_sensitivity(
                    args.workspace, manifest_digest=args.manifest_digest, implementation_provider=provider
                )
            elif args.command == "emc-r2-preflight":
                result = run_emc_provider_preflight(
                    args.workspace, manifest_digest=args.manifest_digest, implementation_provider=provider
                )
            elif args.command == "emc-r2-calibrate":
                result = run_emc_implementation_calibration(
                    args.workspace,
                    manifest_digest=args.manifest_digest,
                    implementation_provider=provider,
                    progress=lambda message: print(message, file=sys.stderr, flush=True),
                )
            else:
                result = run_emc_implementation_validation(
                    args.workspace,
                    manifest_digest=args.manifest_digest,
                    implementation_provider=provider,
                    progress=lambda message: print(message, file=sys.stderr, flush=True),
                )
        elif args.command in {"emc-resource-r1-seal", "emc-resource-r1-run"}:
            module = __import__(
                "discoveryos.benchmarks.executable_mechanism_contract",
                fromlist=["IMPLEMENTATION_SCHEMA"],
            )
            provider = CodexExecProvider(
                command=tuple(shlex.split(args.codex_command, posix=False)),
                model=args.model,
                reasoning_effort=args.reasoning_effort,
                output_schema=module.IMPLEMENTATION_SCHEMA,
            )
            if args.command == "emc-resource-r1-seal":
                result = seal_emc_resource_calibration(args.workspace, provider=provider)
            else:
                result = run_emc_resource_calibration(
                    args.workspace,
                    manifest_digest=args.manifest_digest,
                    provider=provider,
                    progress=lambda message: print(message, file=sys.stderr, flush=True),
                )
        elif args.command in {"emc-r3-seal", "emc-r3-instrumentation", "emc-r3-calibrate", "emc-r3-validate"}:
            module = __import__(
                "discoveryos.benchmarks.executable_mechanism_contract",
                fromlist=["IMPLEMENTATION_SCHEMA"],
            )
            provider = CodexExecProvider(
                command=tuple(shlex.split(args.codex_command, posix=False)),
                model=args.model,
                reasoning_effort=args.reasoning_effort,
                output_schema=module.IMPLEMENTATION_SCHEMA,
            )
            if args.command == "emc-r3-seal":
                result = seal_emc_r3_protocol(
                    args.workspace,
                    resource_workspace=args.resource_workspace,
                    resource_record_sha256=args.resource_record_sha256,
                    implementation_provider=provider,
                    max_workers=args.max_workers,
                )
            elif args.command == "emc-r3-instrumentation":
                result = run_emc_r3_instrumentation(
                    args.workspace,
                    manifest_digest=args.manifest_digest,
                    implementation_provider=provider,
                )
            elif args.command == "emc-r3-calibrate":
                result = run_emc_r3_calibration(
                    args.workspace,
                    manifest_digest=args.manifest_digest,
                    implementation_provider=provider,
                    progress=lambda message: print(message, file=sys.stderr, flush=True),
                )
            else:
                result = run_emc_r3_validation(
                    args.workspace,
                    manifest_digest=args.manifest_digest,
                    implementation_provider=provider,
                    progress=lambda message: print(message, file=sys.stderr, flush=True),
                )
        elif args.command in {"emc-ocv-r1-seal", "emc-ocv-r1-calibrate", "emc-ocv-r1-validate"}:
            module = __import__(
                "discoveryos.benchmarks.executable_mechanism_contract",
                fromlist=["IMPLEMENTATION_SCHEMA"],
            )
            provider = CodexExecProvider(
                command=tuple(shlex.split(args.codex_command, posix=False)),
                model=args.model,
                reasoning_effort=args.reasoning_effort,
                output_schema=module.IMPLEMENTATION_SCHEMA,
            )
            if args.command == "emc-ocv-r1-seal":
                result = seal_operator_causal_value_protocol(
                    args.workspace,
                    emc_r3_workspace=args.emc_r3_workspace,
                    emc_r3_validation_record_sha256=args.emc_r3_validation_record_sha256,
                    implementation_provider=provider,
                    max_workers=args.max_workers,
                )
            elif args.command == "emc-ocv-r1-calibrate":
                result = calibrate_operator_causal_value(
                    args.workspace,
                    manifest_digest=args.manifest_digest,
                    implementation_provider=provider,
                    progress=lambda message: print(message, file=sys.stderr, flush=True),
                )
            else:
                result = run_operator_causal_value_validation(
                    args.workspace,
                    manifest_digest=args.manifest_digest,
                    implementation_provider=provider,
                    progress=lambda message: print(message, file=sys.stderr, flush=True),
                )
        elif args.command in {
            "cib-r1-seal-parent-real",
            "cib-r1-calibrate-parent-real",
            "cib-r1-run-parent-real",
        }:
            provider = CodexExecProvider(
                command=tuple(shlex.split(args.codex_command, posix=False)),
                model=args.model,
                reasoning_effort=args.reasoning_effort,
                output_schema=__import__(
                    "discoveryos.benchmarks.parent_intervention_real",
                    fromlist=["DESCENDANT_CHAIN_SCHEMA"],
                ).DESCENDANT_CHAIN_SCHEMA,
            )
            if args.command == "cib-r1-seal-parent-real":
                result = seal_parent_real_cib_protocol(
                    args.workspace,
                    source_workspace=args.source_workspace,
                    source_manifest_digest=args.source_manifest_digest,
                    provider=provider,
                    max_workers=args.max_workers,
                )
            elif args.command == "cib-r1-calibrate-parent-real":
                result = calibrate_parent_real_cib(
                    args.workspace,
                    manifest_digest=args.manifest_digest,
                    provider=provider,
                    progress=lambda message: print(message, file=sys.stderr, flush=True),
                )
            else:
                result = run_parent_real_cib(
                    args.workspace,
                    manifest_digest=args.manifest_digest,
                    provider=provider,
                    progress=lambda message: print(message, file=sys.stderr, flush=True),
                )
        elif args.command in {"cmi-search-value-r1-seal", "cmi-search-value-r1-run"}:
            provider = CodexExecProvider(
                command=tuple(shlex.split(args.codex_command, posix=False)),
                model=args.model,
                reasoning_effort=args.reasoning_effort,
            )
            if args.command == "cmi-search-value-r1-seal":
                result = seal_cmi_search_value_r1(
                    args.workspace,
                    cmi_r7_workspace=args.cmi_r7_workspace,
                    cmi_r7_report_sha256=args.cmi_r7_report_sha256,
                    real_provider_preflight_path=args.real_provider_preflight,
                    real_provider_preflight_sha256=args.real_provider_preflight_sha256,
                    provider=provider,
                )
            else:
                result = run_cmi_search_value_r1(
                    args.workspace,
                    manifest_digest=args.manifest_digest,
                    provider=provider,
                    progress=lambda message: print(message, file=sys.stderr, flush=True),
                )
        elif args.command in {"si2-seal", "si2-run-discovery", "si2-confirm"}:
            command = tuple(shlex.split(args.codex_command, posix=False))
            local_provider = CodexExecProvider(
                command=command,
                model=args.model,
                reasoning_effort=args.reasoning_effort,
            )
            structural_provider = CodexExecProvider(
                command=command,
                model=args.model,
                reasoning_effort=args.reasoning_effort,
                output_schema=STRUCTURAL_PATCH_SCHEMA,
            )
            if args.command == "si2-seal":
                result = seal_si2_protocol(
                    args.workspace,
                    local_provider=local_provider,
                    structural_provider=structural_provider,
                    shinka_checkout=args.shinka_checkout,
                    shinka_python=args.shinka_python,
                    headless_cli=args.headless_cli,
                    node_executable=args.node_executable,
                )
            elif args.command == "si2-run-discovery":
                result = run_si2_discovery(
                    args.workspace,
                    manifest_digest=args.manifest_digest,
                    local_provider=local_provider,
                    structural_provider=structural_provider,
                    progress=lambda message: print(message, file=sys.stderr, flush=True),
                )
            else:
                result = run_si2_confirmation(
                    args.workspace,
                    manifest_digest=args.manifest_digest,
                    local_provider=local_provider,
                    structural_provider=structural_provider,
                    progress=lambda message: print(message, file=sys.stderr, flush=True),
                )
        else:
            result = demo_status(args.workspace)
    except (RuntimeError, ValueError, PermissionError) as error:
        print(json.dumps({"status": "ERROR", "error": str(error)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
