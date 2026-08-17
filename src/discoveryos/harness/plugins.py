from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Mapping, Protocol

from discoveryos.runtime.ledger import EvidenceLedger
from discoveryos.util import digest_json, jsonable, pairs, unpairs, utc_now

from .context import ResearchContext, ServiceKey


class HarnessEventType(str, Enum):
    PROFILE_BOOTING = "PROFILE_BOOTING"
    PLUGIN_ACTIVATED = "PLUGIN_ACTIVATED"
    PLUGIN_DISPOSED = "PLUGIN_DISPOSED"
    PROFILE_READY = "PROFILE_READY"
    PROFILE_FAILED = "PROFILE_FAILED"
    PROFILE_DISPOSED = "PROFILE_DISPOSED"
    STRATEGY_HANDOFF = "STRATEGY_HANDOFF"
    SEARCH_STARTED = "SEARCH_STARTED"
    SEARCH_SETTLED = "SEARCH_SETTLED"
    SEARCH_FAILED = "SEARCH_FAILED"


class ResearchCapability(str, Enum):
    """Search-plane roles that a plugin can publish to a Profile."""

    BOOTSTRAP_PROPOSAL = "BOOTSTRAP_PROPOSAL"
    LOCAL_REFINEMENT = "LOCAL_REFINEMENT"
    STRUCTURAL_ESCAPE = "STRUCTURAL_ESCAPE"
    META_STRATEGY = "META_STRATEGY"


@dataclass(frozen=True, slots=True)
class HarnessEvent:
    event_type: HarnessEventType
    profile_id: str
    plugin_id: str | None = None
    payload: tuple[tuple[str, Any], ...] = ()
    created_at: str = field(default_factory=utc_now)


class HarnessEventSink:
    def __init__(self, ledger: EvidenceLedger) -> None:
        self.ledger = ledger

    def emit(self, event: HarnessEvent) -> None:
        self.ledger.record_event(f"HARNESS_{event.event_type.value}", jsonable(event))


@dataclass(frozen=True, slots=True)
class PluginManifest:
    plugin_id: str
    version: str
    source_system: str
    source_revision: str
    license_id: str
    implementation_digest: str
    authority_scope: str
    failure_semantics: str
    replay_contract: str
    capabilities: tuple[ResearchCapability, ...] = ()
    requires: tuple[ServiceKey[Any], ...] = ()
    provides: tuple[ServiceKey[Any], ...] = ()

    def __post_init__(self) -> None:
        required = (
            self.plugin_id,
            self.version,
            self.source_system,
            self.source_revision,
            self.license_id,
            self.authority_scope,
            self.failure_semantics,
            self.replay_contract,
        )
        if not all(item.strip() for item in required):
            raise ValueError("plugin provenance, authority, failure and replay fields are required")
        if len(self.implementation_digest) != 64 or any(
            character not in "0123456789abcdef" for character in self.implementation_digest
        ):
            raise ValueError("plugin implementation digest must be a lowercase SHA-256 digest")
        if len(set(self.provides)) != len(self.provides):
            raise ValueError("plugin cannot declare duplicate provided services")
        if len(set(self.capabilities)) != len(self.capabilities):
            raise ValueError("plugin cannot declare duplicate research capabilities")

    @property
    def digest(self) -> str:
        return digest_json(
            {
                "plugin_id": self.plugin_id,
                "version": self.version,
                "source_system": self.source_system,
                "source_revision": self.source_revision,
                "license_id": self.license_id,
                "implementation_digest": self.implementation_digest,
                "authority_scope": self.authority_scope,
                "failure_semantics": self.failure_semantics,
                "replay_contract": self.replay_contract,
                "capabilities": tuple(item.value for item in self.capabilities),
                "requires": tuple((key.name, key.authority) for key in self.requires),
                "provides": tuple((key.name, key.authority) for key in self.provides),
            }
        )


@dataclass(frozen=True, slots=True)
class PluginSelection:
    plugin_id: str
    manifest_digest: str
    config: tuple[tuple[str, Any], ...] = ()

    @classmethod
    def create(
        cls,
        plugin_id: str,
        manifest_digest: str,
        config: Mapping[str, Any] | None = None,
    ) -> PluginSelection:
        if len(manifest_digest) != 64 or any(
            character not in "0123456789abcdef" for character in manifest_digest
        ):
            raise ValueError("profile selections require a bound plugin manifest digest")
        return cls(
            plugin_id=plugin_id,
            manifest_digest=manifest_digest,
            config=pairs(dict(config or {})),
        )

    def config_dict(self) -> dict[str, Any]:
        return unpairs(self.config)


@dataclass(frozen=True, slots=True)
class ResearchProfile:
    name: str
    plugins: tuple[PluginSelection, ...]
    parent_profile_id: str | None = None
    revision_reason: str | None = None
    adaptive: bool = False
    created_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if not self.name or not self.plugins:
            raise ValueError("research profile requires a name and plugins")
        ids = [item.plugin_id for item in self.plugins]
        if len(ids) != len(set(ids)):
            raise ValueError("research profile plugin ids must be unique")
        if self.parent_profile_id is None and self.revision_reason is not None:
            raise ValueError("a root profile cannot have a revision reason")
        if self.parent_profile_id is not None and not self.revision_reason:
            raise ValueError("a profile revision requires a reason")

    @property
    def profile_id(self) -> str:
        identity = {
            "name": self.name,
            "plugins": self.plugins,
            "parent_profile_id": self.parent_profile_id,
            "revision_reason": self.revision_reason,
            "adaptive": self.adaptive,
        }
        return f"profile_{digest_json(identity)[:24]}"


@dataclass(slots=True)
class PluginActivation:
    services: Mapping[ServiceKey[Any], object]
    dispose: Callable[[], None] = lambda: None
    capabilities: tuple[ResearchCapability, ...] = ()


class ResearchPlugin(Protocol):
    manifest: PluginManifest

    def activate(self, context: ResearchContext, config: Mapping[str, Any]) -> PluginActivation:
        ...


@dataclass(slots=True)
class HarnessSession:
    profile: ResearchProfile
    context: ResearchContext
    _activations: list[tuple[str, PluginActivation]]
    _sink: HarnessEventSink
    _closed: bool = False

    def close(self) -> None:
        if self._closed:
            return
        for plugin_id, activation in reversed(self._activations):
            activation.dispose()
            self._sink.emit(
                HarnessEvent(HarnessEventType.PLUGIN_DISPOSED, self.profile.profile_id, plugin_id)
            )
        self._sink.emit(HarnessEvent(HarnessEventType.PROFILE_DISPOSED, self.profile.profile_id))
        self._closed = True

    def __enter__(self) -> HarnessSession:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        del exc_type, exc, traceback
        self.close()


class ResearchHarness:
    """Boots an ordered profile atomically and tears it down in reverse order."""

    def __init__(self, plugins: tuple[ResearchPlugin, ...]) -> None:
        self._plugins = {plugin.manifest.plugin_id: plugin for plugin in plugins}
        if len(self._plugins) != len(plugins):
            raise ValueError("research plugin ids must be unique")

    def boot(self, profile: ResearchProfile, root: ResearchContext, sink: HarnessEventSink) -> HarnessSession:
        sink.emit(HarnessEvent(HarnessEventType.PROFILE_BOOTING, profile.profile_id))
        ledger = sink.ledger
        ledger.add_node(profile.profile_id, "research_profile", profile)
        if profile.parent_profile_id is not None:
            ledger.add_edge(
                profile.parent_profile_id,
                profile.profile_id,
                "HARNESS_REVISED_TO",
                {"reason": profile.revision_reason},
            )
        context = root
        activations: list[tuple[str, PluginActivation]] = []
        try:
            for index, selection in enumerate(profile.plugins):
                plugin = self._plugins.get(selection.plugin_id)
                if plugin is None:
                    raise KeyError(f"profile references an unknown plugin: {selection.plugin_id}")
                if selection.manifest_digest != plugin.manifest.digest:
                    raise RuntimeError(
                        f"plugin manifest binding mismatch: {selection.plugin_id}"
                    )
                missing = [key.name for key in plugin.manifest.requires if not context.has(key)]
                if missing:
                    raise RuntimeError(
                        f"plugin {selection.plugin_id} is missing services: {','.join(sorted(missing))}"
                    )
                activation = plugin.activate(context, selection.config_dict())
                if activation.capabilities != plugin.manifest.capabilities:
                    raise RuntimeError(
                        f"plugin {selection.plugin_id} activated capabilities that differ "
                        "from its manifest"
                    )
                undeclared = set(activation.services) - set(plugin.manifest.provides)
                if undeclared:
                    raise RuntimeError(
                        f"plugin {selection.plugin_id} provided undeclared services: "
                        + ",".join(sorted(key.name for key in undeclared))
                    )
                context = context.extend(
                    activation.services,
                    scope_id=f"{profile.profile_id}:{index}:{selection.plugin_id}",
                    owner=selection.plugin_id,
                )
                activations.append((selection.plugin_id, activation))
                plugin_node_id = f"plugin:{selection.plugin_id}@{plugin.manifest.digest[:24]}"
                ledger.add_node(
                    plugin_node_id,
                    "research_plugin",
                    {
                        "plugin_id": plugin.manifest.plugin_id,
                        "version": plugin.manifest.version,
                        "manifest_digest": plugin.manifest.digest,
                        "source_system": plugin.manifest.source_system,
                        "source_revision": plugin.manifest.source_revision,
                        "license_id": plugin.manifest.license_id,
                        "implementation_digest": plugin.manifest.implementation_digest,
                        "authority_scope": plugin.manifest.authority_scope,
                        "failure_semantics": plugin.manifest.failure_semantics,
                        "replay_contract": plugin.manifest.replay_contract,
                        "capabilities": tuple(
                            capability.value for capability in plugin.manifest.capabilities
                        ),
                        "requires": tuple(key.name for key in plugin.manifest.requires),
                        "provides": tuple(key.name for key in plugin.manifest.provides),
                    },
                )
                ledger.add_edge(
                    profile.profile_id,
                    plugin_node_id,
                    "PROFILE_LOADS_PLUGIN",
                    {"order": index, "config": selection.config},
                )
                sink.emit(
                    HarnessEvent(HarnessEventType.PLUGIN_ACTIVATED, profile.profile_id, selection.plugin_id)
                )
        except Exception as error:
            for plugin_id, activation in reversed(activations):
                activation.dispose()
                sink.emit(HarnessEvent(HarnessEventType.PLUGIN_DISPOSED, profile.profile_id, plugin_id))
            sink.emit(
                HarnessEvent(
                    HarnessEventType.PROFILE_FAILED,
                    profile.profile_id,
                    payload=pairs({"error_type": type(error).__name__, "message": str(error)}),
                )
            )
            raise
        sink.emit(HarnessEvent(HarnessEventType.PROFILE_READY, profile.profile_id))
        return HarnessSession(profile, context, activations, sink)
