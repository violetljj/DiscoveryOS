from __future__ import annotations

import re
from dataclasses import dataclass, field

from discoveryos.runtime.ledger import EvidenceLedger
from discoveryos.util import canonical_json, digest_json, utc_now


@dataclass(frozen=True, slots=True)
class SemanticDelta:
    candidate_id: str
    change: str
    motivation: str
    effect: str
    applicability: str
    confidence: str
    failure_modes: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    created_at: str = field(default_factory=utc_now)

    @property
    def delta_id(self) -> str:
        return f"delta_{digest_json(self)[:20]}"

    def as_text(self) -> str:
        failures = "; ".join(self.failure_modes) if self.failure_modes else "none observed"
        return (
            f"change: {self.change}\nmotivation: {self.motivation}\neffect: {self.effect}\n"
            f"applicability: {self.applicability}\nconfidence: {self.confidence}\nfailure modes: {failures}"
        )


class SemanticMemory:
    def __init__(self, ledger: EvidenceLedger) -> None:
        self.ledger = ledger

    def add(self, delta: SemanticDelta) -> bool:
        with self.ledger.connect() as connection:
            existing = connection.execute("SELECT text, confidence, tags FROM semantic_deltas WHERE delta_id=?", (delta.delta_id,)).fetchone()
            text = delta.as_text()
            tags = canonical_json(delta.tags)
            if existing:
                if (existing["text"], existing["confidence"], existing["tags"]) != (text, delta.confidence, tags):
                    raise RuntimeError(f"semantic delta collision: {delta.delta_id}")
                return False
            connection.execute(
                "INSERT INTO semantic_deltas VALUES (?,?,?,?,?,?)",
                (delta.delta_id, delta.candidate_id, text, delta.confidence, tags, delta.created_at),
            )
            return True

    def search(self, query: str, limit: int = 5) -> list[str]:
        terms = {term.lower() for term in re.findall(r"[\w-]+", query) if len(term) > 2}
        with self.ledger.connect() as connection:
            rows = connection.execute("SELECT text, tags, created_at FROM semantic_deltas ORDER BY created_at DESC").fetchall()
        scored: list[tuple[int, str, str]] = []
        for row in rows:
            haystack = f"{row['text']} {row['tags']}".lower()
            score = sum(term in haystack for term in terms)
            scored.append((score, row["created_at"], row["text"]))
        scored.sort(reverse=True)
        return [text for score, _, text in scored if score > 0][:limit]


class ProgressiveContextBuilder:
    def __init__(self, memory: SemanticMemory) -> None:
        self.memory = memory

    def build(self, *, task: str, candidate_summary: str, interfaces: tuple[str, ...], forbidden: tuple[str, ...], limit: int = 5) -> str:
        relevant = self.memory.search(f"{task} {candidate_summary}", limit=limit)
        blocks = [f"TASK\n{task}", f"CURRENT CANDIDATE\n{candidate_summary}"]
        if relevant:
            blocks.append("RELEVANT SEMANTIC DELTAS\n" + "\n\n".join(relevant))
        blocks.append("REQUIRED INTERFACES\n" + "\n".join(f"- {item}" for item in interfaces))
        blocks.append("FORBIDDEN\n" + "\n".join(f"- {item}" for item in forbidden))
        return "\n\n".join(blocks)
