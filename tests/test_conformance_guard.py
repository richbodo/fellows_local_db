"""Unit tests for the Stop/SubagentStop conformance guard's pure decision.

The guard (.claude/hooks/utils/conformance_guard.py) blocks a stop when a diff
touches the attestation without tests, or adds a deferral comment to a frontier
file without a strict-xfail. We test `_decide()` with synthetic diffs so the
logic is verified without a live hook/session or git. See
plans/conformance_discipline.md.
"""
import importlib.util
import os

_GUARD = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    ".claude", "hooks", "utils", "conformance_guard.py",
)
_spec = importlib.util.spec_from_file_location("conformance_guard", _GUARD)
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)

ARCH = guard.ATTESTATION_FILE
FRONTIER = guard.FRONTIER_FILES[0]  # app/static/app.js


def test_attestation_changed_without_tests_blocks():
    msg = guard._decide(
        changed={ARCH},
        added_by_file={ARCH: ["| CST-X | ... | conformant: now true |"]},
    )
    assert msg and "attestation" in msg.lower()


def test_attestation_changed_with_tests_allows():
    msg = guard._decide(
        changed={ARCH, "tests/test_attestation_has_evidence.py"},
        added_by_file={ARCH: ["| CST-X | ... | conformant |"]},
    )
    assert msg is None


def test_attestation_file_touched_but_no_rows_changed_allows():
    # A prose/typo edit that doesn't add a conformant/partial row must not fire.
    msg = guard._decide(
        changed={ARCH},
        added_by_file={ARCH: ["Fixed a typo in the intro paragraph."]},
    )
    assert msg is None


def test_deferral_phrase_in_frontier_without_xfail_blocks():
    msg = guard._decide(
        changed={FRONTIER},
        added_by_file={FRONTIER: ["  // enforcement lands later, with the fixture"]},
    )
    assert msg and "deferral" in msg.lower()


def test_deferral_phrase_with_strict_xfail_allows():
    msg = guard._decide(
        changed={FRONTIER, "tests/e2e/test_x.py"},
        added_by_file={
            FRONTIER: ["  // inert for now"],
            "tests/e2e/test_x.py": ["@pytest.mark.xfail(strict=True, reason='PR3')"],
        },
    )
    assert msg is None


def test_unrelated_change_allows():
    msg = guard._decide(
        changed={"app/static/styles.css"},
        added_by_file={},
    )
    assert msg is None
