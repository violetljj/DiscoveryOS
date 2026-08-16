from __future__ import annotations

import unittest

from discoveryos.contracts.models import MetricDirection
from discoveryos.operators.parent_selection import (
    ParentCandidate,
    ParentSelectionConfig,
    ParentSelectionContext,
    ShinkaWeightedParentSelectionPolicy,
    parent_selection_diagnostics,
)


class ParentSelectionMechanicsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = ParentSelectionConfig(base_seed=7, selection_lambda=2.0)
        self.policy = ShinkaWeightedParentSelectionPolicy(self.config)

    def test_quality_exploitation_and_exploration_both_have_weight(self) -> None:
        receipt = self.policy.select(self._context(seed=3))
        components = {item.candidate_id: item for item in receipt.components}
        self.assertGreater(
            components["high"].exploitation_component,
            components["low"].exploitation_component,
        )
        self.assertGreater(components["low"].selection_probability, 0.0)
        self.assertAlmostEqual(1.0, sum(item.selection_probability for item in receipt.components))

    def test_parent_exposure_prevents_permanent_monopoly(self) -> None:
        normal = self.policy.select(self._context(seed=2))
        exposed = self.policy.select(self._context(seed=2, high_exposure=100))
        normal_probability = next(
            item.selection_probability for item in normal.components if item.candidate_id == "high"
        )
        exposed_probability = next(
            item.selection_probability for item in exposed.components if item.candidate_id == "high"
        )
        self.assertLess(exposed_probability, normal_probability)
        self.assertGreater(
            next(item.selection_probability for item in exposed.components if item.candidate_id == "low"),
            0.0,
        )

    def test_invalid_parent_is_excluded_and_archive_incumbent_remain_eligible(self) -> None:
        receipt = self.policy.select(self._context(seed=1, include_invalid=True))
        self.assertNotIn("invalid", {item.candidate_id for item in receipt.components})
        self.assertEqual({"high", "low"}, {item.candidate_id for item in receipt.components})

    def test_deterministic_replay_and_seed_sensitive_sampling(self) -> None:
        context = self._context(seed=5)
        receipt = self.policy.select(context)
        replayed_receipt = self.policy.select(context)
        self.assertEqual(receipt.receipt_id, replayed_receipt.receipt_id)
        self.assertEqual(receipt.selected_parent_ids, replayed_receipt.selected_parent_ids)
        self.assertEqual((True, ()), self.policy.replay(receipt, context))
        selected = {
            self.policy.select(self._context(seed=seed)).selected_parent_ids[0]
            for seed in range(40)
        }
        self.assertEqual({"high", "low"}, selected)

    def test_lineage_diagnostics_do_not_invent_structural_roots(self) -> None:
        contexts = tuple(self._context(seed=seed) for seed in range(8))
        receipts = tuple(self.policy.select(context) for context in contexts)
        diagnostics = parent_selection_diagnostics(receipts, contexts)
        self.assertGreaterEqual(diagnostics.unique_parent_count, 1)
        self.assertGreater(diagnostics.parent_entropy, 0.0)
        self.assertGreater(diagnostics.effective_parent_count, 1.0)
        self.assertIsNone(diagnostics.unique_structural_root_parent_count)
        self.assertAlmostEqual(
            1.0,
            diagnostics.incumbent_parent_fraction + diagnostics.non_incumbent_parent_fraction,
        )

    def test_probability_cap_repairs_effective_parent_distribution(self) -> None:
        uncapped = ShinkaWeightedParentSelectionPolicy(
            ParentSelectionConfig(selection_lambda=10.0)
        )
        capped = ShinkaWeightedParentSelectionPolicy(
            ParentSelectionConfig(
                policy_version="shinka_weighted_dos_v2_probability_cap",
                selection_lambda=10.0,
                maximum_selection_probability=0.8,
            )
        )
        contexts = tuple(self._context(seed=seed) for seed in range(8))
        capped_contexts = tuple(
            ParentSelectionContext(
                run_id=context.run_id,
                step=context.step,
                metric_direction=context.metric_direction,
                candidates=context.candidates,
                seed=context.seed,
                policy_version=capped.config.policy_version,
            )
            for context in contexts
        )
        uncapped_diagnostics = parent_selection_diagnostics(
            tuple(uncapped.select(context) for context in contexts),
            contexts,
        )
        capped_receipts = tuple(capped.select(context) for context in capped_contexts)
        capped_diagnostics = parent_selection_diagnostics(capped_receipts, capped_contexts)
        self.assertGreater(capped_diagnostics.unique_parent_count, 1)
        self.assertGreater(capped_diagnostics.effective_parent_count, 1)
        self.assertGreater(capped_diagnostics.parent_entropy, uncapped_diagnostics.parent_entropy)
        self.assertTrue(any(not receipt.selected_is_incumbent for receipt in capped_receipts))
        self.assertTrue(all(receipt.eligible_parent_count == 2 for receipt in capped_receipts))
        self.assertTrue(all(max(receipt.selection_probabilities) <= 0.8 for receipt in capped_receipts))

    def _context(
        self,
        *,
        seed: int,
        high_exposure: int = 0,
        include_invalid: bool = False,
    ) -> ParentSelectionContext:
        candidates = [
            ParentCandidate(
                candidate_id="high",
                fitness=10.0,
                valid=True,
                generation=2,
                parent_exposure_count=high_exposure,
                improvement_history=(2.0,),
                archive=True,
                incumbent=True,
            ),
            ParentCandidate(
                candidate_id="low",
                fitness=5.0,
                valid=True,
                generation=1,
                parent_exposure_count=0,
                improvement_history=(),
                archive=True,
                incumbent=False,
            ),
        ]
        if include_invalid:
            candidates.append(
                ParentCandidate(
                    candidate_id="invalid",
                    fitness=100.0,
                    valid=False,
                    generation=3,
                    parent_exposure_count=0,
                )
            )
        return ParentSelectionContext(
            run_id="parent-mechanics",
            step=0,
            metric_direction=MetricDirection.MAXIMIZE,
            candidates=tuple(candidates),
            seed=seed,
            policy_version=self.config.policy_version,
        )


if __name__ == "__main__":
    unittest.main()
