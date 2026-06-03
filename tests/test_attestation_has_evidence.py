"""The conformance attestation is a Security Target: a `conformant` claim with
no executable evidence is a finding.

This checker parses the AC/CST attestation tables in docs/Architecture.md and
asserts that every row claiming `conformant` (and not `partial`) cites either:
  - a resolvable test ref (`path/to/test.py[::name]` — file exists, and if a
    `::name` is given, a `def name` / `class name` exists in it) that is NOT
    `xfail` or unconditionally `skip`; or
  - an explicitly declared non-test verification kind (human-review / LLM rubric
    / code inspection / by architecture / by bounding / by construction).

A bare doc pointer (`*.md`) is NOT evidence — a doc that asserts a property does
not prove it. `partial` / `Open` / `not-applicable` rows are exempt from
resolution (they're honestly aspirational) but keep their status.

The marker-state check (no `xfail`/`skip` test as evidence) closes the exact
seam that let `CST-PWA-STORAGE-EVICTABLE` cite an `xfail(strict=True)` test as
proof. A conditional `skipif(cond)` is fine — it's an environment guard that
runs in real CI. Existence alone was never enough; the cited test must be a
live, non-deferred assertion.

The parsing/resolution/marker primitives live in `scripts/conformance_lib.py`
so this gate and `scripts/conformance_report.py` can never disagree about what a
row cites. Rationale + the convention this enforces:
plans/conformance_discipline.md, plans/conformance_report_and_gate.md. Regression
net for the bug where the gate attested `conformant` for durability properties
its code never enforced (plans/private_data_enforcement.md).
"""
import os

from scripts.conformance_lib import ARCH_MD, evaluate_attestation


def test_architecture_md_exists():
    assert os.path.isfile(ARCH_MD), "attestation source missing: {}".format(ARCH_MD)


def test_every_conformant_row_has_executable_evidence():
    with open(ARCH_MD, encoding="utf-8") as f:
        rows = evaluate_attestation(f.read())

    assert rows, "no attestation tables parsed — did the table format change?"

    findings = [f for row in rows for f in row["findings"]]
    assert not findings, (
        "Attestation rows claim conformance without executable evidence "
        "(see plans/conformance_discipline.md § Evidence rule):\n  - "
        + "\n  - ".join(findings)
    )
