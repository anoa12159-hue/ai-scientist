"""Offline, fail-closed SHRGT45 Replay adapters."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from ai_scientist_mvp.application.ports import ArtifactStore
from ai_scientist_mvp.application.services import compute_authority_hash
from ai_scientist_mvp.domain import canonical_json
from ai_scientist_mvp.domain.errors import LedgerIntegrityError
from ai_scientist_mvp.domain.types import (
    ArtifactEnvelope,
    ArtifactRef,
    CandidateSnapshot,
    CounterexampleSnapshot,
    HypothesisSnapshot,
    MagnetogramQASnapshot,
    MechanismSnapshot,
    SourceAssetRef,
    VerificationSnapshot,
    VersionedRef,
)
from ai_scientist_mvp.infrastructure.contract_validation import (
    ContractValidator,
    default_contracts_root,
)

_FIXED_TS = "2026-08-20T00:00:00Z"
_SCHEMA_VERSION = "0.1.0"
_PRODUCER = {"id": "replay-adapter", "version": "0.1.0"}
_FIXTURE_FILE_COUNT = 171
_FIXTURE_TOTAL_BYTES = 9_725_849
_PACKAGE_IDENTITY = {
    "0808": (90, 3_818_486, "a45e77758ca59d98a7fb333326f5463177ad62944376a95c4880230595e6c032"),
    "0814": (43, 1_284_797, "e577951858466b40cc001627ef27185267d9ed63e249f6ef78b500723d9c47dc"),
}


def _artifact_id(run_id: str, kind: str, logical_key: str) -> str:
    digest = hashlib.sha256(logical_key.encode("utf-8")).hexdigest()[:20]
    return f"{run_id}-{kind}-{digest}"


def _versioned_ref(obj: Mapping[str, Any], id_field: str) -> VersionedRef:
    return {
        "id": obj[id_field],
        "schema_version": obj["schema_version"],
        "content_hash": obj["content_hash"],
    }


def _assert_content_hash(obj: Mapping[str, Any], label: str) -> None:
    actual = canonical_json.content_hash_excluding(dict(obj))
    if actual != obj.get("content_hash"):
        raise LedgerIntegrityError(f"{label} content_hash mismatch")


def _is_link_like(path: Path) -> bool:
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


class ManifestAssetCatalog:
    """Preflight all frozen fixture identities before a Run can write an Artifact."""

    def __init__(self, fixtures_root: Path) -> None:
        self.fixtures_root = Path(fixtures_root).resolve()
        self.project_root = self.fixtures_root.parent.parent.resolve()
        self.contracts = ContractValidator(default_contracts_root())
        self.manifest: dict[str, Any] = {}
        self.case_manifest: dict[str, Any] = {}
        self.import_audit: dict[str, Any] = {}
        self._assets: dict[str, SourceAssetRef] = {}
        self._packages: dict[str, dict[str, Any]] = {}
        self._stage_refs: dict[str, list[VersionedRef]] = {}

    def load(self) -> None:
        manifest = self._read_json("manifest.json")
        case = self._read_json("case-manifest.json")
        audit = self._read_json("import-audit.json")
        for label, obj in (("manifest", manifest), ("import audit", audit)):
            if obj.get("schema_version") != _SCHEMA_VERSION:
                raise LedgerIntegrityError(f"unsupported {label} schema_version")
        self.contracts.validate("replay-case-manifest", case)
        _assert_content_hash(case, "ReplayCaseManifest")
        _assert_content_hash(audit, "import audit")

        raw_assets = manifest.get("source_assets")
        raw_packages = manifest.get("source_packages")
        if not isinstance(raw_assets, list) or not isinstance(raw_packages, dict):
            raise LedgerIntegrityError("manifest source_assets/source_packages shape mismatch")
        asset_ids = [item.get("asset_id") for item in raw_assets if isinstance(item, dict)]
        if len(asset_ids) != len(raw_assets) or len(set(asset_ids)) != len(asset_ids):
            raise LedgerIntegrityError("manifest contains missing or duplicate asset_id")
        assets = {item["asset_id"]: cast(SourceAssetRef, item) for item in raw_assets}

        for asset_id, asset in assets.items():
            self.contracts.validate("source-asset-ref", asset)
            _assert_content_hash(asset, f"SourceAssetRef {asset_id}")
            self._verify_source_bytes(asset)
        if len(assets) != _FIXTURE_FILE_COUNT:
            raise LedgerIntegrityError("manifest must contain exactly 171 SourceAssetRefs")
        if manifest.get("logical_file_count") != len(assets):
            raise LedgerIntegrityError("manifest logical_file_count mismatch")
        actual_total_bytes = sum(a["byte_size"] for a in assets.values())
        if actual_total_bytes != _FIXTURE_TOTAL_BYTES:
            raise LedgerIntegrityError("manifest frozen total byte count mismatch")
        if manifest.get("logical_total_bytes") != actual_total_bytes:
            raise LedgerIntegrityError("manifest logical_total_bytes mismatch")

        packages: dict[str, dict[str, Any]] = {}
        for package_key, package in raw_packages.items():
            if not isinstance(package, dict):
                raise LedgerIntegrityError(f"package {package_key} is not an object")
            self.contracts.validate("source-package-ref", package)
            _assert_content_hash(package, f"SourcePackageRef {package_key}")
            self._verify_package(package_key, package, assets)
            packages[package_key] = package
        if set(packages) != {"0808", "0814"}:
            raise LedgerIntegrityError("manifest must contain exactly the 0808 and 0814 packages")

        objects: dict[str, Mapping[str, Any]] = {**assets}
        for package in packages.values():
            package_id = package["package_id"]
            if package_id in objects:
                raise LedgerIntegrityError(f"duplicate versioned identity: {package_id}")
            objects[package_id] = package
        self._verify_manifest_references(manifest, case, audit, objects, packages, assets)

        self.manifest = manifest
        self.case_manifest = case
        self.import_audit = audit
        self._assets = assets
        self._packages = packages
        self._stage_refs = {
            stage: cast(list[VersionedRef], refs)
            for stage, refs in case["stage_asset_refs"].items()
        }

    def _read_json(self, name: str) -> dict[str, Any]:
        path = self.fixtures_root / name
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise LedgerIntegrityError(f"invalid fixture JSON: {name}") from exc
        if not isinstance(value, dict):
            raise LedgerIntegrityError(f"fixture JSON must be an object: {name}")
        return value

    def _safe_path(self, repository_relative_path: str, *, directory: bool = False) -> Path:
        raw = Path(repository_relative_path)
        if raw.is_absolute() or any(part in {".", ".."} for part in raw.parts):
            raise LedgerIntegrityError("runtime fixture path must be repository-relative")
        lexical_path = self.project_root / raw
        try:
            lexical_path.relative_to(self.fixtures_root)
        except ValueError as exc:
            raise LedgerIntegrityError(f"fixture path escapes frozen root: {raw}") from exc
        cursor = self.project_root
        for part in raw.parts:
            cursor = cursor / part
            if cursor.exists() and _is_link_like(cursor):
                raise LedgerIntegrityError(f"fixture path traverses link/junction: {raw}")
        path = lexical_path.resolve(strict=False)
        try:
            path.relative_to(self.fixtures_root)
        except ValueError as exc:
            raise LedgerIntegrityError(f"fixture path escapes frozen root: {raw}") from exc
        if directory and not path.is_dir():
            raise LedgerIntegrityError(f"fixture package directory missing: {raw}")
        if not directory and not path.is_file():
            raise LedgerIntegrityError(f"fixture source missing: {raw}")
        return path

    def _verify_source_bytes(self, asset: SourceAssetRef) -> None:
        path = self._safe_path(asset["repository_relative_path"])
        data = path.read_bytes()
        if len(data) != asset["byte_size"]:
            raise LedgerIntegrityError(f"source byte_size drift: {asset['asset_id']}")
        if hashlib.sha256(data).hexdigest().lower() != asset["asset_sha256"].lower():
            raise LedgerIntegrityError(f"source SHA256 drift: {asset['asset_id']}")

    def _verify_package(
        self, package_key: str, package: dict[str, Any], assets: dict[str, SourceAssetRef]
    ) -> None:
        self._safe_path(package["repository_relative_root"], directory=True)
        refs = package["member_asset_refs"]
        ids = [ref.get("id") for ref in refs]
        expected_count, expected_bytes, expected_tree_hash = _PACKAGE_IDENTITY[package_key]
        if package["member_count"] != expected_count:
            raise LedgerIntegrityError(f"package {package_key} frozen member count mismatch")
        if package["total_bytes"] != expected_bytes:
            raise LedgerIntegrityError(f"package {package_key} frozen byte count mismatch")
        if package["tree_hash"].lower() != expected_tree_hash:
            raise LedgerIntegrityError(f"package {package_key} frozen tree hash mismatch")
        if len(ids) != len(set(ids)) or len(ids) != package["member_count"]:
            raise LedgerIntegrityError(f"package {package_key} member identity/count mismatch")
        prefix = f"s04.{'source0808' if package_key == '0808' else 'demo0814'}::"
        expected = {asset_id for asset_id in assets if asset_id.startswith(prefix)}
        if set(ids) != expected:
            raise LedgerIntegrityError(f"package {package_key} member set mismatch")
        if sum(assets[asset_id]["byte_size"] for asset_id in ids) != package["total_bytes"]:
            raise LedgerIntegrityError(f"package {package_key} total_bytes mismatch")
        tree_entries: list[str] = []
        package_root = Path(package["repository_relative_root"])
        for asset_id in ids:
            asset = assets[asset_id]
            member_path = Path(asset["repository_relative_path"]).relative_to(package_root)
            tree_entries.append(
                f"{member_path.as_posix()}\t{asset['byte_size']}\t{asset['asset_sha256'].lower()}\n"
            )
        tree_hash = hashlib.sha256("".join(sorted(tree_entries)).encode("utf-8")).hexdigest()
        if tree_hash != package["tree_hash"].lower():
            raise LedgerIntegrityError(f"package {package_key} computed tree hash mismatch")
        for index, ref in enumerate(refs):
            self._resolve_object_ref(ref, assets, f"{package_key}.member_asset_refs[{index}]")

    @staticmethod
    def _resolve_object_ref(
        ref: object, objects: Mapping[str, Mapping[str, Any]], location: str
    ) -> Mapping[str, Any]:
        if not isinstance(ref, dict) or set(ref) != {"id", "schema_version", "content_hash"}:
            raise LedgerIntegrityError(f"malformed VersionedRef at {location}")
        target = objects.get(ref["id"])
        if target is None:
            raise LedgerIntegrityError(f"unresolved VersionedRef at {location}: {ref['id']}")
        if ref["schema_version"] != target["schema_version"]:
            raise LedgerIntegrityError(f"stale schema_version at {location}")
        if ref["content_hash"] != target["content_hash"]:
            raise LedgerIntegrityError(f"stale content_hash at {location}")
        return target

    def _verify_manifest_references(
        self,
        manifest: dict[str, Any],
        case: dict[str, Any],
        audit: dict[str, Any],
        objects: Mapping[str, Mapping[str, Any]],
        packages: dict[str, dict[str, Any]],
        assets: dict[str, SourceAssetRef],
    ) -> None:
        package_lineage = manifest.get("package_lineage", [])
        member_lineage = manifest.get("member_lineage", [])
        if len(package_lineage) != 1 or len(member_lineage) != 37:
            raise LedgerIntegrityError("Fixture lineage must contain 1 package and 37 member edges")
        for group in ("package_lineage", "member_lineage"):
            for index, edge in enumerate(manifest.get(group, [])):
                for endpoint in ("upstream_ref", "downstream_ref"):
                    self._resolve_object_ref(
                        edge.get(endpoint), objects, f"{group}[{index}].{endpoint}"
                    )
                if edge.get("relation_type") != "DERIVED_FROM":
                    raise LedgerIntegrityError(f"unexpected relation at {group}[{index}]")
        package_edge = package_lineage[0]
        if (
            package_edge["upstream_ref"]["id"] != packages["0808"]["package_id"]
            or package_edge["downstream_ref"]["id"] != packages["0814"]["package_id"]
        ):
            raise LedgerIntegrityError("package lineage must be 0814 DERIVED_FROM 0808")
        if packages["0808"]["lineage_edges"]:
            raise LedgerIntegrityError("0808 authoritative package cannot have an upstream")
        if packages["0814"]["lineage_edges"] != [
            _versioned_ref(packages["0808"], "package_id")
        ]:
            raise LedgerIntegrityError("0814 package upstream identity mismatch")
        for index, edge in enumerate(member_lineage):
            upstream = assets[edge["upstream_ref"]["id"]]
            downstream = assets[edge["downstream_ref"]["id"]]
            if upstream["asset_sha256"].lower() != downstream["asset_sha256"].lower():
                raise LedgerIntegrityError(f"member lineage byte mismatch at edge {index}")
        for key, package in packages.items():
            for index, ref in enumerate(package["lineage_edges"]):
                self._resolve_object_ref(ref, objects, f"{key}.lineage_edges[{index}]")

        all_asset_ids = set(assets)
        included = case["included_asset_refs"]
        for index, ref in enumerate(included):
            self._resolve_object_ref(ref, assets, f"included_asset_refs[{index}]")
        if {ref["id"] for ref in included} != all_asset_ids or len(included) != len(all_asset_ids):
            raise LedgerIntegrityError("Case included_asset_refs is not the exact 171-asset set")

        for stage, refs in case["stage_asset_refs"].items():
            for index, ref in enumerate(refs):
                self._resolve_object_ref(ref, assets, f"stage_asset_refs.{stage}[{index}]")
        stage_s04 = case["stage_asset_refs"]["S04_DATA_AND_VERIFICATION"]
        if stage_s04 != packages["0814"]["member_asset_refs"]:
            raise LedgerIntegrityError("default S04 refs must exactly equal ordered 0814 members")
        if any(ref["id"].startswith("s04.source0808::") for ref in stage_s04):
            raise LedgerIntegrityError("0808 provenance member entered default S04 runtime input")

        for index, spec in enumerate(case["declared_finding_specs"]):
            for ref_index, ref in enumerate(spec.get("rationale_source_refs", [])):
                self._resolve_object_ref(
                    ref,
                    objects,
                    f"declared_finding_specs[{index}].rationale_source_refs[{ref_index}]",
                )
        case_specs = {
            (item["code"], item["finding_kind"], item["replay_policy"])
            for item in case["declared_finding_specs"]
        }
        audit_specs = {
            (item["code"], item["finding_kind"], item["replay_policy"])
            for item in audit.get("declared_finding_specs", [])
        }
        if case_specs != audit_specs:
            raise LedgerIntegrityError("Case and import-audit declared Finding specs drift")
        info_codes = {item.get("code") for item in audit.get("informational_gap_findings", [])}
        if info_codes != {
            "CANDIDATE_PRESELECTED_EXPERT_SEED_NOT_SYSTEM_RANKED",
            "LEGACY_HYPOTHESIS_PACKAGE_NOT_MACHINE_VALIDATABLE",
        }:
            raise LedgerIntegrityError("import-audit informational Gap set mismatch")

    def asset(self, asset_id: str) -> SourceAssetRef:
        try:
            return self._assets[asset_id]
        except KeyError as exc:
            raise LedgerIntegrityError(f"unknown source asset: {asset_id}") from exc

    def resolve_ref(self, ref: VersionedRef) -> SourceAssetRef:
        return cast(SourceAssetRef, self._resolve_object_ref(ref, self._assets, ref.get("id", "?")))

    def default_s04_assets(self) -> list[SourceAssetRef]:
        refs = self._packages["0814"]["member_asset_refs"]
        if refs != self._stage_refs["S04_DATA_AND_VERIFICATION"]:
            raise LedgerIntegrityError("S04/0814 binding changed after catalog preflight")
        return [self.resolve_ref(ref) for ref in refs]

    def provenance_assets(self) -> list[SourceAssetRef]:
        return [self.resolve_ref(ref) for ref in self._packages["0808"]["member_asset_refs"]]

    def stage_assets(self, stage_id: str) -> list[SourceAssetRef]:
        refs = self._stage_refs.get(stage_id)
        if refs is None:
            raise LedgerIntegrityError(f"unknown stage id: {stage_id}")
        return [self.resolve_ref(ref) for ref in refs]

    def read_bytes(self, asset: SourceAssetRef) -> bytes:
        current = self.asset(asset["asset_id"])
        if current != asset:
            raise LedgerIntegrityError(f"unregistered SourceAssetRef: {asset['asset_id']}")
        path = self._safe_path(asset["repository_relative_path"])
        data = path.read_bytes()
        if len(data) != asset["byte_size"] or (
            hashlib.sha256(data).hexdigest().lower() != asset["asset_sha256"].lower()
        ):
            raise LedgerIntegrityError(f"source byte drift: {asset['asset_id']}")
        return data


class ReplayArtifactImporter:
    """Persist imported, derived, and native objects through the public Store boundary."""

    def __init__(
        self, store: ArtifactStore, catalog: ManifestAssetCatalog, run_id: str, task_id: str
    ) -> None:
        self.store = store
        self.catalog = catalog
        self.run_id = run_id
        self.task_id = task_id
        self.contracts = catalog.contracts

    def import_source(self, asset_id: str) -> ArtifactRef:
        asset = self.catalog.asset(asset_id)
        content = self.catalog.read_bytes(asset)
        envelope = {
            "artifact_id": _artifact_id(self.run_id, "src", asset_id),
            "logical_artifact_id": asset_id,
            "artifact_type": "SourceDocument",
            "schema_version": _SCHEMA_VERSION,
            "artifact_revision": 1,
            "task_id": self.task_id,
            "run_id": self.run_id,
            "run_mode": "REPLAY",
            "origin_mode": "IMPORTED",
            "authority_mode": "SOURCE_BYTES",
            "content_ref": "artifact-content://" + hashlib.sha256(asset_id.encode()).hexdigest(),
            "content_sha256": compute_authority_hash("SOURCE_BYTES", content),
            "source_asset_refs": [_versioned_ref(asset, "asset_id")],
            "producer": _PRODUCER,
            "source_authored_at": asset["source_authored_at"],
            "ingested_at": asset["ingested_at"],
            "created_at": _FIXED_TS,
        }
        return self.store.put(cast(ArtifactEnvelope, envelope), content, "SOURCE_BYTES")

    def import_summary(
        self,
        artifact_type: str,
        schema_name: str,
        payload: dict[str, Any],
        source_asset_refs: list[VersionedRef],
        parent_refs: list[ArtifactRef],
    ) -> ArtifactRef:
        if not parent_refs:
            raise LedgerIntegrityError(f"derived {artifact_type} requires imported parents")
        self.contracts.validate(schema_name, payload)
        envelope = {
            "artifact_id": _artifact_id(self.run_id, "derived", payload["snapshot_id"]),
            "logical_artifact_id": payload["snapshot_id"],
            "artifact_type": artifact_type,
            "schema_version": _SCHEMA_VERSION,
            "artifact_revision": 1,
            "task_id": self.task_id,
            "run_id": self.run_id,
            "run_mode": "REPLAY",
            "origin_mode": "DERIVED",
            "authority_mode": "CANONICAL_JSON",
            "derivation_kind": "EXTRACTED_FROM_IMPORTED",
            "derived_from_refs": parent_refs,
            "payload": payload,
            "content_sha256": compute_authority_hash("CANONICAL_JSON", payload),
            "parent_refs": parent_refs,
            "source_asset_refs": source_asset_refs,
            "producer": _PRODUCER,
            "created_at": _FIXED_TS,
        }
        return self.store.put(cast(ArtifactEnvelope, envelope), payload, "CANONICAL_JSON")

    def persist_native(
        self,
        artifact_type: str,
        schema_name: str,
        logical_id: str,
        payload: dict[str, Any],
        parent_refs: list[ArtifactRef] | None = None,
    ) -> ArtifactRef:
        self.contracts.validate(schema_name, payload)
        envelope = {
            "artifact_id": _artifact_id(self.run_id, "native", f"{artifact_type}:{logical_id}"),
            "logical_artifact_id": logical_id,
            "artifact_type": artifact_type,
            "schema_version": _SCHEMA_VERSION,
            "artifact_revision": 1,
            "task_id": self.task_id,
            "run_id": self.run_id,
            "run_mode": "REPLAY",
            "origin_mode": "NATIVE",
            "authority_mode": "CANONICAL_JSON",
            "payload": payload,
            "content_sha256": compute_authority_hash("CANONICAL_JSON", payload),
            "parent_refs": parent_refs or [],
            "producer": _PRODUCER,
            "created_at": _FIXED_TS,
        }
        return self.store.put(cast(ArtifactEnvelope, envelope), payload, "CANONICAL_JSON")


def _snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    payload["content_hash"] = canonical_json.content_hash_excluding(payload)
    return payload


class ReplayCandidateProvider:
    def __init__(self, catalog: ManifestAssetCatalog) -> None:
        self.catalog = catalog

    def candidate_snapshot(self) -> CandidateSnapshot:
        assets = self.catalog.stage_assets("S01_CANDIDATE")
        return cast(CandidateSnapshot, _snapshot({
            "snapshot_id": "candidate-shrgt45", "schema_version": _SCHEMA_VERSION,
            "parameter": "SHRGT45", "selection_method": "EXPERT_SEED",
            "ranking_status": "NOT_IMPLEMENTED",
            "source_refs": [_versioned_ref(a, "asset_id") for a in assets],
            "limitation_note": "SHRGT45 是专家预选种子；候选排序模块尚未实现。",
        }))


class ReplayMechanismProvider:
    def __init__(self, catalog: ManifestAssetCatalog) -> None:
        self.catalog = catalog

    def mechanism_snapshot(self) -> MechanismSnapshot:
        assets = self.catalog.stage_assets("S02_MECHANISM")
        return cast(MechanismSnapshot, _snapshot({
            "snapshot_id": "mechanism-shrgt45", "schema_version": _SCHEMA_VERSION,
            "parameter": "SHRGT45", "source_version": "V2.3",
            "allowed_interpretation": "光球非势性/自由能状态的定量代理，可能与自由能状态变化相关。",
            "forbidden_claims": [
                "直接测量总自由能", "直接测量自由能注入率", "证明磁重联",
                "证明MHD失稳", "证明三维拓扑", "证明完整因果链",
            ],
            "source_refs": [_versioned_ref(a, "asset_id") for a in assets],
            "extraction_completeness": "PARTIAL",
        }))


class ReplayHypothesisProvider:
    def __init__(self, catalog: ManifestAssetCatalog) -> None:
        self.catalog = catalog

    def hypothesis_snapshot(self) -> HypothesisSnapshot:
        return cast(HypothesisSnapshot, _snapshot({
            "snapshot_id": "hypothesis-shrgt45", "schema_version": _SCHEMA_VERSION,
            "upstream_mechanism_ref": _versioned_ref(
                self.catalog.asset("s02.mechanism-brief-v2_3"), "asset_id"
            ),
            "predictor": "SHRGT45", "outcome": "M1.0+ 太阳耀斑", "window": "[t+3h, t+6h)",
            "flow3_domain_status": "LEGACY_NOT_MACHINE_VALIDATABLE", "machine_verifiable": False,
        }))


class ReplayDataProvider:
    def __init__(self, catalog: ManifestAssetCatalog) -> None:
        self.catalog = catalog

    def verification_snapshot(self) -> VerificationSnapshot:
        assets = self.catalog.default_s04_assets()
        return cast(VerificationSnapshot, _snapshot({
            "snapshot_id": "verification-shrgt45", "schema_version": _SCHEMA_VERSION,
            "import_summary": "0814 Demo 运行投影（43 成员）历史导入；非正式统计执行。",
            "is_formal_execution": False,
            "source_refs": [_versioned_ref(a, "asset_id") for a in assets],
        }))


class ReplayCounterexampleProvider:
    def __init__(self, catalog: ManifestAssetCatalog) -> None:
        self.catalog = catalog

    def counterexample_snapshot(self) -> CounterexampleSnapshot:
        return cast(CounterexampleSnapshot, _snapshot({
            "snapshot_id": "counterexample-shrgt45", "schema_version": _SCHEMA_VERSION,
            "scientific_counterexample_candidates": [], "data_label_issues": [],
            "not_evaluable_items": ["历史反例输入包身份尚未逐文件定位"],
            "next_steps": ["后续以独立任务绑定机器可验证输入；本次不补造。"],
        }))


class ReplayMagnetogramQAProvider:
    def __init__(self, catalog: ManifestAssetCatalog) -> None:
        self.catalog = catalog

    def magnetogram_qa_snapshot(self) -> MagnetogramQASnapshot:
        return cast(MagnetogramQASnapshot, _snapshot({
            "snapshot_id": "magnetogram-qa-shrgt45", "schema_version": _SCHEMA_VERSION,
            "file_checks": ["18 个已登记 S06 来源文件的路径、字节数与 SHA256 已核对"],
            "frame_checks": [], "provenance_checks": ["仅核对已登记来源，不推导机制证据"],
            "qa_verdict": "PASS",
            "qa_scope_note": (
                "QA PASS 仅表示已定义的文件/provenance 检查通过，"
                "不等于机制或预测证据。"
            ),
        }))
