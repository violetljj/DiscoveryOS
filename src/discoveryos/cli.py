from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from discoveryos.domains.clearance_demo import (
    demo_status,
    replay_demo,
    run_demo_certification,
    run_demo_discovery,
)
from discoveryos.harness import algorithm_discovery_v1_profile
from discoveryos.util import jsonable


CORE_COMMANDS = frozenset(
    {
        "demo-discovery",
        "demo-certify",
        "status",
        "demo-replay",
        "harness-profile-show",
    }
)


def build_core_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="discoveryos",
        description="Evidence-first Algorithm Discovery Harness",
        epilog=(
            "Historical protocol runners are isolated behind `discoveryos legacy --help`. "
            "Existing direct historical command names remain compatible and are loaded lazily."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    discovery = subparsers.add_parser(
        "demo-discovery",
        help="run the deterministic authority-kernel discovery example",
    )
    discovery.add_argument("--workspace", type=Path, default=Path("runs/clearance-demo"))
    discovery.add_argument("--candidates", type=int, default=12)
    discovery.add_argument("--seed", type=int, default=7)

    certification = subparsers.add_parser(
        "demo-certify",
        help="certify the already-frozen demo winner on final blind",
    )
    certification.add_argument("--workspace", type=Path, default=Path("runs/clearance-demo"))
    certification.add_argument("--seed", type=int, default=7001)

    status = subparsers.add_parser("status", help="inspect a demo workspace without mutating it")
    status.add_argument("--workspace", type=Path, default=Path("runs/clearance-demo"))

    replay = subparsers.add_parser(
        "demo-replay",
        help="re-execute and compare every frozen demo evaluation receipt",
    )
    replay.add_argument("--workspace", type=Path, default=Path("runs/clearance-demo"))

    subparsers.add_parser(
        "harness-profile-show",
        help="print the manifest-bound Research Harness V1 profile without booting plugins",
    )
    return parser


def build_parser() -> argparse.ArgumentParser:
    """Compatibility parser for historical callers; imported only on demand."""

    from discoveryos.legacy_cli import build_parser as build_legacy_parser

    return build_legacy_parser()


def _legacy_main(argv: list[str]) -> int:
    from discoveryos.legacy_cli import main as legacy_main

    return legacy_main(argv)


def main(argv: list[str] | None = None) -> int:
    resolved = list(sys.argv[1:] if argv is None else argv)
    if resolved and resolved[0] == "legacy":
        return _legacy_main(resolved[1:])
    if resolved and resolved[0] not in CORE_COMMANDS and resolved[0] not in {"-h", "--help"}:
        return _legacy_main(resolved)

    args = build_core_parser().parse_args(resolved)
    try:
        if args.command == "demo-discovery":
            result = run_demo_discovery(args.workspace, candidate_count=args.candidates, seed=args.seed)
        elif args.command == "demo-certify":
            result = run_demo_certification(args.workspace, seed=args.seed)
        elif args.command == "demo-replay":
            result = replay_demo(args.workspace)
        elif args.command == "harness-profile-show":
            profile = algorithm_discovery_v1_profile()
            result = {
                "status": "RESEARCH_HARNESS_V1_PROFILE_AVAILABLE",
                "profile_id": profile.profile_id,
                "profile": jsonable(profile),
                "manifest_bound": True,
                "claim_ceiling_changed": False,
            }
        else:
            result = demo_status(args.workspace)
    except (RuntimeError, ValueError, PermissionError) as error:
        print(json.dumps({"status": "ERROR", "error": str(error)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
