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
)
from discoveryos.domains.clearance_demo import demo_status, replay_demo, run_demo_certification, run_demo_discovery
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
