# TASK-003-CORRECTION-1：Fixture Manifest 引用与血缘修正

> 状态：`READY`（待实施）
>
> 所属阶段：T003 修正（治理登记，不实施）
>
> 授权人：`actor_id=project_owner_01`
>
> 独立复核结论：`T003_INDEPENDENT_REVIEW = CHANGES_REQUIRED`

## Goal

对 T003 Fixture Manifest 做引用、血缘与身份完整性修正：把 171 条索引升级为完整、
Schema 合法、content_hash 自洽的 `SourceAssetRef`；建立完整 `SourcePackageRef` 与可版本化
血缘；让 `ReplayCaseManifest` 全部使用 `VersionedRef`；补齐来源/时间/角色/边界等冻结语义
字段；并增加独立 Fail-Closed 测试。**本任务卡仅登记修正范围，不实施修正。**

## Why

T003 独立复核发现：当前 `manifest.json` 的资产条目不是完整 `SourceAssetRef`，包引用未精确
绑定成员，血缘使用裸路径而非版本化引用，`ReplayCaseManifest` 的 `stage_asset_refs` /
`included_asset_refs` 未使用 `VersionedRef`，Excluded 项存在伪路径，且缺少对 D-005 逐文件
身份与 Fail-Closed 边界的独立测试。必须修正后再进入 T003 正式关闭。

## Depends on

- 当前 HEAD `f32f53edd33f8d434881e96429cc243d07393041`（T003 初始实现）；
- 冻结 baseline content_hash `55F7F20CC02BBBF8A59823166CD16A256394048E28F5F7D7A24651D1C9E91047`；
- 冻结契约 `docs/contracts/CONTRACTS.md` 0.1.0 与 T002 JSON Schema（`source-asset-ref`、
  `source-package-ref`、`versioned-ref`、`lineage-edge`、`replay-case-manifest`）；
- `governance/decisions/source/D-005.fixture-whitelist.accepted.md` 与
  `D-005.fixture-whitelist.draft.md`（逐文件身份与包边界权威）。

## 唯一 Allowed change（本卡生成阶段）

```text
tasks/TASK-003-CORRECTION-1.md
```

## 修正范围冻结（实施阶段 Allowed implementation changes）

```text
fixtures/shrgt45/manifest.json
fixtures/shrgt45/case-manifest.json
fixtures/shrgt45/import-audit.json
fixtures/shrgt45/README.md
tests/fixtures/test_fixture_manifest.py
tests/smoke/test_project_structure.py
```

## Forbidden changes

- 不得修改 `contracts/**`、`docs/contracts/**`、`governance/**`、`governance/baseline.lock.json`、
  原始 Fixture 字节、`src/**` 或任何 T004 内容。
- 不得重写、格式化、重新生成或删除现有 171 个 `assets/` / `packages/` 历史字节。
- 不得 amend `f32f53e` 或任何既有提交。
- 不得创建 remote、push 或 PR。
- 不得关闭 T003、生成 T003 CompletionRecord、启动 T004。

## 必须修正的语义（15 条）

1. 保留现有 171 个 `assets/` / `packages/` 历史字节，禁止重写、格式化、重新生成或删除。
2. 将 171 条索引升级为完整、Schema 合法、content_hash 自洽的 `SourceAssetRef`。
3. 建立两个完整 `SourcePackageRef`；`member_asset_refs` 必须分别精确绑定 90 / 43 个
   `SourceAssetRef`。
4. 建立可版本化的包级血缘和 37 条成员 `DERIVED_FROM` 血缘；不得用裸路径代替引用。
5. `ReplayCaseManifest` 的 `stage_asset_refs` 和 `included_asset_refs` 必须全部使用
   `VersionedRef`：
   - `included_asset_refs` 精确覆盖 171 个 `SourceAssetRef`；
   - 默认 S04 阶段只含 0814 的 43 个资产；
   - 0808 只用于 provenance / audit。
6. 所有 `content_hash` 使用 RFC8785 JCS；不得把原始文件 SHA256 当作 `content_hash`。
7. 补齐 `source_version`、来源日期、`ingested_at`、`role`、`provenance_status`、
   `usage_boundary`；来源日期必须有证据并说明精度，不得伪造精确时间。
8. 补齐十个 `DeclaredFindingSpec` 的冻结语义字段和 `rationale_source_refs`。
9. 将 Excluded 项改为真实来源路径或明确目录边界，不得使用“S06 三张图”一类伪路径。
10. 增加独立测试：Schema 校验、所有 `content_hash`、引用闭合、171 精确路径集合、
    D-005 逐文件身份、包成员边界、未知路径、缺失文件、哈希变化、未知版本、包混用、
    0808 进入默认运行输入等 Fail-Closed 反例。
11. 显式授权 `tests/smoke/test_project_structure.py`，接受 `f32f53e` 中解除 Fixture
    占位断言的必要修改，但不得削弱其余 smoke guardrail。
12. Allowed implementation changes 仅限本节所列六个文件。
13. 不得修改 `contracts/**`、`docs/contracts/**`、`governance/**`、`baseline.lock.json`、
    原始 Fixture 字节、`src/**` 或任何 T004 内容。
14. 修正必须形成独立 commit，不 amend `f32f53e`。
15. 不关闭 T003，不生成 CompletionRecord，不启动 T004。

## Acceptance criteria（修正实施阶段）

1. `manifest.json` 中每条资产均为完整、Schema 合法、content_hash 自洽的 `SourceAssetRef`；
2. 两个 `SourcePackageRef.member_asset_refs` 分别精确绑定 90 / 43 个 `SourceAssetRef`；
3. 包级血缘与 37 条成员 `DERIVED_FROM` 血缘均为版本化引用，无裸路径；
4. `ReplayCaseManifest.included_asset_refs` 精确覆盖 171 个 `SourceAssetRef`；
   默认 S04 只含 0814 的 43 个资产；0808 只用于 provenance/audit；
5. 所有 `content_hash` 按 RFC8785 JCS 计算，与原始文件 SHA256 区分；
6. `source_version` / 来源日期（含精度说明）/ `ingested_at` / `role` / `provenance_status` /
   `usage_boundary` 已补齐且不伪造精确时间；
7. 十个 `DeclaredFindingSpec` 具备冻结语义字段与 `rationale_source_refs`；
8. Excluded 项均为真实来源路径或明确目录边界；
9. 独立测试覆盖 Schema 校验、content_hash、引用闭合、171 路径集合、D-005 逐文件身份、
   包成员边界，以及全部 Fail-Closed 反例；
10. smoke guardrail 除解除 Fixture 占位断言外不削弱；
11. 全部验证命令通过，baseline 0 failures。

## Verification commands

```powershell
python -m pytest tests/fixtures tests/smoke tests/contract -q
python -m ruff check .
python -m mypy src
python -c "import sys; sys.path.insert(0, 'src'); import ai_scientist_mvp"
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify_project.ps1
git diff --check
git status --short
git remote -v
```

## Stop conditions

- 需要修改冻结契约、governance、baseline、原始 Fixture 字节、`src/**` 或任何 T004 内容；
- 需要重写/格式化/重新生成 171 个历史字节；
- 需要伪造来源日期或补造无证据的来源身份；
- 需要联网、付费 API、密钥或破坏性数据操作。

## Handoff

修正实施完成时必须汇报：实际修改文件、SourceAssetRef/SourcePackageRef 引用闭合结果、
37 条血缘版本化结果、content_hash 自洽结果、来源日期精度说明、测试覆盖与 Fail-Closed 反例、
每条验证命令真实结果、baseline 复核、新 commit id、git status、remote 状态、未运行项目及原因。

## 当前实施状态

```text
CORRECTION_IMPLEMENTATION = NOT_STARTED
```
