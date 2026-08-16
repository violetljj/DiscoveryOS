from __future__ import annotations

import ast
import io
import math
import tokenize
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum

from discoveryos.contracts.models import ResourceUsage
from discoveryos.util import digest_json, utc_now


class NoveltyDecision(str, Enum):
    ACCEPT = "ACCEPT"
    REJECT_RESAMPLE = "REJECT_RESAMPLE"
    REJECT_EXHAUSTED = "REJECT_EXHAUSTED"


class NoveltyExhaustion(str, Enum):
    REJECT = "REJECT"
    ACCEPT_LAST = "ACCEPT_LAST"


@dataclass(frozen=True, slots=True)
class NoveltyConfig:
    policy_version: str = "shinka_novelty_dos_v1"
    max_novelty_attempts: int = 3
    similarity_threshold: float = 0.94
    semantic_difference_threshold: float = 0.12
    shingle_size: int = 3
    exhaustion: NoveltyExhaustion = NoveltyExhaustion.REJECT

    def __post_init__(self) -> None:
        if not self.policy_version or self.max_novelty_attempts < 1:
            raise ValueError("novelty policy version and positive attempt bound are required")
        if not 0 <= self.similarity_threshold <= 1:
            raise ValueError("novelty similarity threshold must be in [0, 1]")
        if not 0 <= self.semantic_difference_threshold <= 1 or self.shingle_size < 1:
            raise ValueError("novelty semantic threshold or shingle size is invalid")


@dataclass(frozen=True, slots=True)
class NoveltyComparison:
    candidate_id: str
    scopes: tuple[str, ...]
    code: str

    def __post_init__(self) -> None:
        if not self.candidate_id or not self.scopes:
            raise ValueError("novelty comparison identity and scope are required")

    @property
    def code_digest(self) -> str:
        return digest_json({"code": self.code})


@dataclass(frozen=True, slots=True)
class NoveltySimilarity:
    candidate_id: str
    scopes: tuple[str, ...]
    exact_duplicate: bool
    structural_similarity: float
    semantic_difference: float
    comparison_code_digest: str


@dataclass(frozen=True, slots=True)
class NoveltyAssessment:
    decision: NoveltyDecision
    max_similarity: float
    nearest_candidate_id: str | None
    exact_duplicate: bool
    high_similarity: bool
    meaningfully_novel: bool
    reason_codes: tuple[str, ...]
    similarities: tuple[NoveltySimilarity, ...]
    false_reject_diagnostic: str


@dataclass(frozen=True, slots=True)
class NoveltyReceipt:
    receipt_id: str
    run_id: str
    step: int
    attempt: int
    max_attempts: int
    source_candidate_id: str
    proposal_candidate_id: str
    proposal_code_digest: str
    comparison_set_digest: str
    assessment: NoveltyAssessment
    policy_version: str
    usage: ResourceUsage = field(default_factory=ResourceUsage)
    created_at: str = field(default_factory=utc_now)

    @classmethod
    def create(
        cls,
        *,
        run_id: str,
        step: int,
        attempt: int,
        max_attempts: int,
        source_candidate_id: str,
        proposal_candidate_id: str,
        proposal_code: str,
        comparisons: tuple[NoveltyComparison, ...],
        assessment: NoveltyAssessment,
        policy_version: str,
        usage: ResourceUsage | None = None,
    ) -> "NoveltyReceipt":
        proposal_digest = digest_json({"code": proposal_code})
        comparison_digest = digest_json(
            tuple((item.candidate_id, item.scopes, item.code_digest) for item in comparisons)
        )
        identity = {
            "run_id": run_id,
            "step": step,
            "attempt": attempt,
            "max_attempts": max_attempts,
            "source_candidate_id": source_candidate_id,
            "proposal_candidate_id": proposal_candidate_id,
            "proposal_code_digest": proposal_digest,
            "comparison_set_digest": comparison_digest,
            "assessment": assessment,
            "policy_version": policy_version,
        }
        return cls(
            receipt_id=f"novelty_{digest_json(identity)[:24]}",
            usage=usage or ResourceUsage(),
            **identity,
        )


@dataclass(frozen=True, slots=True)
class NoveltyDiagnostics:
    proposal_novelty_rejection_rate: float
    duplicate_avoided_evaluations: int
    novelty_resample_count: int
    novelty_tokens: int
    novelty_wall: float
    accepted_candidate_similarity: float | None
    unique_candidate_rate: float
    novelty_false_reject_diagnostics: tuple[str, ...]


class ShinkaStyleNoveltyPolicy:
    """Cheap exact check, local cosine screen, then a bounded semantic check.

    ShinkaEvolve embeds mutable code and only invokes its LLM novelty judge for
    high-similarity proposals. DOS substitutes a deterministic token-shingle
    representation and AST difference judge so the same cascade is replayable
    and does not require a new external service.
    """

    def __init__(self, config: NoveltyConfig) -> None:
        self.config = config

    def assess(
        self,
        proposal_code: str,
        comparisons: tuple[NoveltyComparison, ...],
        *,
        attempt: int,
    ) -> NoveltyAssessment:
        if attempt < 1 or attempt > self.config.max_novelty_attempts:
            raise ValueError("novelty attempt is outside the frozen bound")
        proposal_tokens = _normalized_tokens(proposal_code)
        proposal_normalized = " ".join(proposal_tokens)
        rows: list[NoveltySimilarity] = []
        for comparison in comparisons:
            existing_tokens = _normalized_tokens(comparison.code)
            existing_normalized = " ".join(existing_tokens)
            exact = proposal_normalized == existing_normalized
            similarity = _cosine_shingle_similarity(
                proposal_tokens,
                existing_tokens,
                self.config.shingle_size,
            )
            semantic_difference = _semantic_difference(proposal_code, comparison.code)
            rows.append(
                NoveltySimilarity(
                    candidate_id=comparison.candidate_id,
                    scopes=comparison.scopes,
                    exact_duplicate=exact,
                    structural_similarity=similarity,
                    semantic_difference=semantic_difference,
                    comparison_code_digest=comparison.code_digest,
                )
            )
        ordered = tuple(
            sorted(
                rows,
                key=lambda item: (-item.structural_similarity, item.candidate_id),
            )
        )
        nearest = ordered[0] if ordered else None
        max_similarity = nearest.structural_similarity if nearest else 0.0
        exact = bool(nearest and nearest.exact_duplicate)
        high_similarity = max_similarity > self.config.similarity_threshold
        meaningfully_novel = bool(
            nearest
            and nearest.semantic_difference >= self.config.semantic_difference_threshold
        )
        if exact:
            reject = True
            reasons = ("EXACT_NORMALIZED_DUPLICATE", "CHEAP_LEVEL_0_REJECT")
            diagnostic = "EXACT_DUPLICATE_LOW_FALSE_REJECT_RISK"
        elif high_similarity and not meaningfully_novel:
            reject = True
            reasons = (
                "LOCAL_STRUCTURAL_SIMILARITY_ABOVE_THRESHOLD",
                "DETERMINISTIC_SEMANTIC_JUDGE_NOT_MEANINGFULLY_NOVEL",
            )
            diagnostic = "NEAR_DUPLICATE_REVIEW_SAMPLE"
        elif high_similarity:
            reject = False
            reasons = (
                "LOCAL_STRUCTURAL_SIMILARITY_ABOVE_THRESHOLD",
                "DETERMINISTIC_SEMANTIC_JUDGE_MEANINGFULLY_NOVEL",
            )
            diagnostic = "HIGH_SIMILARITY_ACCEPTED_AFTER_SEMANTIC_CHECK"
        else:
            reject = False
            reasons = ("LOCAL_STRUCTURAL_SIMILARITY_BELOW_THRESHOLD",)
            diagnostic = "LOW_SIMILARITY_ACCEPT"
        if reject and attempt == self.config.max_novelty_attempts:
            if self.config.exhaustion is NoveltyExhaustion.ACCEPT_LAST:
                decision = NoveltyDecision.ACCEPT
                reasons = (*reasons, "EXHAUSTION_ACCEPT_LAST")
            else:
                decision = NoveltyDecision.REJECT_EXHAUSTED
                reasons = (*reasons, "NOVELTY_ATTEMPTS_EXHAUSTED")
        elif reject:
            decision = NoveltyDecision.REJECT_RESAMPLE
        else:
            decision = NoveltyDecision.ACCEPT
        return NoveltyAssessment(
            decision=decision,
            max_similarity=max_similarity,
            nearest_candidate_id=nearest.candidate_id if nearest else None,
            exact_duplicate=exact,
            high_similarity=high_similarity,
            meaningfully_novel=meaningfully_novel,
            reason_codes=reasons,
            similarities=ordered,
            false_reject_diagnostic=diagnostic,
        )

    def replay(
        self,
        receipt: NoveltyReceipt,
        proposal_code: str,
        comparisons: tuple[NoveltyComparison, ...],
    ) -> tuple[bool, tuple[str, ...]]:
        issues: list[str] = []
        reconstructed = self.assess(proposal_code, comparisons, attempt=receipt.attempt)
        if receipt.proposal_code_digest != digest_json({"code": proposal_code}):
            issues.append("NOVELTY_PROPOSAL_DIGEST_MISMATCH")
        comparison_digest = digest_json(
            tuple((item.candidate_id, item.scopes, item.code_digest) for item in comparisons)
        )
        if receipt.comparison_set_digest != comparison_digest:
            issues.append("NOVELTY_COMPARISON_DIGEST_MISMATCH")
        if receipt.assessment != reconstructed:
            issues.append("NOVELTY_ASSESSMENT_REPLAY_MISMATCH")
        return not issues, tuple(issues)


def novelty_diagnostics(receipts: tuple[NoveltyReceipt, ...]) -> NoveltyDiagnostics:
    rejected = tuple(
        item
        for item in receipts
        if item.assessment.decision in {
            NoveltyDecision.REJECT_RESAMPLE,
            NoveltyDecision.REJECT_EXHAUSTED,
        }
    )
    accepted = tuple(
        item for item in receipts if item.assessment.decision is NoveltyDecision.ACCEPT
    )
    proposal_ids = {item.proposal_candidate_id for item in receipts}
    return NoveltyDiagnostics(
        proposal_novelty_rejection_rate=(len(rejected) / len(receipts)) if receipts else 0.0,
        duplicate_avoided_evaluations=len(rejected),
        novelty_resample_count=sum(
            item.assessment.decision is NoveltyDecision.REJECT_RESAMPLE for item in receipts
        ),
        novelty_tokens=sum(item.usage.tokens for item in receipts),
        novelty_wall=sum(item.usage.wall_seconds for item in receipts),
        accepted_candidate_similarity=(
            sum(item.assessment.max_similarity for item in accepted) / len(accepted)
            if accepted
            else None
        ),
        unique_candidate_rate=(len(proposal_ids) / len(receipts)) if receipts else 0.0,
        novelty_false_reject_diagnostics=tuple(
            item.assessment.false_reject_diagnostic for item in rejected
        ),
    )


def _normalized_tokens(code: str) -> tuple[str, ...]:
    try:
        tokens = tokenize.generate_tokens(io.StringIO(code).readline)
        ignored = {
            tokenize.ENCODING,
            tokenize.ENDMARKER,
            tokenize.INDENT,
            tokenize.DEDENT,
            tokenize.NEWLINE,
            tokenize.NL,
            tokenize.COMMENT,
        }
        return tuple(token.string for token in tokens if token.type not in ignored)
    except (IndentationError, tokenize.TokenError):
        return tuple(code.split())


def _cosine_shingle_similarity(
    left: tuple[str, ...],
    right: tuple[str, ...],
    size: int,
) -> float:
    def shingles(tokens: tuple[str, ...]) -> Counter[tuple[str, ...]]:
        if len(tokens) < size:
            return Counter({tokens: 1}) if tokens else Counter()
        return Counter(tuple(tokens[index : index + size]) for index in range(len(tokens) - size + 1))

    left_counts = shingles(left)
    right_counts = shingles(right)
    if not left_counts and not right_counts:
        return 1.0
    if not left_counts or not right_counts:
        return 0.0
    dot = sum(value * right_counts[key] for key, value in left_counts.items())
    left_norm = math.sqrt(sum(value * value for value in left_counts.values()))
    right_norm = math.sqrt(sum(value * value for value in right_counts.values()))
    return dot / (left_norm * right_norm)


def _semantic_difference(left: str, right: str) -> float:
    try:
        left_tree = ast.dump(ast.parse(left), annotate_fields=False, include_attributes=False)
        right_tree = ast.dump(ast.parse(right), annotate_fields=False, include_attributes=False)
    except SyntaxError:
        left_tree = " ".join(_normalized_tokens(left))
        right_tree = " ".join(_normalized_tokens(right))
    left_features = Counter(_semantic_features(left_tree))
    right_features = Counter(_semantic_features(right_tree))
    if not left_features and not right_features:
        return 0.0
    intersection = sum((left_features & right_features).values())
    union = sum((left_features | right_features).values())
    return 1.0 - (intersection / union if union else 1.0)


def _semantic_features(value: str) -> tuple[str, ...]:
    tokens = tuple(part for part in value.replace("(", " ").replace(")", " ").replace(",", " ").split() if part)
    return tuple(" ".join(tokens[index : index + 2]) for index in range(max(0, len(tokens) - 1)))
