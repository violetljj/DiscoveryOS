from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from discoveryos.contracts.models import DataRole, Fidelity, GateDecision, RunMode
from discoveryos.domains.clearance_demo import initialize_demo, replay_demo, run_demo_certification, run_demo_discovery
from discoveryos.evaluation import GateEngine
from discoveryos.runtime.artifacts import ArtifactStore, ImmutableWriteError
from discoveryos.runtime.vault import VaultAccessError


class ArtifactStoreTests(unittest.TestCase):
    def test_named_records_are_create_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = ArtifactStore(Path(directory))
            first = store.write_record("receipts/example.json", {"value": 1})
            second = store.write_record("receipts/example.json", {"value": 1})
            self.assertEqual(first, second)
            with self.assertRaises(ImmutableWriteError):
                store.write_record("receipts/example.json", {"value": 2})


class VaultTests(unittest.TestCase):
    def test_final_blind_requires_certification_and_frozen_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            context = initialize_demo(Path(directory))
            split_id = next(split.split_id for split in context.contract.data_splits if split.role is DataRole.FINAL_BLIND)
            with self.assertRaises(VaultAccessError):
                context.vault.issue(
                    context.contract,
                    split_id=split_id,
                    candidate_id=context.baseline.candidate_id,
                    mode=RunMode.DISCOVERY,
                    fidelity=Fidelity.G7,
                )
            with self.assertRaises(VaultAccessError):
                context.vault.issue(
                    context.contract,
                    split_id=split_id,
                    candidate_id=context.baseline.candidate_id,
                    mode=RunMode.CERTIFICATION,
                    fidelity=Fidelity.G7,
                )
            context.ledger.freeze_candidate(context.baseline.candidate_id, context.contract.digest, "test freeze")
            capability = context.vault.issue(
                context.contract,
                split_id=split_id,
                candidate_id=context.baseline.candidate_id,
                mode=RunMode.CERTIFICATION,
                fidelity=Fidelity.G7,
            )
            self.assertTrue(context.vault.read(context.contract, capability))


class EndToEndTests(unittest.TestCase):
    def test_discovery_has_no_blind_feedback_then_certifies_frozen_winner(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            discovery = run_demo_discovery(workspace, candidate_count=6, seed=7)
            self.assertEqual("DISCOVERY_COMPLETE", discovery["status"])
            self.assertEqual(0, discovery["blind_receipt_count"])
            winner = discovery["winner_id"]
            decision = json.loads(
                (workspace / "artifacts" / "records" / "decisions" / "discovery_winner.json").read_text(encoding="utf-8")
            )
            self.assertFalse(decision["blind_used"])
            context = initialize_demo(workspace)
            development_evidence = next(item for item in context.ledger.evidence_records() if item.fidelity is Fidelity.G2)
            tampered = replace(development_evidence, evaluator_digest="0" * 64)
            self.assertEqual(GateDecision.INVALID, GateEngine().evaluate(context.contract, tampered).decision)
            tampered_data = replace(development_evidence, data_digest="f" * 64)
            self.assertEqual(GateDecision.INVALID, GateEngine().evaluate(context.contract, tampered_data).decision)
            certification = run_demo_certification(workspace, seed=7001)
            self.assertEqual("CERTIFICATION_COMPLETE", certification["status"])
            self.assertEqual(winner, certification["winner_id"])
            self.assertFalse(certification["winner_changed"])
            self.assertEqual("CERTIFIED_BLIND", certification["claim_ceiling"])
            replay = replay_demo(workspace)
            self.assertEqual("REPLAY_COMPLETE", replay["status"])
            self.assertEqual(replay["total"], replay["passed"])


if __name__ == "__main__":
    unittest.main()
