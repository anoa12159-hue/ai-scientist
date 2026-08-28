# TASK-P6-07：天文研究工作台产品界面

> 状态：`COMPLETED`

## 目标

将以 Replay 审计为中心的技术页面改造成面向科研人员的天文工作台。用户可以浏览匿名化的 JW-SSD 四模态观测、查看 PNG/FITS 信息，并显式发起单样本 Qwen-VL 五分类分析；历史 Replay 与治理信息降级为系统审计信息，不作为主产品流程。

## 安全与科学边界

- 推理 API 不返回、搜索或展示官方标签，公开样本编号不得包含类别。
- 单次仅分析一个样本，不提供 195 条批量入口。
- 模型输出是开发性 AI 判读，不代表正式科学结论或发布授权。
- 不修改冻结契约、Fixture、治理记录或既有 Replay Artifact。
- API Key 仅由现有本地 `.env` 运行时读取，不进入前端、日志或响应。

## Allowed changes

- `src/ai_scientist_mvp/api/workbench.py`
- `src/ai_scientist_mvp/api/server.py`
- `src/ai_scientist_mvp/api/__init__.py`
- `src/ai_scientist_mvp/workflow/replay_web.py`
- `web/index.html`
- `web/app.js`
- `web/styles.css`
- `web/README.md`
- `tests/unit/test_workbench.py`
- `tests/unit/test_web_contract.py`
- `tests/smoke/test_project_structure.py`
- `tasks/TASK-P6-07.md`

## 验收

- 工作台可列出匿名观测并显示连续谱/磁图 PNG、FITS 摘要。
- 单样本分析使用异步任务状态，页面不会在网络调用期间表现为无反馈卡死。
- 标签隔离、路径安全、图片 MIME、任务状态和前端产品文案有自动测试。
- Ruff、mypy 和相关单元测试通过。

## 验证结果

- `tests/unit/test_workbench.py tests/unit/test_web_contract.py tests/unit/test_api.py`：5 passed。
- Ruff、mypy、Node 语法检查与 `git diff --check`：通过。
- 服务器验收：195 条匿名观测、首条 FITS 摘要、真实 PNG 和静态页面均返回成功。
- 未代替用户调用 Qwen；真实单样本模型效果由工作台按钮手动验收。
