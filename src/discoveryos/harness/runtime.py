from __future__ import annotations

from dataclasses import dataclass

from discoveryos.contracts.models import ProblemContract
from discoveryos.operators.action_controller import AnytimeTraceRecorder, DeterministicActionController
from discoveryos.operators.local_patch import PatchProvider
from discoveryos.operators.novelty import ShinkaStyleNoveltyPolicy
from discoveryos.runtime.artifacts import ArtifactStore
from discoveryos.runtime.ledger import EvidenceLedger
from discoveryos.runtime.scheduler import ExperimentExecutor
from discoveryos.runtime.search_loop import (
    LedgerBackedSearchStateProjector,
    SearchLoopResult,
    SearchLoopRunner,
    SearchRunSpec,
    UnifiedActionExecutor,
)
from discoveryos.util import pairs

from .plugins import (
    HarnessEvent,
    HarnessEventSink,
    HarnessEventType,
    HarnessSession,
    ResearchHarness,
    ResearchProfile,
)
from .bindings import HarnessRunManifest, SourceSnapshot
from .strategies import (
    ACTION_CONTROLLER,
    OPERATOR_REGISTRY,
    OperatorRegistry,
    build_root_research_context,
    standard_research_plugins,
)


@dataclass(slots=True)
class HarnessSearchRuntime:
    """The sole composition path from a ResearchProfile to the unified search loop.

    The harness selects Search-plane services. The existing executor, ledger,
    evaluator and budget settlement remain the frozen authority path.
    """

    profile: ResearchProfile
    session: HarnessSession
    loop: SearchLoopRunner
    sink: HarnessEventSink
    manifest: HarnessRunManifest
    _ran: bool = False

    @classmethod
    def build(
        cls,
        *,
        profile: ResearchProfile,
        spec: SearchRunSpec,
        contract: ProblemContract,
        ledger: EvidenceLedger,
        artifacts: ArtifactStore,
        experiment_executor: ExperimentExecutor,
        base_controller: DeterministicActionController,
        local_provider: PatchProvider,
        structural_provider: PatchProvider,
        manifest: HarnessRunManifest,
        source_snapshot: SourceSnapshot,
        novelty_policy: ShinkaStyleNoveltyPolicy | None = None,
    ) -> HarnessSearchRuntime:
        if spec.contract_digest != contract.digest:
            raise ValueError("harness search spec must bind the frozen contract")
        environment_digest = ledger.get_candidate(spec.root_candidate_id).environment_digest
        issues = manifest.verify(
            profile=profile,
            spec=spec,
            contract=contract,
            environment_digest=environment_digest,
            local_provider=local_provider,
            structural_provider=structural_provider,
            source_snapshot=source_snapshot,
        )
        if issues:
            raise ValueError("harness run manifest mismatch: " + ",".join(issues))
        projector = LedgerBackedSearchStateProjector(
            spec=spec,
            contract=contract,
            controller_config=base_controller.config,
            ledger=ledger,
            artifacts=artifacts,
        )
        root, sink = build_root_research_context(
            contract=contract,
            ledger=ledger,
            artifacts=artifacts,
            experiment_executor=experiment_executor,
            local_provider=local_provider,
            structural_provider=structural_provider,
            base_controller=base_controller,
        )
        session = ResearchHarness(standard_research_plugins()).boot(profile, root, sink)
        try:
            registry = session.context.get(OPERATOR_REGISTRY)
            controller = session.context.get(ACTION_CONTROLLER)
            executor = UnifiedActionExecutor(
                spec=spec,
                contract=contract,
                ledger=ledger,
                artifacts=artifacts,
                projector=projector,
                experiment_executor=experiment_executor,
                novelty_policy=novelty_policy,
                generative_operators=tuple(operator for _, operator in registry.operators),
            )
            loop = SearchLoopRunner(
                controller=controller,
                projector=projector,
                executor=executor,
                trace=AnytimeTraceRecorder(artifacts, ledger),
            )
            ledger.add_node(spec.run_id, "search_run", spec)
            ledger.add_harness_run_binding(
                profile_id=profile.profile_id,
                run_id=spec.run_id,
                manifest_id=manifest.manifest_id,
                manifest=manifest,
            )
        except Exception:
            session.close()
            raise
        return cls(profile=profile, session=session, loop=loop, sink=sink, manifest=manifest)

    @property
    def operator_registry(self) -> OperatorRegistry:
        return self.session.context.get(OPERATOR_REGISTRY)

    def close(self) -> None:
        self.session.close()

    async def run(self) -> SearchLoopResult:
        if self._ran:
            raise RuntimeError("a harness search runtime is single-use")
        self._ran = True
        self.sink.emit(
            HarnessEvent(
                HarnessEventType.SEARCH_STARTED,
                self.profile.profile_id,
                payload=pairs({"run_id": self.loop.projector.spec.run_id}),
            )
        )
        try:
            result = await self.loop.run()
            self.sink.emit(
                HarnessEvent(
                    HarnessEventType.SEARCH_SETTLED,
                    self.profile.profile_id,
                    payload=pairs(
                        {
                            "run_id": result.run_id,
                            "settled_steps": result.settled_steps,
                            "stop_decision_id": result.stop_decision.decision_id,
                        }
                    ),
                )
            )
            return result
        except Exception as error:
            self.sink.emit(
                HarnessEvent(
                    HarnessEventType.SEARCH_FAILED,
                    self.profile.profile_id,
                    payload=pairs(
                        {
                            "run_id": self.loop.projector.spec.run_id,
                            "error_type": type(error).__name__,
                            "message": str(error),
                        }
                    ),
                )
            )
            raise
        finally:
            self.close()
