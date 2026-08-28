# JW-SSD 五分类评测边界

当前评测唯一身份由外层 ZIP 文件名和 SHA256 共同确定：

```text
SHRGT45_官方五分类四模态扩展样本_20260826.zip
db07a1a05336597d3cba3717605057caa45b80f7365c3963ea9d662e6dda40d4
```

`audit_jwssd_archive` 只在内存中读取 ZIP，不解压、不执行成员。样本标签只能来自 ZIP 内的 `样本清单.csv`；四个成员必须同时存在：连续谱 FITS/PNG、磁图 FITS/PNG。类目录名和文件名只用于路径完整性校验，不能替代清单标签。

```python
from pathlib import Path
from ai_scientist_mvp.skills import audit_jwssd_archive

manifest = audit_jwssd_archive(
    Path("SHRGT45_官方五分类四模态扩展样本_20260826.zip"),
    expected_sha256="db07a1a05336597d3cba3717605057caa45b80f7365c3963ea9d662e6dda40d4",
    expected_sample_count=195,
)
```

训练/验证划分必须在 `HARPNUM` 组级完成，评测集标签由独立评测进程读取。五分类主指标为混淆矩阵、每类 Precision/Recall/F1、macro-F1、micro-F1 和 balanced accuracy；每类 Recall 使用 Wilson 95% 区间。该任务不定义耀斑正类，不生成 M1+ TSS/HSS。
