# TASK-P6-02：RunReadModel 薄前端

> 状态：`COMPLETED`

新增无构建依赖的静态前端 `web/index.html`、`web/app.js`、`web/styles.css`。前端通过 Fetch 读取后端 `RunReadModel`，展示 Run、阶段、闸门、Artifact/Finding 数量和报告引用；不读取标签、不推导科学结论、不修改运行状态。

验证：`tests/unit/test_web_contract.py` 1 passed。
