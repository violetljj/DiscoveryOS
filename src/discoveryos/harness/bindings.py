from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from discoveryos.contracts.models import ProblemContract, ResourceBudget
from discoveryos.runtime.ledger import EvidenceLedger
from discoveryos.runtime.search_loop import SearchRunSpec
from discoveryos.util import digest_bytes, digest_json, jsonable, utc_now

from .plugins import ResearchProfile


_SOURCE_ROOT = Path(__file__).resolve().parents[1]
_CODE_BUNDLE_PATHS = (
    "harness/ada_adaptation.py",
    "harness/bindings.py",
    "harness/context.py",
    "harness/evox_strategy.py",
    "harness/fairness.py",
    "harness/plugins.py",
    "harness/runtime.py",
    "harness/strategies.py",
    "operators/action_controller.py",
    "operators/local_patch.py",
    "operators/structural_rewrite.py",
    "runtime/search_loop.py",
)


def harness_code_bundle_digest() -> str:
    """Digest every implementation surface that can change Harness decisions."""

    return digest_json(
        {
            relative: digest_bytes(
                (_SOURCE_ROOT / relative).read_bytes().replace(b"\r\n", b"\n")
            )
            for relative in _CODE_BUNDLE_PATHS
        }
    )


@dataclass(frozen=True, slots=True)
class ProviderBinding:
    provider_name: str
    model: str
    settings_digest: str
    executable_version: str

    def __post_init__(self) -> None:
        if not self.provider_name or not self.model or not self.executable_version:
            raise ValueError("provider identity, model and executable version are required")
        if len(self.settings_digest) != 64:
            raise ValueError("provider settings must be bound by a SHA-256 digest")

    def verify(self, provider: object) -> tuple[str, ...]:
        issues: list[str] = []
        if getattr(provider, "provider_name", None) != self.provider_name:
            issues.append("PROVIDER_NAME_MISMATCH")
        if getattr(provider, "model", None) != self.model:
            issues.append("PROVIDER_MODEL_MISMATCH")
        if getattr(provider, "settings_digest", None) != self.settings_digest:
            issues.append("PROVIDER_SETTINGS_MISMATCH")
        return tuple(issues)


@dataclass(frozen=True, slots=True)
class SourceSnapshot:
    repository_commit: str
    tracked_source_tree_digest: str
    worktree_clean: bool


def capture_git_source_snapshot(repository: Path) -> SourceSnapshot:
    def run(*arguments: str) -> str:
        completed = subprocess.run(
            ("git", *arguments),
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        return completed.stdout.strip()

    commit = run("rev-parse", "HEAD")
    tracked = run("ls-files", "-s")
    status = run("status", "--porcelain=v1", "--untracked-files=all")
    return SourceSnapshot(commit, digest_json(tracked.splitlines()), not status)


@dataclass(frozen=True, slots=True)
class HarnessRunManifest:
    """Create-once binding between a frozen profile and one search run."""

    run_id: str
    search_run_spec_digest: str
    profile_id: str
    plugin_manifest_digests: tuple[tuple[str, str], ...]
    code_bundle_digest: str
    repository_commit: str
    tracked_source_tree_digest: str
    worktree_clean: bool
    local_provider: ProviderBinding
    structural_provider: ProviderBinding
    task_instance_digest: str
    contract_digest: str
    evaluator_bindings: tuple[tuple[str, ...], ...]
    environment_digest: str
    seeds: tuple[int, ...]
    budget: ResourceBudget
    winner_rule_digest: str
    claim_ceiling: str
    manifest_version: str = "HARNESS_RUN_MANIFEST_V1"
    created_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        required_digests = (
            self.search_run_spec_digest,
            self.code_bundle_digest,
            self.tracked_source_tree_digest,
            self.task_instance_digest,
            self.contract_digest,
            self.winner_rule_digest,
        )
        if (
            not self.run_id
            or not self.profile_id
            or not self.repository_commit
            or not self.environment_digest
        ):
            raise ValueError("run, profile and repository identities are required")
        if any(len(value) != 64 for value in required_digests):
            raise ValueError("run bindings must use SHA-256 digests")
        if not self.plugin_manifest_digests or not self.seeds:
            raise ValueError("plugin manifests and seeds must be frozen")
        if len({item[0] for item in self.plugin_manifest_digests}) != len(
            self.plugin_manifest_digests
        ):
            raise ValueError("plugin manifest ids must be unique")

    @property
    def manifest_id(self) -> str:
        return f"harness_run_manifest_{digest_json(self)[:24]}"

    def verify(
        self,
        *,
        profile: ResearchProfile,
        spec: SearchRunSpec,
        contract: ProblemContract,
        environment_digest: str,
        local_provider: object,
        structural_provider: object,
        source_snapshot: SourceSnapshot,
    ) -> tuple[str, ...]:
        issues: list[str] = []
        expected_plugins = tuple(
            (selection.plugin_id, selection.manifest_digest) for selection in profile.plugins
        )
        checks = (
            (self.run_id == spec.run_id, "RUN_ID_MISMATCH"),
            (self.search_run_spec_digest == spec.digest, "SEARCH_RUN_SPEC_MISMATCH"),
            (self.profile_id == profile.profile_id, "PROFILE_BINDING_MISMATCH"),
            (self.plugin_manifest_digests == expected_plugins, "PLUGIN_BINDING_MISMATCH"),
            (self.code_bundle_digest == harness_code_bundle_digest(), "CODE_BUNDLE_MISMATCH"),
            (self.contract_digest == contract.digest, "CONTRACT_BINDING_MISMATCH"),
            (self.evaluator_bindings == contract.evaluator_bindings, "EVALUATOR_BINDING_MISMATCH"),
            (self.environment_digest == environment_digest, "ENVIRONMENT_BINDING_MISMATCH"),
            (self.seeds == spec.seeds, "SEED_BINDING_MISMATCH"),
            (self.budget == spec.budget, "BUDGET_BINDING_MISMATCH"),
            (self.winner_rule_digest == digest_json(contract.winner_rule), "WINNER_RULE_MISMATCH"),
            (self.claim_ceiling == contract.claim_ceiling.value, "CLAIM_CEILING_MISMATCH"),
            (self.repository_commit == source_snapshot.repository_commit, "REPOSITORY_COMMIT_MISMATCH"),
            (
                self.tracked_source_tree_digest == source_snapshot.tracked_source_tree_digest,
                "TRACKED_SOURCE_TREE_MISMATCH",
            ),
            (self.worktree_clean and source_snapshot.worktree_clean, "WORKTREE_NOT_CLEAN"),
        )
        issues.extend(issue for valid, issue in checks if not valid)
        issues.extend(f"LOCAL_{issue}" for issue in self.local_provider.verify(local_provider))
        issues.extend(
            f"STRUCTURAL_{issue}" for issue in self.structural_provider.verify(structural_provider)
        )
        return tuple(issues)


@dataclass(frozen=True, slots=True)
class HarnessRunReplayResult:
    manifest_id: str
    bindings_valid: bool
    issues: tuple[str, ...]


def replay_harness_run_binding(
    ledger: EvidenceLedger,
    manifest: HarnessRunManifest,
    *,
    profile: ResearchProfile,
    spec: SearchRunSpec,
    contract: ProblemContract,
    environment_digest: str,
    local_provider: object,
    structural_provider: object,
    source_snapshot: SourceSnapshot,
) -> HarnessRunReplayResult:
    issues = list(
        manifest.verify(
            profile=profile,
            spec=spec,
            contract=contract,
            environment_digest=environment_digest,
            local_provider=local_provider,
            structural_provider=structural_provider,
            source_snapshot=source_snapshot,
        )
    )
    with ledger.connect() as connection:
        node = connection.execute(
            "SELECT payload FROM graph_nodes WHERE node_id=?", (manifest.manifest_id,)
        ).fetchone()
        edge = connection.execute(
            "SELECT payload FROM graph_edges WHERE source_id=? AND target_id=? "
            "AND edge_type='PROFILE_EXECUTED_SEARCH_RUN'",
            (profile.profile_id, spec.run_id),
        ).fetchone()
    if node is None:
        issues.append("RUN_MANIFEST_NODE_MISSING")
    else:
        stored = json.loads(node["payload"])
        if digest_json(stored) != digest_json(jsonable(manifest)):
            issues.append("RUN_MANIFEST_NODE_MISMATCH")
    if edge is None:
        issues.append("PROFILE_RUN_EDGE_MISSING")
    else:
        stored_edge = json.loads(edge["payload"])
        if stored_edge.get("manifest_id") != manifest.manifest_id:
            issues.append("PROFILE_RUN_EDGE_MISMATCH")
    unique = tuple(dict.fromkeys(issues))
    return HarnessRunReplayResult(manifest.manifest_id, not unique, unique)
