# TASK-003：SHRGT45 Fixture Manifest

> 状态：`READY`
>
> 所属阶段：T003

## Goal

按 D-003 策略和 D-005 批准白名单，导入或引用精选历史资产，生成逐文件 Fixture Manifest、
快照与导入审计，并对缺失项和已知边界做显式登记。本任务只建立 Fixture 边界与审计身份，
不实现任何运行时内核。

## Why

后续 ArtifactStore、Replay Adapter、LangGraph 工作流都需要一个可哈希、可追溯、Fail Closed
的 Fixture 边界。在写入运行时代码前，必须先机械化 D-005 批准的精确逻辑范围（171 文件、
9,725,849 B），否则无法对来源身份做确定性校验。

## Depends on

- T002 `COMPLETED`：`governance/completions/TASK-002.completion.json`（ACCEPTED）
- `governance/baseline.lock.json` content_hash：`55F7F20CC02BBBF8A59823166CD16A256394048E28F5F7D7A24651D1C9E91047`
- 冻结契约 `docs/contracts/CONTRACTS.md` 版本 `0.1.0`（SourceAssetRef / SourcePackageRef / ReplayCaseManifest）
- D-003（精选只读快照策略）、D-005（批准白名单与 0808/0814 血缘）

## Inputs（只读）

- `governance/baseline.lock.json`
- `governance/decisions/source/D-005.fixture-whitelist.accepted.md`
- `docs/contracts/CONTRACTS.md`
- `contracts/foundation/{source-asset-ref,source-package-ref,replay-case-manifest}.schema.json`
- 源资料库 `D:\桌面\揭榜-移交版`（只读）

## 数据与安全边界

- 源资料 `D:\桌面\揭榜-移交版` **只读**：不开发、不清理、不覆盖。
- 不执行任何历史脚本、Notebook、可执行文件；不解压任何嵌套 ZIP。
- 不读取、复制或提交 `.env`、密钥、`.venv`、缓存。
- 默认运行输入只用 **0814**（43 成员 Demo 运行投影）；**0808**（90 成员完整权威来源包）只用于 provenance/完整性审计。
- 未知路径、缺失必需成员、哈希变化、Manifest 不一致必须 **Fail Closed**。

## Allowed changes

```text
fixtures/shrgt45/     （case-manifest.*、逐文件 Manifest、快照索引、导入审计报告）
tests/fixtures/       （Fixture Manifest 与哈希/血缘/边界测试）
```

## Forbidden changes

- 不得修改 `AGENTS.md`、`governance/**`、`docs/contracts/**`、`docs/adr/**`、`tasks/**`、`contracts/**`。
- 不得修改 `src/**`（ArtifactStore、Ledger、Checkpoint 属 T004；Provider/Adapter 属 T005）。
- 不得实现 LangGraph 节点、API、前端、数据库、在线模型或 JSOC。
- 不得执行历史脚本、Notebook 或可执行文件，不得解压嵌套 ZIP。
- 不得读取或复制 `.env`、密钥、`.venv`。
- 不得把机器绝对路径写入 Python、配置、CI 或测试。
- 不得修改源资料库 `D:\桌面\揭榜-移交版`。

## Required outputs

- `fixtures/shrgt45/case-manifest.*`：逻辑资产 ID、相对路径、原来源、版本、日期、字节数与 SHA256；
- Included / Excluded 清单（Excluded 内嵌审计项，不被运行读取）；
- S04 两个独立 `SourcePackageRef`：
  - 0808 = `AUTHORITATIVE_COMPLETE_SOURCE_PACKAGE`，90 成员，3,818,486 B；
  - 0814 = `DERIVED_RUNTIME_FIXTURE_PROJECTION`，43 成员，1,284,797 B；
- 两包独立身份 + 显式血缘（`0814 DERIVED_FROM 0808` / `0808 SOURCE_OF 0814`）；
- 37 条已核对 `DERIVED_FROM` 血缘：字节相同的映射成员保留两个 `SourceAssetRef`、
  两个包成员身份和显式 lineage edge，不得跨包合并去重；
- 0814 的 6 个本地组织/完整性成员（无虚构 0808 父文件）显式登记；
- 两个导入审计 tree hash（规范化相对路径 + 字节数 + SHA256，ordinal 排序后 SHA256）；
- `S04_0808_PACKAGE_INTEGRITY_REFERENCES_MISSING_FROM_TRANSFER` 声明（缺失原作者包级
  `file_sha256_manifest.csv` 与外层 ZIP）；
- Manifest 中的 S01 专家预选种子 Gap 声明（运行时 Finding 由后续 Adapter/Graph 生成）；
- 导入审计报告；
- D-005 批准白名单的逐文件机械化。

## Acceptance criteria

1. 总范围精确为 **171 文件、9,725,849 B**（D-005 冻结值），任何偏差 Fail Closed。
2. 0808 = 90 成员、0814 = 43 成员，两包独立 `SourcePackageRef` 且血缘显式。
3. 37 条 DERIVED_FROM 血缘已核对，映射成员不跨包去重。
4. 哈希变化、缺失必需成员、未知路径、Manifest 不一致时 Fail Closed。
5. 默认运行输入只含 0814；0808 仅 provenance/审计展开。
6. 不执行脚本、不解压 ZIP、不读取 `.env`、不复制 `.venv`、不修改源资料。
7. 契约测试（fixture 哈希、血缘、边界）通过；smoke/contract 不回归。

## Verification commands

在项目根目录执行：

```powershell
python -m pytest tests/fixtures tests/smoke tests/contract -q
python -m ruff check .
python -m mypy src
python -c "import sys; sys.path.insert(0, 'src'); import ai_scientist_mvp"
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify_project.ps1
git diff --check
git status --short
```

## Stop conditions

- 所需 Fixture 缺失、变更、损坏或身份未知；
- 总范围与 171 文件 / 9,725,849 B 或 0808/0814 成员数不一致；
- 需要联网、付费 API、密钥或破坏性数据操作；
- 需要执行历史脚本、解压嵌套 ZIP、或修改源资料库才能完成；
- 需要修改冻结契约、governance 或 T002 CompletionRecord 才能通过；
- 需要提前实现 T004+ 运行时内容。

## Handoff

完成时必须汇报：实际新增/修改文件、逐文件 Manifest 覆盖、0808/0814 包与血缘核对、
导入审计 tree hash、已知缺口、每条验证命令真实结果、未运行检查及原因、T004 是否具备开始条件。
