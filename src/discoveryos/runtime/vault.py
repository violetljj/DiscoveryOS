from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from pathlib import Path

from discoveryos.contracts.models import DataRole, Fidelity, ProblemContract, RunMode
from discoveryos.runtime.ledger import EvidenceLedger
from discoveryos.util import canonical_json, digest_bytes


class VaultAccessError(PermissionError):
    pass


@dataclass(frozen=True, slots=True)
class SplitCapability:
    contract_digest: str
    split_id: str
    candidate_id: str
    mode: RunMode
    fidelity: Fidelity
    nonce: str
    signature: str


class SplitVault:
    """Fail-closed split access. Hostile evaluator sandboxing remains a deployment concern."""

    def __init__(self, root: Path, ledger: EvidenceLedger) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.ledger = ledger
        self._secret = secrets.token_bytes(32)

    def split_path(self, role: DataRole, relative_path: str) -> Path:
        role_root = (self.root / role.value).resolve()
        path = (role_root / relative_path).resolve()
        if path != role_root and role_root not in path.parents:
            raise VaultAccessError("split path escapes its role root")
        return path

    def put_split(self, role: DataRole, relative_path: str, payload: bytes) -> str:
        path = self.split_path(role, relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if path.read_bytes() != payload:
                raise VaultAccessError(f"split is immutable: {role.value}/{relative_path}")
        else:
            path.write_bytes(payload)
        return digest_bytes(payload)

    def verify_contract_splits(self, contract: ProblemContract) -> tuple[str, ...]:
        issues: list[str] = []
        resolved: set[Path] = set()
        for split in contract.data_splits:
            path = self.split_path(split.role, split.relative_path)
            if path in resolved:
                issues.append(f"SPLIT_PATH_REUSED:{split.split_id}")
            resolved.add(path)
            if not path.is_file():
                issues.append(f"SPLIT_MISSING:{split.split_id}")
            elif digest_bytes(path.read_bytes()) != split.sha256:
                issues.append(f"SPLIT_HASH_MISMATCH:{split.split_id}")
        return tuple(issues)

    def issue(
        self,
        contract: ProblemContract,
        *,
        split_id: str,
        candidate_id: str,
        mode: RunMode,
        fidelity: Fidelity,
    ) -> SplitCapability:
        split = next((item for item in contract.data_splits if item.split_id == split_id), None)
        if split is None:
            raise VaultAccessError(f"unknown split: {split_id}")
        allowed_roles = {
            Fidelity.G1: {DataRole.DEVELOPMENT},
            Fidelity.G2: {DataRole.DEVELOPMENT},
            Fidelity.G3: {DataRole.DEVELOPMENT},
            Fidelity.G4: {DataRole.DEVELOPMENT},
            Fidelity.G5: {DataRole.CALIBRATION},
            Fidelity.G6: {DataRole.SHADOW},
            Fidelity.G7: {DataRole.FINAL_BLIND},
        }
        if split.role not in allowed_roles.get(fidelity, set()):
            raise VaultAccessError(f"split role {split.role.value} is not valid for {fidelity.value}")
        if split.role in {DataRole.SHADOW, DataRole.FINAL_BLIND} and mode is not RunMode.CERTIFICATION:
            raise VaultAccessError(f"{split.role.value} is unavailable in {mode.value} mode")
        if split.role is DataRole.FINAL_BLIND:
            if fidelity is not Fidelity.G7 or not self.ledger.is_frozen(candidate_id, contract.digest):
                raise VaultAccessError("final blind requires a frozen candidate at G7")
        body = {
            "contract_digest": contract.digest,
            "split_id": split_id,
            "candidate_id": candidate_id,
            "mode": mode.value,
            "fidelity": fidelity.value,
            "nonce": secrets.token_hex(16),
        }
        signature = hmac.new(self._secret, canonical_json(body).encode("utf-8"), hashlib.sha256).hexdigest()
        return SplitCapability(
            contract_digest=body["contract_digest"],
            split_id=split_id,
            candidate_id=candidate_id,
            mode=mode,
            fidelity=fidelity,
            nonce=body["nonce"],
            signature=signature,
        )

    def read(self, contract: ProblemContract, capability: SplitCapability) -> bytes:
        body = {
            "contract_digest": capability.contract_digest,
            "split_id": capability.split_id,
            "candidate_id": capability.candidate_id,
            "mode": capability.mode.value,
            "fidelity": capability.fidelity.value,
            "nonce": capability.nonce,
        }
        expected = hmac.new(self._secret, canonical_json(body).encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, capability.signature) or capability.contract_digest != contract.digest:
            raise VaultAccessError("invalid split capability")
        split = next((item for item in contract.data_splits if item.split_id == capability.split_id), None)
        if split is None:
            raise VaultAccessError("capability references an unknown split")
        payload = self.split_path(split.role, split.relative_path).read_bytes()
        if digest_bytes(payload) != split.sha256:
            raise VaultAccessError("split integrity failure")
        return payload
