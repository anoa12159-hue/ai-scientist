# TASK-P6-01：RunReadModel 查询 API

> 状态：`COMPLETED`

实现系统无关的只读 API：Run、Stage、Artifact、Finding、报告和审核查询，以及冻结 D-006 `RunReadModel` 聚合。API 不执行科学计算、不修改 Artifact/Ledger、不泄露绝对路径或密钥。

实现：`api/read_model.py` 与 `api/server.py`；支持 `/health`、`/runs/{run_id}/read-model`、`stages`、`artifacts`、`findings`、`reviews` 和单 Artifact 详情；写请求明确返回只读错误。验证：`tests/unit/test_api.py` 2 passed，Ruff/mypy 通过。
