from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
ZIP_PATH = PACKAGE_ROOT.parent / f"{PACKAGE_ROOT.name}.zip"
AUDIT = PACKAGE_ROOT / "06_审计与交付"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    files = [path for path in sorted(PACKAGE_ROOT.rglob("*")) if path.is_file() and path.name != "file_sha256_manifest.csv" and not path.name.startswith(".")]
    manifest = {
        "run_id": PACKAGE_ROOT.name,
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "result_report": "01_主报告/01_全信息基准版Demo结果报告_20260808.md",
        "final_analysis_sample": "03_结果数据/10_final_analysis_sample.csv",
        "formal_independent_control_count": 0,
        "files": [str(path.relative_to(PACKAGE_ROOT)).replace("\\", "/") for path in files],
    }
    AUDIT.mkdir(parents=True, exist_ok=True)
    (AUDIT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (AUDIT / "file_sha256_manifest.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        handle.write("relative_path,size_bytes,sha256\n")
        for path in files:
            handle.write(f"{str(path.relative_to(PACKAGE_ROOT)).replace('\\', '/')},{path.stat().st_size},{sha256(path)}\n")
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()
    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in [path for path in sorted(PACKAGE_ROOT.rglob("*")) if path.is_file() and not path.name.startswith(".") and path.name != "file_sha256_manifest.csv"]:
            archive.write(path, path.relative_to(PACKAGE_ROOT))
    (AUDIT / "zip_sha256.csv").write_text(f"file,bytes,sha256\n{ZIP_PATH.name},{ZIP_PATH.stat().st_size},{sha256(ZIP_PATH)}\n", encoding="utf-8")


if __name__ == "__main__":
    main()
