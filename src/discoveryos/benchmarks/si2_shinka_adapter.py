from __future__ import annotations

import argparse
import json
import os
import random
import time
from pathlib import Path
from typing import Any

from discoveryos.benchmarks.si2_tasks import normalized_source, si2_confirmation_tasks, si2_discovery_tasks
from discoveryos.util import digest_bytes


SHINKA_SOURCE_COMMIT = "2bf8cfeb6fd39c79555cd94a8f395d64e740aae8"


def task_by_id(task_id: str):
    matches = [item for item in (*si2_discovery_tasks(), *si2_confirmation_tasks()) if item.task.task_id == task_id]
    if len(matches) != 1:
        raise ValueError(f"unknown or duplicate SI-2 task: {task_id}")
    return matches[0]


def shinka_evaluator_source(public_tests_source: str, evaluator_source: str) -> str:
    payload = {
        "public_tests_source": public_tests_source,
        "evaluator_source": evaluator_source,
    }
    return f'''from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

PAYLOAD = {payload!r}


def main(program_path: str, results_dir: str) -> None:
    output = Path(results_dir)
    output.mkdir(parents=True, exist_ok=True)
    correct = False
    error = ""
    metrics = {{"combined_score": 0.0, "public": {{"score": 0.0}}, "private": {{}}}}
    try:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "algorithm.py").write_text(Path(program_path).read_text(encoding="utf-8"), encoding="utf-8")
            (root / "public_tests.py").write_text(PAYLOAD["public_tests_source"], encoding="utf-8")
            (root / "evaluate.py").write_text(PAYLOAD["evaluator_source"], encoding="utf-8")
            env = os.environ.copy(); env["PYTHONDONTWRITEBYTECODE"] = "1"
            public = subprocess.run([sys.executable, "public_tests.py"], cwd=root, env=env, capture_output=True, text=True, timeout=30)
            if public.returncode != 0:
                raise RuntimeError(public.stderr or public.stdout or "public tests failed")
            evaluated = subprocess.run([sys.executable, "evaluate.py"], cwd=root, env=env, capture_output=True, text=True, timeout=60)
            if evaluated.returncode != 0:
                raise RuntimeError(evaluated.stderr or evaluated.stdout or "evaluator failed")
            payload = json.loads(evaluated.stdout.splitlines()[-1])
            score = float(payload["metrics"]["score"])
            correct = float(payload["metrics"]["valid"]) == 1.0
            metrics = {{
                "combined_score": score if correct else 0.0,
                "public": {{"score": score if correct else 0.0}},
                "private": {{"discoveryos_valid": correct}},
            }}
    except Exception as exc:
        error = f"{{type(exc).__name__}}:{{exc}}"
        metrics["private"]["error"] = error
    (output / "metrics.json").write_text(json.dumps(metrics, sort_keys=True), encoding="utf-8")
    (output / "correct.json").write_text(json.dumps({{"correct": correct, "error": error}}, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--program_path", required=True)
    parser.add_argument("--results_dir", required=True)
    args = parser.parse_args()
    main(args.program_path, args.results_dir)
'''


def _model_usage(metadata: dict[str, Any]) -> tuple[int, int, int]:
    result = metadata.get("llm_result")
    if not isinstance(result, dict):
        return 0, 0, 0
    return (
        int(result.get("input_tokens") or 0),
        int(result.get("output_tokens") or 0),
        int(result.get("thinking_tokens") or 0),
    )


def run_shinka_arm(
    *,
    task_id: str,
    results_dir: Path,
    model: str,
    reasoning_effort: str,
    generations: int,
    token_ceiling: int,
    seed: int,
) -> dict[str, Any]:
    from shinka.core import EvolutionConfig, ShinkaEvolveRunner
    from shinka.database import DatabaseConfig
    from shinka.launch import LocalJobConfig

    item = task_by_id(task_id)
    results_dir = results_dir.resolve()
    if results_dir.exists() and any(results_dir.iterdir()):
        raise RuntimeError("Shinka SI-2 arm requires an empty results directory")
    results_dir.mkdir(parents=True, exist_ok=True)
    random.seed(seed)
    started = time.monotonic()
    initial_source = (
        "# EVOLVE-BLOCK-START\n"
        + normalized_source(item.task.algorithm_source).strip()
        + "\n# EVOLVE-BLOCK-END\n"
    )
    evaluator_source = shinka_evaluator_source(
        normalized_source(item.task.public_tests_source),
        normalized_source(item.task.evaluator_source),
    )
    task_message = (
        item.task.question
        + " Modify only the evolved Python program. Preserve the required function signature and return a complete implementation."
    )
    runner = ShinkaEvolveRunner(
        evo_config=EvolutionConfig(
            task_sys_msg=task_message,
            patch_types=["full"],
            patch_type_probs=[1.0],
            num_generations=generations,
            max_patch_resamples=1,
            max_patch_attempts=1,
            job_type="local",
            language="python",
            llm_models=[f"headless/codex@{model}?effort={reasoning_effort}"],
            llm_dynamic_selection="fixed",
            llm_kwargs={"temperatures": [0.0], "max_tokens": [8192], "reasoning_efforts": [reasoning_effort]},
            meta_rec_interval=None,
            embedding_model=None,
            init_program_path=None,
            results_dir=str(results_dir),
            max_novelty_attempts=1,
            novelty_llm_models=None,
            use_text_feedback=True,
            enable_controlled_oversubscription=False,
        ),
        job_config=LocalJobConfig(eval_program_path="unused", time="00:02:00"),
        db_config=DatabaseConfig(
            db_path="evolution_db.sqlite",
            num_islands=1,
            archive_size=8,
            num_archive_inspirations=1,
            num_top_k_inspirations=1,
        ),
        max_evaluation_jobs=1,
        max_proposal_jobs=1,
        max_db_workers=1,
        verbose=False,
        init_program_str=initial_source,
        evaluate_str=evaluator_source,
    )
    runner.run()
    programs = sorted(runner.db.get_all_programs(), key=lambda program: (program.generation, program.timestamp, program.id))
    cumulative_tokens = 0
    cumulative_input = 0
    cumulative_output = 0
    cumulative_thinking = 0
    best = 0.0
    observations = []
    for program in programs:
        input_tokens, output_tokens, thinking_tokens = _model_usage(program.metadata or {})
        cumulative_input += input_tokens
        cumulative_output += output_tokens
        cumulative_thinking += thinking_tokens
        cumulative_tokens += input_tokens + output_tokens
        if program.correct and program.combined_score is not None:
            best = max(best, float(program.combined_score))
        observations.append(
            {
                "candidate_id": program.id,
                "generation": int(program.generation),
                "cumulative_tokens": cumulative_tokens,
                "score": float(program.combined_score or 0.0),
                "best_score": best,
                "valid": bool(program.correct),
                "parent_id": program.parent_id,
                "source_digest": digest_bytes(program.code.encode("utf-8")),
            }
        )
    makespan = time.monotonic() - started
    result = {
        "task_id": task_id,
        "arm": "EXTERNAL_STRONG_BASELINE",
        "external_system": "SakanaAI/ShinkaEvolve",
        "external_source_commit": SHINKA_SOURCE_COMMIT,
        "model": model,
        "reasoning_effort": reasoning_effort,
        "seed": seed,
        "generation_limit": generations,
        "observations": observations,
        "best_score": best,
        "actual_usage": {
            "tokens": cumulative_tokens,
            "llm_input_tokens": cumulative_input,
            "llm_output_tokens": cumulative_output,
            "llm_thinking_tokens": cumulative_thinking,
            "end_to_end_makespan": makespan,
        },
        "evaluator_calls": len(programs),
        "valid_candidate_rate": sum(bool(program.correct) for program in programs) / max(1, len(programs)),
        "resource_checks": {
            "token_ceiling_respected": cumulative_tokens <= token_ceiling,
        },
    }
    output_path = results_dir / "si2-shinka-arm-result.json"
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--reasoning-effort", required=True)
    parser.add_argument("--generations", type=int, required=True)
    parser.add_argument("--token-ceiling", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    args = parser.parse_args()
    result = run_shinka_arm(
        task_id=args.task_id,
        results_dir=args.results_dir,
        model=args.model,
        reasoning_effort=args.reasoning_effort,
        generations=args.generations,
        token_ceiling=args.token_ceiling,
        seed=args.seed,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    main()
