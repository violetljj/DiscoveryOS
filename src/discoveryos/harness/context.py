from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Generic, Mapping, TypeVar, cast


T = TypeVar("T")


class ResearchContextError(RuntimeError):
    pass


class MissingServiceError(ResearchContextError):
    pass


class AuthorityOverrideError(ResearchContextError):
    pass


@dataclass(frozen=True, slots=True)
class ServiceKey(Generic[T]):
    """Runtime-checkable key for one harness service.

    Authority services are inherited by every scope and cannot be replaced.
    Search-plane services remain replaceable through child contexts.
    """

    name: str
    expected_type: type[Any] | tuple[type[Any], ...] = object
    authority: bool = False

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("service key name is required")

    def validate(self, value: object) -> None:
        if not isinstance(value, self.expected_type):
            expected = (
                ",".join(item.__name__ for item in self.expected_type)
                if isinstance(self.expected_type, tuple)
                else self.expected_type.__name__
            )
            raise TypeError(f"service {self.name} requires {expected}, got {type(value).__name__}")


@dataclass(frozen=True, slots=True)
class ServiceBinding:
    key: ServiceKey[Any]
    value: object
    owner: str


class ResearchContext:
    """Persistent scoped service context.

    Extending a context creates a child layer; the parent is never mutated.
    Isolation keeps immutable authority services plus explicitly exported
    replaceable services. This is composition isolation, not a security sandbox.
    """

    def __init__(
        self,
        *,
        scope_id: str,
        parent: ResearchContext | None = None,
        bindings: Mapping[ServiceKey[Any], ServiceBinding] | None = None,
    ) -> None:
        if not scope_id:
            raise ValueError("research context scope_id is required")
        self.scope_id = scope_id
        self.parent = parent
        self._bindings = dict(bindings or {})

    @classmethod
    def root(
        cls,
        services: Mapping[ServiceKey[Any], object],
        *,
        scope_id: str = "research-root",
    ) -> ResearchContext:
        bindings: dict[ServiceKey[Any], ServiceBinding] = {}
        for key, value in services.items():
            key.validate(value)
            bindings[key] = ServiceBinding(key=key, value=value, owner=scope_id)
        return cls(scope_id=scope_id, bindings=bindings)

    def has(self, key: ServiceKey[T]) -> bool:
        try:
            self.binding(key)
        except MissingServiceError:
            return False
        return True

    def get(self, key: ServiceKey[T]) -> T:
        return cast(T, self.binding(key).value)

    def binding(self, key: ServiceKey[T]) -> ServiceBinding:
        current: ResearchContext | None = self
        while current is not None:
            binding = current._bindings.get(key)
            if binding is not None:
                return binding
            current = current.parent
        raise MissingServiceError(f"service is not available in {self.scope_id}: {key.name}")

    def extend(
        self,
        services: Mapping[ServiceKey[Any], object],
        *,
        scope_id: str,
        owner: str,
    ) -> ResearchContext:
        bindings: dict[ServiceKey[Any], ServiceBinding] = {}
        for key, value in services.items():
            key.validate(value)
            if key.authority and self.has(key) and self.get(key) is not value:
                raise AuthorityOverrideError(f"authority service cannot be replaced: {key.name}")
            bindings[key] = ServiceBinding(key=key, value=value, owner=owner)
        return ResearchContext(scope_id=scope_id, parent=self, bindings=bindings)

    def intercept(
        self,
        key: ServiceKey[T],
        interceptor: Callable[[T], T],
        *,
        scope_id: str,
        owner: str,
    ) -> ResearchContext:
        if key.authority:
            raise AuthorityOverrideError(f"authority service cannot be intercepted: {key.name}")
        return self.extend(
            {key: interceptor(self.get(key))},
            scope_id=scope_id,
            owner=owner,
        )

    def isolate(
        self,
        *,
        scope_id: str,
        exported: tuple[ServiceKey[Any], ...] = (),
    ) -> ResearchContext:
        flattened = self._flatten()
        exported_set = set(exported)
        bindings = {
            key: ServiceBinding(key=key, value=binding.value, owner=binding.owner)
            for key, binding in flattened.items()
            if key.authority or key in exported_set
        }
        missing = [key.name for key in exported if key not in bindings]
        if missing:
            raise MissingServiceError("cannot export missing services: " + ",".join(sorted(missing)))
        return ResearchContext(scope_id=scope_id, bindings=bindings)

    def _flatten(self) -> dict[ServiceKey[Any], ServiceBinding]:
        chain: list[ResearchContext] = []
        current: ResearchContext | None = self
        while current is not None:
            chain.append(current)
            current = current.parent
        flattened: dict[ServiceKey[Any], ServiceBinding] = {}
        for context in reversed(chain):
            flattened.update(context._bindings)
        return flattened
