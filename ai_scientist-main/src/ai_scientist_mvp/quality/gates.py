"""Small, deterministic quality gates with explicit not-evaluable states."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_scientist_mvp.domain import canonical_json


@dataclass(frozen=True)
class QualityGate:
    gate_id: str
    status: str
    numerator: int | None
    denominator: int | None
    note: str


@dataclass(frozen=True)
class QualityGateReport:
    schema_validity: QualityGate
    citation_accuracy: QualityGate
    hypothesis_operationalization: QualityGate
    data_recompute_consistency: QualityGate
    content_hash: str

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_validity": self.schema_validity.__dict__,
            "citation_accuracy": self.citation_accuracy.__dict__,
            "hypothesis_operationalization": self.hypothesis_operationalization.__dict__,
            "data_recompute_consistency": self.data_recompute_consistency.__dict__,
        }
        payload["content_hash"] = canonical_json.content_hash_excluding(payload)
        return payload


def build_quality_gate_report(
    *,
    schema_valid: int,
    schema_total: int,
    citations_verified: int,
    citations_total: int,
    hypotheses_operational: int,
    hypotheses_total: int,
    recomputations_matching: int,
    recomputations_total: int,
) -> QualityGateReport:
    gates = [
        _gate(
            "SCHEMA_VALIDITY", schema_valid, schema_total,
            "Schema validation only; not scientific validity.",
        ),
        _gate(
            "CITATION_ACCURACY", citations_verified, citations_total,
            "Only exact quote checks count as verified.",
        ),
        _gate(
            "HYPOTHESIS_OPERATIONALIZATION", hypotheses_operational, hypotheses_total,
            "Operational means required fields and validator pass.",
        ),
        _gate(
            "DATA_RECOMPUTE_CONSISTENCY", recomputations_matching, recomputations_total,
            "Compares deterministic recomputation outputs.",
        ),
    ]
    report = QualityGateReport(
        schema_validity=gates[0],
        citation_accuracy=gates[1],
        hypothesis_operationalization=gates[2],
        data_recompute_consistency=gates[3],
        content_hash="",
    )
    payload = report.to_payload()
    return QualityGateReport(
        schema_validity=gates[0],
        citation_accuracy=gates[1],
        hypothesis_operationalization=gates[2],
        data_recompute_consistency=gates[3],
        content_hash=payload["content_hash"],
    )


def audit_reproducibility_manifest(
    root: Path, expected_sha256: dict[str, str]
) -> tuple[QualityGate, ...]:
    """Check a path-relative file hash manifest without reading secrets."""
    passed = 0
    findings: list[str] = []
    for relative, expected in sorted(expected_sha256.items()):
        path = (root / relative).resolve()
        if path.parent != root.resolve() and root.resolve() not in path.parents:
            findings.append(f"PATH_ESCAPE:{relative}")
            continue
        if not path.is_file():
            findings.append(f"MISSING:{relative}")
            continue
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual.casefold() != expected.casefold():
            findings.append(f"HASH_MISMATCH:{relative}")
            continue
        passed += 1
    status = "PASS" if not findings else "FAIL"
    note = "all listed files match" if not findings else "; ".join(findings)
    return (QualityGate("REPRODUCIBILITY_MANIFEST", status, passed, len(expected_sha256), note),)


def _gate(gate_id: str, numerator: int, denominator: int, note: str) -> QualityGate:
    if denominator < 0 or numerator < 0 or numerator > denominator:
        raise ValueError(f"invalid counts for {gate_id}")
    if denominator == 0:
        return QualityGate(gate_id, "NOT_EVALUABLE", None, None, "No eligible items were supplied.")
    status = "PASS" if numerator == denominator else "FAIL"
    return QualityGate(gate_id, status, numerator, denominator, note)
