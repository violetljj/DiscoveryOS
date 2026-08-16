from __future__ import annotations

import argparse
import json
from pathlib import Path

from discoveryos.domains.clearance_demo import demo_status, replay_demo, run_demo_certification, run_demo_discovery


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
        else:
            result = demo_status(args.workspace)
    except (RuntimeError, ValueError, PermissionError) as error:
        print(json.dumps({"status": "ERROR", "error": str(error)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
