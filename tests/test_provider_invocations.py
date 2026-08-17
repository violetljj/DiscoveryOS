from __future__ import annotations

import json
import os
import stat
import tempfile
import threading
import unittest
from pathlib import Path

from discoveryos.contracts.models import ResourceUsage
from discoveryos.contracts.patch import GenerationKind, GenerationProviderError, GenerationRequest, ProviderGeneration
from discoveryos.runtime.provider_invocations import DurableProviderInvoker, InvocationStateUnknown, _request_binding
from discoveryos.util import canonical_json, digest_json


class _Provider:
    def __init__(self, *, failure: bool = False) -> None:
        self.calls = 0
        self.failure = failure

    def generate(self, request: GenerationRequest) -> ProviderGeneration:
        self.calls += 1
        if self.failure:
            raise GenerationProviderError(
                "fixture failure",
                raw_response="failure",
                transport_log="log",
                usage=ResourceUsage(llm_input_tokens=7, llm_output_tokens=3, wall_seconds=0.5),
                latency_seconds=0.5,
            )
        return ProviderGeneration(
            raw_response='{"implementation_source":"pass"}',
            usage=ResourceUsage(llm_input_tokens=11, llm_output_tokens=5, wall_seconds=0.25),
            latency_seconds=0.25,
            provider_version="fixture-1",
            provider_request_id="request-1",
            transport_log="trace",
        )


def _request() -> GenerationRequest:
    return GenerationRequest.create(
        kind=GenerationKind.PROPOSAL,
        root_generation_id=None,
        provider="fixture",
        model="fixture-model",
        provider_settings_digest="settings",
        prompt_template_digest="template",
        context_digest="context",
        prompt="prompt",
        token_ceiling=100,
    )


class DurableProviderInvokerTests(unittest.TestCase):
    def test_completed_invocation_is_recovered_without_second_provider_call(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            provider = _Provider()
            invoker = DurableProviderInvoker(Path(temporary), namespace="test")
            first = invoker.invoke(provider, _request())
            second = invoker.invoke(provider, _request())
            self.assertFalse(first.recovered)
            self.assertTrue(second.recovered)
            self.assertEqual(1, provider.calls)
            self.assertEqual(first.generation, second.generation)

    def test_orphaned_claim_blocks_retry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            provider = _Provider()
            request = _request()
            binding = _request_binding(request)
            invocation_id = digest_json({"namespace": "test", "request": binding})
            claim = {
                "invocation_id": invocation_id,
                "request_binding": binding,
                "owner": {"owner_id": "dead-owner"},
            }
            path = root / "records" / "provider-invocations" / invocation_id / "claim.json"
            path.parent.mkdir(parents=True)
            path.write_text(canonical_json(claim) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(InvocationStateUnknown, "retry forbidden"):
                DurableProviderInvoker(root, namespace="test").invoke(provider, request)
            self.assertEqual(0, provider.calls)

    def test_concurrent_observer_cannot_duplicate_in_flight_call(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            entered = threading.Event()
            release = threading.Event()

            class _BlockingProvider(_Provider):
                def generate(self, request: GenerationRequest) -> ProviderGeneration:
                    self.calls += 1
                    entered.set()
                    self.assert_released = release.wait(timeout=5)
                    return ProviderGeneration(
                        raw_response='{"implementation_source":"pass"}',
                        usage=ResourceUsage(llm_input_tokens=11, llm_output_tokens=5, wall_seconds=0.25),
                        latency_seconds=0.25,
                        provider_version="fixture-1",
                    )

            provider = _BlockingProvider()
            invoker = DurableProviderInvoker(Path(temporary), namespace="test")
            outcome: list[object] = []
            worker = threading.Thread(target=lambda: outcome.append(invoker.invoke(provider, _request())))
            worker.start()
            self.assertTrue(entered.wait(timeout=5))
            with self.assertRaisesRegex(InvocationStateUnknown, "retry forbidden"):
                invoker.invoke(provider, _request())
            self.assertEqual(1, provider.calls)
            release.set()
            worker.join(timeout=5)
            self.assertFalse(worker.is_alive())
            self.assertTrue(provider.assert_released)
            self.assertEqual(1, len(outcome))
            self.assertEqual(1, provider.calls)

    def test_provider_failure_and_exact_usage_are_replayed_without_retry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            provider = _Provider(failure=True)
            invoker = DurableProviderInvoker(Path(temporary), namespace="test")
            with self.assertRaises(GenerationProviderError) as first:
                invoker.invoke(provider, _request())
            with self.assertRaises(GenerationProviderError) as second:
                invoker.invoke(provider, _request())
            self.assertEqual(1, provider.calls)
            self.assertEqual(first.exception.usage, second.exception.usage)
            self.assertEqual("fixture failure", second.exception.signature)

    def test_terminal_record_binds_request_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            provider = _Provider()
            invoker = DurableProviderInvoker(root, namespace="test")
            invoker.invoke(provider, _request())
            terminal = next((root / "records" / "provider-invocations").glob("*/terminal.json"))
            payload = json.loads(terminal.read_text(encoding="utf-8"))
            payload["request_binding"]["generation_id"] = "tampered"
            os.chmod(terminal, stat.S_IWRITE | stat.S_IREAD)
            terminal.write_text(canonical_json(payload) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "terminal binding mismatch"):
                invoker.invoke(provider, _request())
            self.assertEqual(1, provider.calls)


if __name__ == "__main__":
    unittest.main()
