from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from discoveryos.contracts.codec import candidate_from_dict, evidence_from_dict, experiment_from_dict, generation_record_from_dict
from discoveryos.contracts.models import (
    CandidateSpec,
    EvidenceRecord,
    ExperimentSpec,
    ProblemContract,
    ResourceBudget,
    ResourceReconciliation,
    ResourceReservation,
    ResourceUsage,
)
from discoveryos.contracts.patch import GenerationKind, GenerationRecord
from discoveryos.util import canonical_json, jsonable, utc_now


class LedgerConflict(RuntimeError):
    pass


class BudgetExceeded(RuntimeError):
    pass


class EvidenceLedger:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS contracts(
                    contract_digest TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS candidates(
                    candidate_id TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS experiments(
                    experiment_id TEXT PRIMARY KEY, candidate_id TEXT NOT NULL, payload TEXT NOT NULL,
                    created_at TEXT NOT NULL, FOREIGN KEY(candidate_id) REFERENCES candidates(candidate_id)
                );
                CREATE TABLE IF NOT EXISTS evidence(
                    receipt_id TEXT PRIMARY KEY, experiment_id TEXT UNIQUE NOT NULL, candidate_id TEXT NOT NULL,
                    fidelity TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL,
                    FOREIGN KEY(experiment_id) REFERENCES experiments(experiment_id),
                    FOREIGN KEY(candidate_id) REFERENCES candidates(candidate_id)
                );
                CREATE TABLE IF NOT EXISTS graph_nodes(
                    node_id TEXT PRIMARY KEY, node_type TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS graph_edges(
                    source_id TEXT NOT NULL, target_id TEXT NOT NULL, edge_type TEXT NOT NULL, payload TEXT NOT NULL,
                    created_at TEXT NOT NULL, PRIMARY KEY(source_id, target_id, edge_type)
                );
                CREATE TABLE IF NOT EXISTS budget_reservations(
                    reservation_id TEXT PRIMARY KEY, tokens REAL NOT NULL, cpu_seconds REAL NOT NULL,
                    gpu_seconds REAL NOT NULL, device_seconds REAL NOT NULL, wall_seconds REAL NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS resource_reservations(
                    reservation_id TEXT PRIMARY KEY, experiment_id TEXT UNIQUE NOT NULL,
                    tokens REAL NOT NULL, cpu_seconds REAL NOT NULL, gpu_seconds REAL NOT NULL,
                    device_seconds REAL NOT NULL, wall_seconds REAL NOT NULL,
                    actual_tokens REAL, actual_cpu_seconds REAL, actual_gpu_seconds REAL,
                    actual_device_seconds REAL, actual_wall_seconds REAL,
                    status TEXT NOT NULL, payload TEXT, created_at TEXT NOT NULL, reconciled_at TEXT
                );
                CREATE TABLE IF NOT EXISTS resource_reservation_rejections(
                    reservation_id TEXT PRIMARY KEY, experiment_id TEXT UNIQUE NOT NULL,
                    payload TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS frozen_candidates(
                    candidate_id TEXT PRIMARY KEY, contract_digest TEXT NOT NULL, reason TEXT NOT NULL,
                    frozen_at TEXT NOT NULL, FOREIGN KEY(candidate_id) REFERENCES candidates(candidate_id)
                );
                CREATE TABLE IF NOT EXISTS semantic_deltas(
                    delta_id TEXT PRIMARY KEY, candidate_id TEXT NOT NULL, text TEXT NOT NULL,
                    confidence TEXT NOT NULL, tags TEXT NOT NULL, created_at TEXT NOT NULL,
                    FOREIGN KEY(candidate_id) REFERENCES candidates(candidate_id)
                );
                CREATE TABLE IF NOT EXISTS generation_records(
                    generation_id TEXT PRIMARY KEY, root_generation_id TEXT NOT NULL,
                    kind TEXT NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS one_mechanical_repair_per_generation
                    ON generation_records(root_generation_id) WHERE kind='MECHANICAL_REPAIR';
                CREATE TABLE IF NOT EXISTS search_runs(
                    run_id TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS search_actions(
                    decision_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, step INTEGER NOT NULL,
                    payload TEXT NOT NULL, created_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES search_runs(run_id),
                    UNIQUE(run_id, step)
                );
                CREATE TABLE IF NOT EXISTS parent_selection_receipts(
                    receipt_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, step INTEGER NOT NULL,
                    payload TEXT NOT NULL, created_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES search_runs(run_id),
                    UNIQUE(run_id, step)
                );
                CREATE TABLE IF NOT EXISTS novelty_receipts(
                    receipt_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, step INTEGER NOT NULL,
                    attempt INTEGER NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES search_runs(run_id),
                    UNIQUE(run_id, step, attempt)
                );
                CREATE TABLE IF NOT EXISTS events(
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT NOT NULL, payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    def _insert_once(self, table: str, key_column: str, key: str, columns: dict[str, Any]) -> bool:
        payload_columns = {name: (canonical_json(value) if name == "payload" and not isinstance(value, str) else value) for name, value in columns.items()}
        with self.connect() as connection:
            existing = connection.execute(f"SELECT * FROM {table} WHERE {key_column} = ?", (key,)).fetchone()
            if existing:
                for name, value in payload_columns.items():
                    if name.endswith("_at"):
                        continue
                    existing_value = existing[name]
                    if name == "payload" and _payload_without_timestamp(str(existing_value)) == _payload_without_timestamp(str(value)):
                        continue
                    if str(existing_value) != str(value):
                        raise LedgerConflict(f"{table} key collision for {key}")
                return False
            names = [key_column, *payload_columns]
            placeholders = ",".join("?" for _ in names)
            connection.execute(
                f"INSERT INTO {table} ({','.join(names)}) VALUES ({placeholders})",
                (key, *(payload_columns[name] for name in payload_columns)),
            )
            return True

    def add_contract(self, contract: ProblemContract) -> bool:
        return self._insert_once("contracts", "contract_digest", contract.digest, {"payload": jsonable(contract), "created_at": contract.created_at})

    def add_candidate(self, candidate: CandidateSpec) -> bool:
        added = self._insert_once("candidates", "candidate_id", candidate.candidate_id, {"payload": jsonable(candidate), "created_at": candidate.created_at})
        self.add_node(candidate.candidate_id, "candidate", candidate)
        for parent_id in candidate.parent_ids:
            self.add_edge(parent_id, candidate.candidate_id, "DERIVED_FROM", {"operator_id": candidate.operator_id})
        return added

    def add_experiment(self, experiment: ExperimentSpec) -> bool:
        added = self._insert_once(
            "experiments",
            "experiment_id",
            experiment.experiment_id,
            {"candidate_id": experiment.candidate_id, "payload": jsonable(experiment), "created_at": experiment.created_at},
        )
        self.add_node(experiment.experiment_id, "experiment", experiment)
        self.add_edge(experiment.candidate_id, experiment.experiment_id, "EVALUATED_BY", {"fidelity": experiment.fidelity.value})
        return added

    def add_evidence(self, evidence: EvidenceRecord) -> bool:
        added = self._insert_once(
            "evidence",
            "receipt_id",
            evidence.receipt_id,
            {
                "experiment_id": evidence.experiment_id,
                "candidate_id": evidence.candidate_id,
                "fidelity": evidence.fidelity.value,
                "payload": jsonable(evidence),
                "created_at": evidence.created_at,
            },
        )
        self.add_node(evidence.receipt_id, "evidence", evidence)
        self.add_edge(evidence.experiment_id, evidence.receipt_id, "PRODUCED", {})
        return added

    def add_generation(self, record: GenerationRecord) -> bool:
        added = self._insert_once(
            "generation_records",
            "generation_id",
            record.generation_id,
            {
                "root_generation_id": record.root_generation_id,
                "kind": record.kind.value,
                "status": record.status.value,
                "payload": record,
                "created_at": record.created_at,
            },
        )
        self.add_node(record.generation_id, "llm_generation", record)
        self.add_edge(
            record.parent_candidate_id,
            record.generation_id,
            "PROPOSED_BY" if record.kind is GenerationKind.PROPOSAL else "REPAIRED_BY",
            {"status": record.status.value},
        )
        if record.candidate_id:
            self.add_edge(record.generation_id, record.candidate_id, "MATERIALIZED", {})
        return added

    def add_node(self, node_id: str, node_type: str, payload: Any) -> bool:
        return self._insert_once("graph_nodes", "node_id", node_id, {"node_type": node_type, "payload": jsonable(payload), "created_at": utc_now()})

    def node_payload(self, node_id: str, node_type: str | None = None) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT node_type,payload FROM graph_nodes WHERE node_id=?",
                (node_id,),
            ).fetchone()
        if row is None:
            return None
        if node_type is not None and row["node_type"] != node_type:
            raise LedgerConflict(f"graph node type mismatch: {node_id}")
        return json.loads(row["payload"])

    def node_payloads(self, node_type: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM graph_nodes WHERE node_type=? ORDER BY created_at,node_id",
                (node_type,),
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def add_edge(self, source_id: str, target_id: str, edge_type: str, payload: Any) -> bool:
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT payload FROM graph_edges WHERE source_id=? AND target_id=? AND edge_type=?",
                (source_id, target_id, edge_type),
            ).fetchone()
            encoded = canonical_json(payload)
            if existing:
                if existing["payload"] != encoded:
                    raise LedgerConflict(f"graph edge collision: {source_id}->{target_id}:{edge_type}")
                return False
            connection.execute(
                "INSERT INTO graph_edges VALUES (?,?,?,?,?)",
                (source_id, target_id, edge_type, encoded, utc_now()),
            )
            return True

    def add_harness_run_binding(
        self,
        *,
        profile_id: str,
        run_id: str,
        manifest_id: str,
        manifest: Any,
    ) -> bool:
        """Atomically create the manifest node and Profile-to-Run edge."""

        manifest_payload = canonical_json(jsonable(manifest))
        edge_payload = canonical_json({"manifest_id": manifest_id})
        created_at = utc_now()
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            node = connection.execute(
                "SELECT node_type,payload FROM graph_nodes WHERE node_id=?", (manifest_id,)
            ).fetchone()
            if node is not None and (
                node["node_type"] != "harness_run_manifest"
                or node["payload"] != manifest_payload
            ):
                raise LedgerConflict(f"graph node collision: {manifest_id}")
            edge = connection.execute(
                "SELECT payload FROM graph_edges WHERE source_id=? AND target_id=? "
                "AND edge_type='PROFILE_EXECUTED_SEARCH_RUN'",
                (profile_id, run_id),
            ).fetchone()
            if edge is not None and edge["payload"] != edge_payload:
                raise LedgerConflict(
                    f"graph edge collision: {profile_id}->{run_id}:PROFILE_EXECUTED_SEARCH_RUN"
                )
            if node is None:
                connection.execute(
                    "INSERT INTO graph_nodes VALUES (?,?,?,?)",
                    (manifest_id, "harness_run_manifest", manifest_payload, created_at),
                )
            if edge is None:
                connection.execute(
                    "INSERT INTO graph_edges VALUES (?,?,?,?,?)",
                    (
                        profile_id,
                        run_id,
                        "PROFILE_EXECUTED_SEARCH_RUN",
                        edge_payload,
                        created_at,
                    ),
                )
            return node is None or edge is None

    def reserve_budget(self, reservation_id: str, requested: ResourceBudget, limit: ResourceBudget) -> bool:
        requested_values = requested.as_dict()
        limits = limit.as_dict()
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute("SELECT * FROM budget_reservations WHERE reservation_id=?", (reservation_id,)).fetchone()
            if existing:
                if any(float(existing[name]) != value for name, value in requested_values.items()):
                    raise LedgerConflict(f"budget reservation collision: {reservation_id}")
                return False
            totals = connection.execute(
                "SELECT COALESCE(SUM(tokens),0) tokens, COALESCE(SUM(cpu_seconds),0) cpu_seconds, "
                "COALESCE(SUM(gpu_seconds),0) gpu_seconds, COALESCE(SUM(device_seconds),0) device_seconds, "
                "COALESCE(SUM(wall_seconds),0) wall_seconds FROM budget_reservations"
            ).fetchone()
            exceeded = [name for name, value in requested_values.items() if limits[name] > 0 and float(totals[name]) + value > limits[name]]
            if exceeded:
                raise BudgetExceeded("budget exceeded: " + ",".join(exceeded))
            connection.execute(
                "INSERT INTO budget_reservations VALUES (?,?,?,?,?,?,?)",
                (
                    reservation_id,
                    requested.tokens,
                    requested.cpu_seconds,
                    requested.gpu_seconds,
                    requested.device_seconds,
                    requested.wall_seconds,
                    utc_now(),
                ),
            )
            return True

    def reserve_resources(
        self,
        *,
        reservation_id: str,
        experiment_id: str,
        requested: ResourceBudget,
        limit: ResourceBudget,
    ) -> tuple[ResourceReservation, bool]:
        requested_values = requested.as_dict()
        limits = limit.as_dict()
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM resource_reservations WHERE reservation_id=?",
                (reservation_id,),
            ).fetchone()
            if existing:
                if existing["experiment_id"] != experiment_id or any(
                    float(existing[name]) != value for name, value in requested_values.items()
                ):
                    raise LedgerConflict(f"resource reservation collision: {reservation_id}")
                return (
                    ResourceReservation(
                        reservation_id=reservation_id,
                        experiment_id=experiment_id,
                        requested=requested,
                        created_at=existing["created_at"],
                    ),
                    False,
                )
            totals = connection.execute(
                "SELECT "
                "COALESCE(SUM(CASE WHEN status='RECONCILED' THEN actual_tokens ELSE tokens END),0) tokens, "
                "COALESCE(SUM(CASE WHEN status='RECONCILED' THEN actual_cpu_seconds ELSE cpu_seconds END),0) cpu_seconds, "
                "COALESCE(SUM(CASE WHEN status='RECONCILED' THEN actual_gpu_seconds ELSE gpu_seconds END),0) gpu_seconds, "
                "COALESCE(SUM(CASE WHEN status='RECONCILED' THEN actual_device_seconds ELSE device_seconds END),0) device_seconds, "
                "COALESCE(SUM(CASE WHEN status='RECONCILED' THEN actual_wall_seconds ELSE wall_seconds END),0) wall_seconds "
                "FROM resource_reservations"
            ).fetchone()
            exceeded = [
                name
                for name, value in requested_values.items()
                if limits[name] > 0 and float(totals[name]) + value > limits[name]
            ]
            if exceeded:
                raise BudgetExceeded("budget exceeded: " + ",".join(exceeded))
            created_at = utc_now()
            connection.execute(
                "INSERT INTO resource_reservations("
                "reservation_id,experiment_id,tokens,cpu_seconds,gpu_seconds,device_seconds,wall_seconds,"
                "status,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    reservation_id,
                    experiment_id,
                    requested.tokens,
                    requested.cpu_seconds,
                    requested.gpu_seconds,
                    requested.device_seconds,
                    requested.wall_seconds,
                    "RESERVED",
                    created_at,
                ),
            )
        return ResourceReservation(reservation_id, experiment_id, requested, created_at), True

    def reconcile_resources(
        self,
        reservation: ResourceReservation,
        actual: ResourceUsage,
        limit: ResourceBudget,
    ) -> ResourceReconciliation:
        actual_values = actual.as_budget_dict()
        requested_values = reservation.requested.as_dict()
        limits = limit.as_dict()
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM resource_reservations WHERE reservation_id=?",
                (reservation.reservation_id,),
            ).fetchone()
            if not row or row["experiment_id"] != reservation.experiment_id:
                raise LedgerConflict(f"unknown resource reservation: {reservation.reservation_id}")
            if row["status"] == "RECONCILED":
                stored = json.loads(row["payload"])
                result = ResourceReconciliation(
                    reservation_id=stored["reservation_id"],
                    experiment_id=stored["experiment_id"],
                    requested=ResourceBudget(**stored["requested"]),
                    actual=ResourceUsage(**stored["actual"]),
                    exceeded_dimensions=tuple(stored["exceeded_dimensions"]),
                    reconciled_at=stored["reconciled_at"],
                )
                if result.actual != actual:
                    raise LedgerConflict(f"resource reconciliation collision: {reservation.reservation_id}")
                return result
            totals = connection.execute(
                "SELECT "
                "COALESCE(SUM(CASE WHEN status='RECONCILED' THEN actual_tokens ELSE tokens END),0) tokens, "
                "COALESCE(SUM(CASE WHEN status='RECONCILED' THEN actual_cpu_seconds ELSE cpu_seconds END),0) cpu_seconds, "
                "COALESCE(SUM(CASE WHEN status='RECONCILED' THEN actual_gpu_seconds ELSE gpu_seconds END),0) gpu_seconds, "
                "COALESCE(SUM(CASE WHEN status='RECONCILED' THEN actual_device_seconds ELSE device_seconds END),0) device_seconds, "
                "COALESCE(SUM(CASE WHEN status='RECONCILED' THEN actual_wall_seconds ELSE wall_seconds END),0) wall_seconds "
                "FROM resource_reservations WHERE reservation_id<>?",
                (reservation.reservation_id,),
            ).fetchone()
            exceeded = {
                name
                for name, value in actual_values.items()
                if value > requested_values[name]
                or (limits[name] > 0 and float(totals[name]) + value > limits[name])
            }
            reconciled_at = utc_now()
            result = ResourceReconciliation(
                reservation_id=reservation.reservation_id,
                experiment_id=reservation.experiment_id,
                requested=reservation.requested,
                actual=actual,
                exceeded_dimensions=tuple(sorted(exceeded)),
                reconciled_at=reconciled_at,
            )
            connection.execute(
                "UPDATE resource_reservations SET actual_tokens=?,actual_cpu_seconds=?,actual_gpu_seconds=?,"
                "actual_device_seconds=?,actual_wall_seconds=?,status='RECONCILED',payload=?,reconciled_at=? "
                "WHERE reservation_id=?",
                (
                    actual_values["tokens"],
                    actual_values["cpu_seconds"],
                    actual_values["gpu_seconds"],
                    actual_values["device_seconds"],
                    actual_values["wall_seconds"],
                    canonical_json(result),
                    reconciled_at,
                    reservation.reservation_id,
                ),
            )
        return result

    def resource_reconciliation(self, reservation_id: str) -> ResourceReconciliation | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT payload FROM resource_reservations WHERE reservation_id=? AND status='RECONCILED'",
                (reservation_id,),
            ).fetchone()
        if not row:
            return None
        stored = json.loads(row["payload"])
        return ResourceReconciliation(
            reservation_id=stored["reservation_id"],
            experiment_id=stored["experiment_id"],
            requested=ResourceBudget(**stored["requested"]),
            actual=ResourceUsage(**stored["actual"]),
            exceeded_dimensions=tuple(stored["exceeded_dimensions"]),
            reconciled_at=stored["reconciled_at"],
        )

    def record_resource_rejection(
        self,
        *,
        reservation_id: str,
        experiment_id: str,
        requested: ResourceBudget,
        exceeded_dimensions: tuple[str, ...],
    ) -> bool:
        return self._insert_once(
            "resource_reservation_rejections",
            "reservation_id",
            reservation_id,
            {
                "experiment_id": experiment_id,
                "payload": {
                    "reservation_id": reservation_id,
                    "experiment_id": experiment_id,
                    "requested": requested,
                    "exceeded_dimensions": tuple(sorted(exceeded_dimensions)),
                },
                "created_at": utc_now(),
            },
        )

    def resource_rejection(self, reservation_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT payload FROM resource_reservation_rejections WHERE reservation_id=?",
                (reservation_id,),
            ).fetchone()
        return json.loads(row["payload"]) if row else None

    def freeze_candidate(self, candidate_id: str, contract_digest: str, reason: str) -> bool:
        return self._insert_once(
            "frozen_candidates",
            "candidate_id",
            candidate_id,
            {"contract_digest": contract_digest, "reason": reason, "frozen_at": utc_now()},
        )

    def is_frozen(self, candidate_id: str, contract_digest: str) -> bool:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM frozen_candidates WHERE candidate_id=? AND contract_digest=?",
                (candidate_id, contract_digest),
            ).fetchone()
        return row is not None

    def get_candidate(self, candidate_id: str) -> CandidateSpec:
        with self.connect() as connection:
            row = connection.execute("SELECT payload FROM candidates WHERE candidate_id=?", (candidate_id,)).fetchone()
        if not row:
            raise KeyError(candidate_id)
        return candidate_from_dict(json.loads(row["payload"]))

    def candidate_records(self) -> list[CandidateSpec]:
        with self.connect() as connection:
            rows = connection.execute("SELECT payload FROM candidates ORDER BY created_at,candidate_id").fetchall()
        return [candidate_from_dict(json.loads(row["payload"])) for row in rows]

    def get_generation(self, generation_id: str) -> GenerationRecord:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT payload FROM generation_records WHERE generation_id=?",
                (generation_id,),
            ).fetchone()
        if not row:
            raise KeyError(generation_id)
        return generation_record_from_dict(json.loads(row["payload"]))

    def repair_for_root(self, root_generation_id: str) -> GenerationRecord | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT payload FROM generation_records WHERE root_generation_id=? AND kind=?",
                (root_generation_id, GenerationKind.MECHANICAL_REPAIR.value),
            ).fetchone()
        return generation_record_from_dict(json.loads(row["payload"])) if row else None

    def generation_records(self) -> list[GenerationRecord]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM generation_records ORDER BY created_at,generation_id"
            ).fetchall()
        return [generation_record_from_dict(json.loads(row["payload"])) for row in rows]

    def evidence_payloads(self, *, fidelity: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT payload FROM evidence"
        parameters: tuple[Any, ...] = ()
        if fidelity:
            query += " WHERE fidelity=?"
            parameters = (fidelity,)
        query += " ORDER BY created_at, receipt_id"
        with self.connect() as connection:
            return [json.loads(row["payload"]) for row in connection.execute(query, parameters)]

    def get_evidence_for_experiment(self, experiment_id: str) -> EvidenceRecord | None:
        with self.connect() as connection:
            row = connection.execute("SELECT payload FROM evidence WHERE experiment_id=?", (experiment_id,)).fetchone()
        return evidence_from_dict(json.loads(row["payload"])) if row else None

    def get_experiment(self, experiment_id: str) -> ExperimentSpec:
        with self.connect() as connection:
            row = connection.execute("SELECT payload FROM experiments WHERE experiment_id=?", (experiment_id,)).fetchone()
        if not row:
            raise KeyError(experiment_id)
        return experiment_from_dict(json.loads(row["payload"]))

    def experiment_records(self) -> list[ExperimentSpec]:
        with self.connect() as connection:
            rows = connection.execute("SELECT payload FROM experiments ORDER BY created_at,experiment_id").fetchall()
        return [experiment_from_dict(json.loads(row["payload"])) for row in rows]

    def evidence_records(self) -> list[EvidenceRecord]:
        return [evidence_from_dict(payload) for payload in self.evidence_payloads()]

    def add_search_run(self, run_id: str, payload: Any) -> bool:
        return self._insert_once(
            "search_runs",
            "run_id",
            run_id,
            {"payload": payload, "created_at": utc_now()},
        )

    def get_search_run(self, run_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute("SELECT payload FROM search_runs WHERE run_id=?", (run_id,)).fetchone()
        if not row:
            raise KeyError(run_id)
        return json.loads(row["payload"])

    def add_search_action(self, *, decision_id: str, run_id: str, step: int, payload: Any) -> bool:
        return self._insert_once(
            "search_actions",
            "decision_id",
            decision_id,
            {"run_id": run_id, "step": step, "payload": payload, "created_at": utc_now()},
        )

    def search_action_payloads(self, run_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM search_actions WHERE run_id=? ORDER BY step,decision_id",
                (run_id,),
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def add_parent_selection_receipt(
        self,
        *,
        receipt_id: str,
        run_id: str,
        step: int,
        payload: Any,
    ) -> bool:
        return self._insert_once(
            "parent_selection_receipts",
            "receipt_id",
            receipt_id,
            {"run_id": run_id, "step": step, "payload": payload, "created_at": utc_now()},
        )

    def parent_selection_receipt_payloads(self, run_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM parent_selection_receipts WHERE run_id=? ORDER BY step,receipt_id",
                (run_id,),
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def add_novelty_receipt(
        self,
        *,
        receipt_id: str,
        run_id: str,
        step: int,
        attempt: int,
        payload: Any,
    ) -> bool:
        return self._insert_once(
            "novelty_receipts",
            "receipt_id",
            receipt_id,
            {
                "run_id": run_id,
                "step": step,
                "attempt": attempt,
                "payload": payload,
                "created_at": utc_now(),
            },
        )

    def novelty_receipt_payloads(self, run_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM novelty_receipts WHERE run_id=? ORDER BY step,attempt,receipt_id",
                (run_id,),
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def record_event(self, event_type: str, payload: Any) -> None:
        with self.connect() as connection:
            connection.execute("INSERT INTO events(event_type,payload,created_at) VALUES (?,?,?)", (event_type, canonical_json(payload), utc_now()))

    def counts(self) -> dict[str, int]:
        tables = (
            "contracts",
            "candidates",
            "experiments",
            "evidence",
            "graph_nodes",
            "graph_edges",
            "frozen_candidates",
            "resource_reservations",
            "resource_reservation_rejections",
            "generation_records",
            "search_runs",
            "search_actions",
            "parent_selection_receipts",
            "novelty_receipts",
        )
        with self.connect() as connection:
            return {table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) for table in tables}


def _payload_without_timestamp(payload: str) -> str:
    try:
        value = json.loads(payload)
    except json.JSONDecodeError:
        return payload
    if isinstance(value, dict):
        value.pop("created_at", None)
    return canonical_json(value)
