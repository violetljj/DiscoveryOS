from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path

from discoveryos.benchmarks import (
    audit_local_patch_invalids,
    replay_local_patch_mechanics,
    run_asha_admission,
    run_local_patch_admission,
    run_local_patch_readmission,
    seal_local_patch_readmission,
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
        else:
            result = demo_status(args.workspace)
    except (RuntimeError, ValueError, PermissionError) as error:
        print(json.dumps({"status": "ERROR", "error": str(error)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
