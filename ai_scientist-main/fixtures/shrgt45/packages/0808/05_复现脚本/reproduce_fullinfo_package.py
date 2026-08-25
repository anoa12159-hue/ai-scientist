from __future__ import annotations

import csv
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
RESULT_DIR = PACKAGE_ROOT / "03_结果数据"


def read(name: str) -> list[dict[str, str]]:
    with (RESULT_DIR / name).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    final_rows = read("10_final_analysis_sample.csv")
    audit = read("11_final_control_audit.csv")
    replacements = read("12_final_control_replacements.csv")
    gates = {row["gate"]: row["count"] for row in read("04_gate_counts.csv")}
    positive = [row for row in final_rows if row.get("sample_state") == "POSITIVE_CANDIDATE"]
    controls = [row for row in final_rows if row.get("sample_state") == "NEGATIVE_CANDIDATE"]
    checks = {
        "final_rows": len(final_rows) == 55,
        "positive_rows": len(positive) == 37,
        "control_rows": len(controls) == 18,
        "excluded_controls": sum(row.get("disposition") == "EXCLUDED_FUTURE6H_MPLUS" for row in audit) == 36,
        "retained_controls": sum(row.get("disposition") == "RETAINED_FINAL_CONTROL" for row in audit) == 15,
        "replacement_rows": len(replacements) == 3,
        "gate_final_rows": gates.get("final_analysis_rows") == "55",
        "gate_final_controls": gates.get("final_control_rows_after_mplus_screen") == "18",
        "no_mplus_on_final_controls": all(not row.get("full_mplus_future6h_ids") for row in controls),
    }
    for name, passed in checks.items():
        print(f"{name}={'PASS' if passed else 'FAIL'}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
