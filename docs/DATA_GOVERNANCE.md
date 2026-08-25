# 数据字典、外部资源与血缘边界

状态：`BASELINE_V1`  
日期：2026-08-25

## 1. 数据集登记

| 数据集 | 角色 | 当前状态 | 可用于 | 禁止用途 | 许可证/条款状态 |
|---|---|---|---|---|---|
| JW-FD 公开子集 | `OFFICIAL_BENCHMARK` | 尚未落盘 | Benchmark train/val/test、管道测试 | 用 test 标签训练/调参 | 未在当前材料中找到明确再分发许可证；提交前向组委会确认 |
| JW-FD 简略版 | `DEVELOPMENT_CALIBRATION` | 移交材料记录 9 个 AR | Schema、读取、切分和窗口 smoke test | M+ 正式验证、WCS/provenance 证明 | 同上 |
| SHRGT45 2026-08-14 Demo | `RESEARCH_REPLAY` | 移交压缩包内，55 条最终记录/4 AR | 离线 Replay、血缘与研究展示 | 独立训练样本、确认性因果结论 | 来源混合；每个成员按其来源条款处理，不整体再分发 |
| JSOC HMI SHARP | `EXTERNAL_SCIENCE_SOURCE` | 由查询获取 | SHARP 标量、时间序列、磁图 QA | 脱离查询键和 FITS 头的无来源使用 | 使用前记录 JSOC/SDO 数据政策与致谢版本 |
| NOAA/NCEI 事件目录 | `LABEL_SOURCE` | Demo 含目录子集 | M+ 事件标签与 control 审计 | 无快照/查询时间的标签生成 | 美国政府公开数据；仍需记录来源与访问日期 |
| JW-SSD | `AUXILIARY_DEVELOPMENT` | 外部下载项 | 形态、字段和多模态开发 | 直接作为耀斑标签或 12 分钟序列 | 未确认再分发许可证，默认不随源码发布 |
| deep_research_agent_v13 缓存 | `LITERATURE_SNAPSHOT` | 独立 zip | 离线检索回退、引用核验 | 将缓存全文公开再分发 | 逐论文核验版权；默认只发布元数据、哈希和允许的摘录 |

许可证状态为“未确认”的数据只能在受控开发区使用，不能进入公开仓库、镜像或最终源码包。

## 2. 核心数据字典

| 字段 | 类型/单位 | 含义 | 来源与质量门 |
|---|---|---|---|
| `image_filename` | string | JW-FD 样本唯一文件名 | 必须唯一、相对路径安全、与输出逐行对齐 |
| `AR` / `NOAA_AR` | string/int | NOAA 活动区标识 | 用于 split 隔离；缺失时不得随机拆分替代 |
| `HARPNUM` | int | HMI Active Region Patch 标识 | 来自 FITS/JSOC；与 NOAA_AR 映射需版本化 |
| `T0` / `T_REC` | UTC timestamp | 预测基准时刻/观测时刻 | 必须含时区并按真实时间排序 |
| `png_path` | relative path | 600×600 Th1000 派生图 | 必须位于 `data_root`，禁止绝对路径逃逸 |
| `fits_path` | relative path | 科学数值或派生 FITS | 校验头、shape、NaN、单位、WCS 和来源 |
| `SHRGT45` | percent | 面积加权磁场倾角大于 45° 的像素比例 | 公式/别名由参数注册表校验；不得由 PNG 视觉值冒充 |
| `USFLUX` | Mx | 总无符号磁通量 | 用作背景/基线控制，记录产品系列与单位 |
| `QUALITY` | bit mask | HMI 质量标记 | 排除冻结的致命位；`QUALITY=0` 作为敏感性线 |
| `flare_label_M1.0_24hr` | 0/1 | T0 后累计 24h 是否有 ≥M1.0 耀斑 | 仅评测组件可在 test 上读取 |
| `flare_label_M1.0_3hr/6hr` | 0/1 | 累计窗口标签 | 不得直接静默转换为非重叠 3–6h 标签 |
| `probability` | float [0,1] | 预测正类概率 | 有限值、范围校验 |
| `prediction` | int {0,1} | 冻结阈值后的类别 | 阈值必须来自 val 配置 |

## 3. 外部服务与许可证清单

| 资源 | 用途 | 发布边界 |
|---|---|---|
| 阿里云百炼/Qwen | 结构化推理 | 不发布密钥；记录模型 ID、调用日期和 token |
| Semantic Scholar API | 论文搜索与引用链 | 遵守 API 条款和限流；缓存元数据保留来源时间 |
| Crossref/OpenAlex/arXiv | DOI、元数据、开放全文定位 | 分别保留来源和许可字段；开放元数据不等于全文可再分发 |
| DuckDuckGo/网页搜索 | 候选来源发现 | 仅保存必要元数据和允许摘录，不把搜索结果当最终证据 |
| PyPI 依赖 | 运行环境 | 最终生成锁定版本和第三方许可证清单 |

## 4. 血缘边界

```text
immutable source bytes / API response
  -> SourceArtifact (source URI, retrieval time, SHA256, license status)
  -> normalized manifest (sample id, AR, T0, modality)
  -> validated feature/label artifact (code/config hash, quality report)
  -> split-scoped model input (train | val | unlabeled test)
  -> prediction artifact
  -> metrics artifact（仅独立评测进程可连接标签）
  -> finding/report（引用上游 artifact id，不复制改写来源）
```

强制边界：

- 原始字节只读；任何解压、转码、裁剪和特征计算都产生新 Artifact。
- `infer_batch` 的进程权限和参数中不存在标签路径；指标计算是独立入口。
- 论文声明必须绑定来源、逐字引文和位置；无法逐字验证时为 `NOT_FOUND`。
- 科学不支持、证据不足、数据缺失和程序失败使用不同状态。
- Checkpoint 保存 Artifact 引用和哈希，不保存大段来源正文。
- 未知许可证、来源不明、哈希不匹配或 split 泄漏立即阻断发布链。

## 5. 发布前待办

- 获取 JW-FD/JW-SSD 的明确许可或组委会书面再分发边界。
- 下载后生成文件级 manifest、SHA256、行数、AR 分布和标签阳性率报告。
- 为 JSOC、NCEI 和每个论文快照补齐访问日期、查询参数和许可字段。
- 从最终锁文件生成第三方 Python/前端许可证清单。
