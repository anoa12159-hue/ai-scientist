# JW-SSD Pilot 复现清单

本清单只覆盖 1–4 条 pilot，不授权或执行 195 条批量评测。正式发布前必须在代码冻结后补充最终 commit hash；当前工作区仍可能有未提交变更。

## 固定输入

- Archive：`SHRGT45_官方五分类四模态扩展样本_20260826.zip`
- Archive SHA256：`db07a1a05336597d3cba3717605057caa45b80f7365c3963ea9d662e6dda40d4`
- 类别：`alpha`、`beta`、`beta-delta`、`beta-gamma`、`beta-gamma-delta`
- 推理只使用 `load_unlabeled_jwssd_samples`、四模态文件和 FITS 数值摘要；标签由独立评测进程读取。

## 固定实现身份

| 文件 | SHA256 |
|---|---|
| `config.qwen_jwssd.toml` | `5b63ddd78c0813ad8833adc584daf9a3bcf453b964a3c50c13047dae6a1e9be1` |
| `src/infer_batch.py` | `5ec897f14261344754d8c1edc7940d9838d621e15a09261701fd1b941ce44a9e` |
| `src/evaluate_jwssd.py` | `d143cbd5e05385e24050076be5a69b3319a21bc13e7620338b9d0981e961b114` |
| `src/ai_scientist_mvp/skills/jwssd_evaluation.py` | `3b5d76c4db10d5b83a730f6aa3e76bd521f4f081696d953e5f995393e9204900` |
| `pyproject.toml` | `aa7845b4cef81f2a2a3d367df6d76e3a7b5afebeef5911798b8abf75b8e2a2e0` |
| `src/ai_scientist_mvp/quality/gates.py` | `bcc0fe0a0cc2c82884f4d51dab8a42bca77de817423f4642b42568cc7a342f64` |
| `src/ai_scientist_mvp/api/read_model.py` | `288b3fc96f92fefff2c53575fa32dee8bd2e7ebf2c872ab052a3a27117082baa` |
| `src/ai_scientist_mvp/api/server.py` | `a260ffbd9c040acb62a7a3b12155f6e56a90f9cc22f971043279e8c4d24995cf` |
| `web/index.html` | `b73c290d99eb55de8ed3aca659bfad58f572f820216e02fb0fca883bff5b1c7c` |
| `web/app.js` | `aab4363c5b2fdb850c3ff58ca8e99bdda39572ed432fd7da418cd10b997e4adc` |
| `web/styles.css` | `5071677bb614cc9054012f31c9b281ef938cdb1429b4196665d2d60bb93643d5` |
| `scripts/offline_acceptance.py` | `ecdf1572095db25d34ca2506b95464c55283aa9d3f613effe3315b0b80fdcb4e` |

当前 Prompt（`src/infer_batch.py::_QWEN_PROMPT`）的 canonical 内容哈希：
`07B67947C2492D01D464BE792B0CF9F18A60DE7D76177C86E4BA001E13EEA878`

当前基线 commit：`b350a9d173239c7420a1ec885f17a74980aedc9e`。由于工作区尚未冻结，不能把它宣称为最终复现 commit。

## 运行边界

- 模型：`qwen-vl-max`，temperature `0`，seed `42`，单请求超时 `180s`。
- 重试：最多 `3` 次，指数退避上限 `16s`，最小间隔 `0.2s`。
- pilot 入口强制 `--limit 1..4`；195 条批量评测列为最后一步，须项目负责人明确授权。
- 结果必须同时保存预测 CSV、独立指标 JSON、四模态 QA Artifact 和 `JWSSDPilotAudit` 血缘。
