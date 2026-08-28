# web/

`web/` 是 HelioScope 太阳活动区智能研究工作台的无构建依赖静态前端。

- 主界面浏览匿名化 JW-SSD 观测，展示连续谱 PNG、磁图 PNG、两类 FITS 数值摘要，
  并可显式启动单样本 Qwen-VL 五分类分析。
- 官方标签不进入目录、详情、图片或模型请求；工作台仅使用 `OBS-xxxx` 公开编号。
- Replay、Artifact 和治理记录属于后台审计能力，不作为科研人员的主操作流程。
- 使用浏览器原生 Fetch，无 Node/npm 构建依赖。将本目录作为静态文件服务，并将 API 地址填写为 `ai_scientist_mvp.api.server` 的地址。

启动 API：

```bash
python -m ai_scientist_mvp.api.server \
  --runs-root /path/to/runs --run-id <run-id> \
  --archive /path/to/SHRGT45_官方五分类四模态扩展样本_20260826.zip \
  --qwen-config config.qwen_jwssd.toml --env-file .env
```

工作台接口：`GET /workbench/catalog`、`GET /workbench/observations/<id>`、
`GET /workbench/observations/<id>/images/<channel>`、`POST /workbench/analyses` 和
`GET /workbench/jobs/<job-id>`。单样本分析是异步任务，不提供批量按钮。

然后用任意静态文件服务器打开 `index.html`；浏览器验收需要在具备浏览器运行时的环境执行。
