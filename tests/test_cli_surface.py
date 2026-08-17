from __future__ import annotations

import json
import subprocess
import sys
import unittest


class CliSurfaceTests(unittest.TestCase):
    def test_core_cli_import_does_not_load_historical_benchmark_runners(self) -> None:
        script = """
import json, sys
import discoveryos.cli
print(json.dumps(sorted(name for name in sys.modules if name.startswith('discoveryos.benchmarks.'))))
"""
        completed = subprocess.run(
            [sys.executable, "-c", script],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual([], json.loads(completed.stdout))

    def test_core_parser_stays_small_until_compatibility_parser_is_requested(self) -> None:
        script = """
import json, sys
from discoveryos.cli import build_core_parser
build_core_parser()
print(json.dumps('discoveryos.legacy_cli' in sys.modules))
"""
        completed = subprocess.run(
            [sys.executable, "-c", script],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertFalse(json.loads(completed.stdout))

    def test_benchmark_package_import_is_lazy(self) -> None:
        script = """
import json, sys
import discoveryos.benchmarks
print(json.dumps(sorted(name for name in sys.modules if name.startswith('discoveryos.benchmarks.') and name != 'discoveryos.benchmarks')))
"""
        completed = subprocess.run(
            [sys.executable, "-c", script],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual([], json.loads(completed.stdout))

    def test_manifest_bound_profile_is_on_the_core_surface(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "discoveryos", "harness-profile-show"],
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(completed.stdout)
        self.assertEqual("P2_FACTORIAL_PROFILES_REFROZEN", payload["status"])
        self.assertTrue(payload["manifest_bound"])
        self.assertEqual("harness-static-v1", payload["profile"]["name"])
        self.assertEqual(4, len(payload["static_composition_arms"]))
        self.assertEqual(
            "P2_FACTORIAL_PROFILES_REFROZEN",
            payload["factorial_profile_audit"]["record"]["status"],
        )

    def test_legacy_protocol_help_is_lazy_but_reachable(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "discoveryos", "legacy", "--help"],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn("cmi-r7-run-fresh", completed.stdout)

    def test_direct_historical_command_name_remains_compatible(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "discoveryos", "asha-admission", "--help"],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn("--seeds", completed.stdout)


if __name__ == "__main__":
    unittest.main()
