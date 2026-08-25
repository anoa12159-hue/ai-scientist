# contracts/

机器契约：JSON Schema 2020-12（T002 已实现）。

- 语义规范源是冻结的 `docs/contracts/CONTRACTS.md` 版本 0.1.0（只读）；
  实现清单见 `docs/contracts/SCHEMA_CATALOG.md`。
- 分组：
  - `shared/` 共享枚举、原语与版本化身份定义（`$defs`，经 `$ref` 复用，不得复制漂移）；
  - `foundation/`、`artifact-runtime/`、`validation-lineage-findings/`、
    `governance-release/`、`domain-query/` 五个分组，共 37 个 Schema。
- 内容身份采用 `RFC8785-JCS + UTF-8 + SHA256`，实现见
  `src/ai_scientist_mvp/domain/canonical_json.py`。
- Python 类型见 `src/ai_scientist_mvp/domain/types.py`，由
  `tests/contract/test_python_type_consistency.py` 证明与 Schema 无漂移。
- 契约测试入口：`tests/contract/`。
