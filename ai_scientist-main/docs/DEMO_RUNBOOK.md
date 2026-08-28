# 本地演示 Runbook

1. 使用已配置的 Python 环境运行离线检查：

   `python scripts/offline_acceptance.py --archive /path/to/SHRGT45_官方五分类四模态扩展样本_20260826.zip`

2. 启动 Replay 演示 API（会在本地 Run 目录写入回放 Artifact）：

   `python -m ai_scientist_mvp.api.server --runs-root /path/to/runs --run-id <run-id>`

3. 用任意静态文件服务器打开 `web/index.html`，填写 API 地址和 Run ID，点击“启动回放”，
   等待 `FIXTURE_IMPORT_REVIEW` 闸门后点击“通过导入闸门”。

4. Pilot 流程使用 `src/infer_batch.py --mode qwen --limit 1..4`，再用独立 `src/evaluate_jwssd.py` 评测；不要省略 `--limit`，也不要在未授权时使用 `--confirm-batch`。

API 和前端展示版本化引用、阶段、闸门、Artifact/Finding 和报告状态；不在浏览器中拼接科学结论。
