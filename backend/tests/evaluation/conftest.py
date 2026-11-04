"""Shared configuration for the evaluation tests.

Each later revision supersedes the previous one's code. The superseded test files are kept
byte-identical (they are artefacts of their revision), so the tests in them that assert the old
manifest still MATCHES the code are marked strict xfail here. Strict means they must fail, and they
fail only because the code changed after that revision was registered. Together they assert that
the old revision is now refused (fail closed). Every other test in those files runs and must pass.

- v5.2 superseded v5.1 (transactional quota ledger).
- v5.2.1 superseded v5.2 (scoring amendment for S15, T11 and C12; the v5.2 code changed in
  app/cli.py, app/evaluation/dataset.py, runner.py and scorers.py).
- v5.2.2 superseded v5.2.1 (attestation-aware publication gate; schema-6 manifest; the code changed
  in app/cli.py, app/evaluation/dataset.py, manifest.py, report.py and runner.py).
- v5.2.3 superseded v5.2.2 (registered four-day execution schedule; the same five files changed).
"""

from __future__ import annotations

import pytest

# test name -> the exception it must now fail with
SUPERSEDED_V5_1: dict[str, type[BaseException]] = {
    # check_manifest itself refuses: "configuration differs from ..._v5.1.yaml"
    "test_v5_1_manifest_matches_the_intended_configuration": ValueError,
    # the CLI reports the mismatch instead of "matches" / the preflight result
    "test_eval_validate_fails_closed_without_a_daily_budget": AssertionError,
    "test_eval_validate_passes_with_a_verified_budget": AssertionError,
    "test_eval_run_refuses_before_any_network_call_without_a_budget": AssertionError,
}
SUPERSEDED_V5_2: dict[str, type[BaseException]] = {
    # check_manifest itself refuses: "configuration differs from ..._v5.2.yaml"
    "test_v5_2_manifest_matches_the_intended_configuration": ValueError,
    # the CLI reports the mismatch instead of "matches" / the preflight result
    "test_eval_validate_v5_2_fails_closed_without_a_budget": AssertionError,
    "test_eval_validate_v5_2_passes_with_a_verified_budget": AssertionError,
    "test_eval_run_v5_2_refuses_without_a_budget_before_any_network_call": AssertionError,
}
SUPERSEDED_V5_2_1: dict[str, type[BaseException]] = {
    # check_manifest itself refuses: "configuration differs from ..._v5.2.1.yaml"
    "test_v5_2_1_manifest_matches_the_intended_configuration": ValueError,
    # the CLI reports the mismatch instead of "matches" / the preflight result
    "test_eval_validate_v5_2_1_reports_the_amendment_and_fails_closed_without_a_budget": (
        AssertionError
    ),
    "test_eval_validate_v5_2_1_passes_with_a_verified_budget": AssertionError,
    "test_eval_run_v5_2_1_refuses_without_a_budget_before_any_network_call": AssertionError,
}
SUPERSEDED_V5_2_2: dict[str, type[BaseException]] = {
    # check_manifest itself refuses: "configuration differs from ..._v5.2.2.yaml"
    "test_v5_2_2_manifest_matches_the_intended_configuration": ValueError,
    "test_the_manifest_also_refuses_modified_evidence": ValueError,
    # the CLI reports the mismatch instead of "matches" / the preflight result
    "test_eval_validate_reports_the_attestation_and_fails_closed_without_a_budget": AssertionError,
    "test_eval_validate_v5_2_2_passes_with_a_verified_budget": AssertionError,
    "test_eval_run_v5_2_2_refuses_without_a_budget_before_any_network_call": AssertionError,
}
SUPERSEDED = {
    "test_execution_v5_1.py": (SUPERSEDED_V5_1, "v5.1 superseded by v5.2"),
    "test_execution_v5_2.py": (SUPERSEDED_V5_2, "v5.2 superseded by v5.2.1"),
    "test_scoring_v5_2_1.py": (SUPERSEDED_V5_2_1, "v5.2.1 superseded by v5.2.2"),
    "test_publication_gate_v5_2_2.py": (SUPERSEDED_V5_2_2, "v5.2.2 superseded by v5.2.3"),
}
REASON = (
    "{}: its manifest no longer matches the execution code, so it is refused before any network "
    "call (expected)"
)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        tests, why = SUPERSEDED.get(item.path.name, ({}, ""))
        expected = tests.get(getattr(item, "originalname", ""))
        if expected is not None:
            item.add_marker(
                pytest.mark.xfail(strict=True, reason=REASON.format(why), raises=expected)
            )
