from __future__ import annotations

from dataclasses import dataclass, field

from discoveryos.runtime.ledger import EvidenceLedger
from discoveryos.util import digest_json, utc_now


@dataclass(frozen=True, slots=True)
class HypothesisNode:
    statement: str
    expected_effects: tuple[str, ...]
    required_experiments: tuple[str, ...]
    falsifiers: tuple[str, ...]
    confidence: str = "low"
    created_at: str = field(default_factory=utc_now)

    @property
    def node_id(self) -> str:
        return f"hyp_{digest_json(self)[:20]}"


@dataclass(frozen=True, slots=True)
class ComponentNode:
    name: str
    interface: str
    artifact_digest: str
    created_at: str = field(default_factory=utc_now)

    @property
    def node_id(self) -> str:
        return f"cmp_{digest_json(self)[:20]}"


@dataclass(frozen=True, slots=True)
class StrategyNode:
    name: str
    policy: tuple[tuple[str, str], ...]
    admitted_budget: float
    created_at: str = field(default_factory=utc_now)

    @property
    def node_id(self) -> str:
        return f"strat_{digest_json(self)[:20]}"


@dataclass(frozen=True, slots=True)
class ClaimNode:
    statement: str
    ceiling: str
    supporting_receipts: tuple[str, ...]
    created_at: str = field(default_factory=utc_now)

    @property
    def node_id(self) -> str:
        return f"claim_{digest_json(self)[:20]}"


class ResearchGraph:
    def __init__(self, ledger: EvidenceLedger) -> None:
        self.ledger = ledger

    def add(self, node: HypothesisNode | ComponentNode | StrategyNode | ClaimNode) -> str:
        node_type = type(node).__name__.removesuffix("Node").lower()
        self.ledger.add_node(node.node_id, node_type, node)
        return node.node_id

    def link(self, source_id: str, target_id: str, relation: str, **metadata: str) -> None:
        self.ledger.add_edge(source_id, target_id, relation, metadata)
