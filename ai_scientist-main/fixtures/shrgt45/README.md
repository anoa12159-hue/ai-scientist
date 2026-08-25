# fixtures/shrgt45/ — SHRGT45 Fixture（T003 已导入）

本目录是 D-005 批准白名单的只读 Fixture 快照，总范围 **171 文件、9,725,849 B**。
来源资料库只读（身份与 `origin_path` 见 `import-audit.json`）；所有文件作为不可变来源
字节复制，未执行任何历史脚本、未解压任何嵌套 ZIP、未读取或复制 `.env` / 密钥 / `.venv`。

## 布局

```text
assets/                  S01–S03、S05–S07 的 38 个逐文件 INCLUDE_COPY（逻辑 ID 见 manifest.json）
packages/0808/           S04 完整权威来源包（90 成员）—— provenance / 审计专用
packages/0814/           S04 Demo 运行投影（43 成员）—— 默认 S04 运行输入
manifest.json            171 个完整 SourceAssetRef（含 content_hash / source_version / 来源日期 /
                         角色 / provenance_status / usage_boundary）；两个完整 SourcePackageRef
                         （member_asset_refs 精确绑定 90 / 43）；包级与 37 条成员 DERIVED_FROM 版本化血缘
case-manifest.json       ReplayCaseManifest（stage_asset_refs / included_asset_refs 全 VersionedRef；
                         Included 171、Excluded 真实路径、10 个 DeclaredFindingSpec、acceptance profile）
import-audit.json        导入审计（计数 / tree hash / 血缘 / 来源日期精度 / Gap 声明）
```

`content_hash` 一律按 RFC8785 JCS 计算，与原始文件字节 `asset_sha256` 严格区分。

## 两个原子包

| 包 | 角色 | 成员 | 字节 | tree hash | 运行边界 |
|---|---|---:|---:|---|---|
| 0808 | `AUTHORITATIVE_COMPLETE_SOURCE_PACKAGE` | 90 | 3,818,486 | `a45e7775…` | provenance/审计专用 |
| 0814 | `DERIVED_RUNTIME_FIXTURE_PROJECTION` | 43 | 1,284,797 | `e5779518…` | 默认 S04 运行输入 |

- 0814 由 37 个与 0808 字节相同的映射成员 + 6 个本地组织/完整性文件组成；
- 37 个映射成员保留两个独立 `SourceAssetRef`、两个包成员身份和显式 `DERIVED_FROM` 血缘，
  不跨包合并去重。

## 已知缺口

`S04_0808_PACKAGE_INTEGRITY_REFERENCES_MISSING_FROM_TRANSFER`：0808 声称的包级
`file_sha256_manifest.csv` 与外层 ZIP 未随移交提供。0808 内容完整性按 manifest 文件集
为 `VERIFIED`，原作者包签名证据为 `PARTIAL`，37 文件派生血缘为 `VERIFIED`。

## 边界

- 未知路径、缺失成员、哈希不匹配、Manifest 不一致 → **Fail Closed**；
- `scientific_verdict=NOT_EVALUATED`、`result_maturity=DEVELOPMENTAL`、`authorization_status=NOT_AUTHORIZED`；
- 导入不代表历史统计结果经过正式验证。
