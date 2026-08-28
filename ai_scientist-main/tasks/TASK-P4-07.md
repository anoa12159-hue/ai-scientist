# TASK-P4-07：JW-SSD 四模态输入 QA

> 状态：`DONE`

`audit_four_modality_sample` 对单个样本的连续谱/磁图 FITS 与 PNG 执行签名、维度、有限值和配对一致性检查，作为视觉证据生成前的质量门。`create_visual_evidence_artifact` 通过标签盲读入 ZIP 四个成员，分别写入不可变 `SourceDocument`，再写入带四个父引用的 `MagnetogramQASnapshot`；内容哈希、来源成员哈希和 QA 范围说明均可复核。它不改写原始文件，也不启动批量推理。

验证：`tests/unit/test_jwssd_evaluation.py` 10 passed；Ruff 与 mypy 通过；真实冻结样本 `JWSSD_alpha_HARP7211_20171228_000000_TAI` 通过 QA 和 ArtifactStore 幂等复核。
