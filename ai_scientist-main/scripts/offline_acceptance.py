"""Run the no-network, no-secret acceptance checks for the local MVP."""
from __future__ import annotations

import argparse
from pathlib import Path

from ai_scientist_mvp.quality import audit_reproducibility_manifest
from ai_scientist_mvp.skills import audit_four_modality_sample, audit_inference_source_isolation

EXPECTED_ARCHIVE_SHA256 = "db07a1a05336597d3cba3717605057caa45b80f7365c3963ea9d662e6dda40d4"


def run(archive: Path, project_root: Path) -> dict[str, object]:
    manifest_checks = audit_four_modality_sample(
        archive,
        "JWSSD_alpha_HARP7211_20171228_000000_TAI",
        expected_sha256=EXPECTED_ARCHIVE_SHA256,
    )
    isolation = audit_inference_source_isolation(project_root / "src" / "infer_batch.py")
    files = audit_reproducibility_manifest(
        project_root,
        {
            "config.qwen_jwssd.toml": (
                "5b63ddd78c0813ad8833adc584daf9a3bcf453b964a3c50c13047dae6a1e9be1"
            ),
            "src/infer_batch.py": (
                "5ec897f14261344754d8c1edc7940d9838d621e15a09261701fd1b941ce44a9e"
            ),
            "src/evaluate_jwssd.py": (
                "d143cbd5e05385e24050076be5a69b3319a21bc13e7620338b9d0981e961b114"
            ),
        },
    )
    if any(check.status != "PASS" for check in manifest_checks) or files[0].status != "PASS":
        raise RuntimeError("offline acceptance failed")
    return {
        "qa_checks": len(manifest_checks),
        "isolation_checks": list(isolation),
        "manifest": files[0].status,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run offline MVP acceptance checks")
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    result = run(args.archive, args.project_root)
    print(result)


if __name__ == "__main__":
    main()
