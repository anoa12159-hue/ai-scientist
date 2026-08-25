# ruff: noqa: E501  (frozen D-005 hash literals exceed the cosmetic line-length rule)
"""T003 correction: SourceAssetRef / SourcePackageRef / lineage verification.

Covers Schema validity, JCS content_hash self-consistency, reference closure,
D-005 per-file identity, package member boundaries, and Fail-Closed mutations
that rehash the object before an independent semantic validator rejects it.
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from ai_scientist_mvp.domain.canonical_json import content_hash_excluding

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures" / "shrgt45"
CONTRACTS = ROOT / "contracts"

LOGICAL_FILE_COUNT = 171
LOGICAL_TOTAL_BYTES = 9_725_849
FROZEN_SCHEMA_VERSION = "0.1.0"
P0808 = {"member_count": 90, "total_bytes": 3_818_486,
         "tree_hash": "a45e77758ca59d98a7fb333326f5463177ad62944376a95c4880230595e6c032"}
P0814 = {"member_count": 43, "total_bytes": 1_284_797,
         "tree_hash": "e577951858466b40cc001627ef27185267d9ed63e249f6ef78b500723d9c47dc"}
EXPECTED_LOCAL_0814 = {
    "00_阅读说明/README.md", "00_阅读说明/数据使用清单.csv", "00_阅读说明/数据文件关系图.svg",
    "05_完整性/acceptance_check.csv", "05_完整性/file_sha256_manifest.csv", "05_完整性/manifest.json",
}

FROZEN_38 = {
    "s01.current-research-constraints": "6f7a67e5e012de9663f164a5602a8509b159a5471889f20a6637a46239d285ad",
    "s01.parameter-ranking-current-state": "80ded8eb60c7ef801867071109bc76e99fe9985e6e0eaca04316184977da5658",
    "s02.mechanism-brief-v2_3": "68ed21d00050a8f8f6b5dcf2b181417d4aee217da0a01c9c502abc384badeba1",
    "s02.mechanism-brief-v2_2-historical": "ef4eda2c011f6af4cc5c707f138140cae810bd311e099c0fc6883bc02559ff76",
    "s02.agent-run-phase2-20260814": "018572a27cad658d0438dffeeb2201a310ac4a97244e7a20586d70867697eecd",
    "s02.mechanism-human-summary": "6ccce727cf27ec8387442e64a625ae36fbd78f10c078b1f12fb49884ad0f8d9f",
    "s03.hypothesis-baseline": "b7e687c310a33f248ec07576ea19f132d0742f04cb64e92c39c53e759cabe9bf",
    "s03.trend-method-theil-sen": "9fdbd6e4e6fb123e6895d606b5ca3f3cd26ff4363f4158b3a4c72469ec2d5dda",
    "s03.hamed-rao-spec": "f40685dac5938ab92d194d7fa1e8c81abc6f660e02c36e4780cac60d55257d61",
    "s03.hamed-rao-calibration-report": "8ec90da836391d59317cd79c0934568e8967ac7181a53071a7a1d091e73531a9",
    "s03.hamed-rao-calibration-summary": "2da32d9c5e778eea66d71fcc69daadbc187a1070a04f82ad7a7e932b0a61104c",
    "s03.hamed-rao-run-metadata": "8d7d5056d1e96e8ad4de6a230ff37ac6f2b81e9d7eb5643f864f923cd53b0677",
    "s05.counterexample-report": "a80fb7a37b0ad9a133c6974c4b48972a06ad2d5fc6061cca851d7a457e6aedd5",
    "s05.next-validation-plan": "d45079e1f413b32e8bc6f728d69f22c9fa8d36ff5158b4ef4a0e2d1a9e253cf2",
    "s05.usflux-ar-stratification": "31d923bc0fdaa65548be6f84a230da471fabcfaae273cfe89f068f4bcb33d428",
    "s05.counterexample-catalog": "859431b967528ca41a2d2877ed0df62ab26008731ccd9bf8068ef56f3f28ca2d",
    "s05.sensitivity-results": "8a12defcc0d6b2d8fc208de5fe788e7a96b0ca5b7791cd684bbb07cb1a1ce669",
    "s05.acceptance-criteria": "76dc664bd0de01767425a8ef5a11052f4b85dd992abd8d0e95626a74b1dfc40a",
    "s06.readme": "02f8f0d4fa9fb17e16504aa77fb43ce06472408bbc92569a1abd506d41e5debd",
    "s06.qa-spec": "4ef62966c4bab0bdf364766f9c83cc57f6bd88dc56dc34330874e06ed3955cdb",
    "s06.manifest": "64465306b3a45e1e9c397196f12499f875c54a7b8ace295b3779dec7fdc00bff",
    "s06.case-keyword-timeseries": "915bedfb73959c2d6d0e20d75a5feb4a723e99fbd1a4948ff7a808bc2e2a1bdc",
    "s06.delivery-sha256": "b9e212a276e82d15bac71d1ebbb085b41d58940037d7134574dcbaece4a86040",
    "s06.input-handoff": "b1f11ff4da928004a28b04f025dac126a61a7dc863ae1e051adaaf0be91f44b8",
    "s06.required-case-status": "93b98a5bd13f0d403e905b7d1c8393de9caf59c66aaf2a22337b8b813d4429d4",
    "s06.case-label-audit": "bb45943a8cbf1d79c4aff525ab8ad66931d3f7e73fe569317f9d8b0654d0092a",
    "s06.file-quality": "fb8709176da9ac34ebe6768476e4e272f67e29d707df00529ae500dcc7f00f1f",
    "s06.frame-quality": "b41081d34a6e66f848466c4105170abb56a7570d5a61318e385a2063d856a2d1",
    "s06.display-config": "571c120e99278be27172bba96385d86f6bc6b1c5f4e648ff075471a96ee4a4f5",
    "s06.upstream-basis": "883e18cc0dad36a9990916d1a85ecdccca19b7722a6a6729bb549cf6d6c2c788",
    "s06.upstream-jsoc-list": "aa087dea816ea1ad0f36185f6c6b19abf3131ef400128a5fc0cb09caff0601a1",
    "s06.upstream-window-audit": "5ba10386f01954b544d1a7d2fb6d9cfc2bb03579e32e8c90f49ba8d723785be6",
    "s06.upstream-row-extract": "693941efa9aaf71b7a78258780c5b0968f54b545c521d542d91d0eabac7d4fd0",
    "s06.upstream-sample-list": "6df0e34bbaf4d0dc5f564e899f0bee21971a000fb6155796dd58b48f95b945a1",
    "s06.portrait-panel": "23410d22835603d88aefc03f539d29d1de7b3b0946024dd788fae180d10d6f35",
    "s06.full-context-panel": "ef4121a2d8919a23251ff828d70ddbe8e0ea3c8c7db99b33342cd3c5eea38249",
    "s07.teacher-review-draft": "bd3336cc8f81beda5c4c4ea55a8f8ae1744e56b66cb256c3df919500b145e042",
    "s07.data-rule-independent-review": "e1b871237f246bbb988cdc32e7b9a66d262f32047760ee3a15282cea7c878d0e",
}

_0808_MEMBER_ID = "s04.source0808::01_主报告/01_全信息基准版Demo结果报告_20260808.md"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _schemas() -> dict:
    schemas = {}
    for path in sorted(CONTRACTS.rglob("*.schema.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        schemas[schema["$id"]] = schema
    return schemas


def _validator(name: str, schemas: dict):
    schema = next(v for k, v in schemas.items() if k.endswith("/" + name + ".schema.json"))
    registry = Registry().with_resources(
        [(Resource.from_contents(s).id(), Resource.from_contents(s)) for s in schemas.values()]
    )
    return Draft202012Validator(schema, registry=registry, format_checker=FormatChecker())


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().lower()


def _manifest() -> dict:
    return _load("manifest.json")


def _case() -> dict:
    return _load("case-manifest.json")


def _audit() -> dict:
    return _load("import-audit.json")


def _rehash(obj: dict) -> dict:
    obj = deepcopy(obj)
    obj["content_hash"] = content_hash_excluding(obj)
    return obj


def _is_versioned_ref(ref: object) -> bool:
    return isinstance(ref, dict) and set(ref) == {"id", "schema_version", "content_hash"}


def _identity_objects(manifest: dict) -> tuple[dict[str, dict], list[str]]:
    objects: dict[str, dict] = {}
    errors: list[str] = []
    for asset in manifest["source_assets"]:
        identity = asset["asset_id"]
        if identity in objects:
            errors.append(f"duplicate identity: {identity}")
        objects[identity] = asset
    for package in manifest["source_packages"].values():
        identity = package["package_id"]
        if identity in objects:
            errors.append(f"duplicate identity: {identity}")
        objects[identity] = package
    return objects, errors


def _versioned_ref_errors(ref: object, objects: dict[str, dict], location: str) -> list[str]:
    if not _is_versioned_ref(ref):
        return [f"malformed VersionedRef at {location}"]
    assert isinstance(ref, dict)
    identity = ref["id"]
    target = objects.get(identity)
    if target is None:
        return [f"unresolved VersionedRef at {location}: {identity}"]
    errors = []
    if ref["schema_version"] != target["schema_version"]:
        errors.append(f"stale schema_version at {location}: {identity}")
    if ref["content_hash"] != target["content_hash"]:
        errors.append(f"stale content_hash at {location}: {identity}")
    return errors


def _semantic_errors(manifest: dict, case: dict) -> list[str]:
    objects, errors = _identity_objects(manifest)
    by_id = {a["asset_id"]: a for a in manifest["source_assets"]}
    # schema_version frozen
    for a in manifest["source_assets"]:
        if a["schema_version"] != FROZEN_SCHEMA_VERSION:
            errors.append(f"bad schema_version: {a['asset_id']}")
    for pkg in manifest["source_packages"].values():
        if pkg["schema_version"] != FROZEN_SCHEMA_VERSION:
            errors.append(f"bad package schema_version: {pkg['package_id']}")
    # Package member refs bind exact frozen sets, without duplicates.
    for pkg_id, prefix, count in (("0808", "s04.source0808::", 90), ("0814", "s04.demo0814::", 43)):
        pkg = manifest["source_packages"][pkg_id]
        refs = pkg["member_asset_refs"]
        expected_ids = {identity for identity in by_id if identity.startswith(prefix)}
        ref_ids = [ref.get("id") for ref in refs if isinstance(ref, dict)]
        if pkg["member_count"] != count or len(refs) != count or len(expected_ids) != count:
            errors.append(f"{pkg_id} member count drift")
        if len(ref_ids) != len(set(ref_ids)):
            errors.append(f"{pkg_id} duplicate member ref")
        if set(ref_ids) != expected_ids:
            errors.append(f"{pkg_id} member set drift")
        for index, ref in enumerate(refs):
            errors.extend(_versioned_ref_errors(ref, objects, f"{pkg_id}.member_asset_refs[{index}]"))
    # 0808 must have no lineage_edges (non-circular)
    if manifest["source_packages"]["0808"]["lineage_edges"]:
        errors.append("0808 must have empty lineage_edges")
    for pkg_id, package in manifest["source_packages"].items():
        for index, ref in enumerate(package["lineage_edges"]):
            errors.extend(_versioned_ref_errors(ref, objects, f"{pkg_id}.lineage_edges[{index}]"))
    # Package lineage is one directed 0814 DERIVED_FROM 0808 relation.
    if len(manifest["package_lineage"]) != 1:
        errors.append("package lineage must contain exactly one edge")
    for index, edge in enumerate(manifest["package_lineage"]):
        if edge.get("relation_type") != "DERIVED_FROM":
            errors.append("package lineage relation wrong")
        upstream = edge.get("upstream_ref")
        downstream = edge.get("downstream_ref")
        errors.extend(_versioned_ref_errors(upstream, objects, f"package_lineage[{index}].upstream_ref"))
        errors.extend(_versioned_ref_errors(downstream, objects, f"package_lineage[{index}].downstream_ref"))
        if (
            not isinstance(upstream, dict)
            or not isinstance(downstream, dict)
            or upstream.get("id") != "s04.source0808"
            or downstream.get("id") != "s04.demo0814"
        ):
            errors.append("package lineage endpoints wrong")
    # Member lineage refs bind current identities and byte-identical parents.
    if len(manifest["member_lineage"]) != 37:
        errors.append("member lineage count drift")
    for index, edge in enumerate(manifest["member_lineage"]):
        if edge.get("relation_type") != "DERIVED_FROM":
            errors.append(f"member lineage relation wrong at {index}")
        upstream = edge.get("upstream_ref")
        downstream = edge.get("downstream_ref")
        errors.extend(_versioned_ref_errors(upstream, objects, f"member_lineage[{index}].upstream_ref"))
        errors.extend(_versioned_ref_errors(downstream, objects, f"member_lineage[{index}].downstream_ref"))
        if isinstance(upstream, dict) and isinstance(downstream, dict):
            upstream_asset = by_id.get(upstream.get("id"))
            downstream_asset = by_id.get(downstream.get("id"))
            if upstream_asset and downstream_asset and upstream_asset["asset_sha256"] != downstream_asset["asset_sha256"]:
                errors.append(f"member lineage bytes differ at {index}")
    # Stage refs all bind current SourceAssetRef identities; S04 == 0814 only.
    for stage, refs in case["stage_asset_refs"].items():
        for index, ref in enumerate(refs):
            errors.extend(_versioned_ref_errors(ref, by_id, f"stage_asset_refs.{stage}[{index}]"))
        if stage == "S04_DATA_AND_VERIFICATION":
            if any(not r["id"].startswith("s04.demo0814::") for r in refs if isinstance(r, dict)):
                errors.append("0808 leaked into S04 runtime")
    # Included refs bind each current SourceAssetRef exactly once.
    included_refs = case["included_asset_refs"]
    included_ids = [ref.get("id") for ref in included_refs if isinstance(ref, dict)]
    for index, ref in enumerate(included_refs):
        errors.extend(_versioned_ref_errors(ref, by_id, f"included_asset_refs[{index}]"))
    if len(included_ids) != len(set(included_ids)):
        errors.append("duplicate included_asset_ref")
    if set(included_ids) != set(by_id) or len(included_refs) != len(by_id):
        errors.append("included_asset_refs != 171 exact set")
    # Finding rationale may bind assets or package identities.
    for spec in case["declared_finding_specs"]:
        for index, ref in enumerate(spec.get("rationale_source_refs", [])):
            errors.extend(
                _versioned_ref_errors(ref, objects, f"{spec['code']}.rationale_source_refs[{index}]")
            )
    return errors


def _disk_path_errors(manifest: dict) -> list[str]:
    errors: list[str] = []
    declared_paths = [a["repository_relative_path"] for a in manifest["source_assets"]]
    declared = set(declared_paths)
    if len(declared_paths) != len(declared):
        errors.append("duplicate repository_relative_path")
    actual = set()
    for sub in ("assets", "packages"):
        for path in (FIXTURES / sub).rglob("*"):
            if path.is_file():
                actual.add(path.relative_to(ROOT).as_posix())
    if actual != declared:
        errors.append(f"path-set drift: extra={actual - declared} missing={declared - actual}")
    for asset in manifest["source_assets"]:
        path = ROOT / asset["repository_relative_path"]
        if not path.is_file():
            continue
        if path.stat().st_size != asset["byte_size"]:
            errors.append(f"byte_size mismatch: {asset['asset_id']}")
        if _sha256(path) != asset["asset_sha256"]:
            errors.append(f"asset_sha256 mismatch: {asset['asset_id']}")
    return errors


# --- identity / schema / content_hash ----------------------------------------

def test_171_source_assets_schema_valid_and_hash_self_consistent() -> None:
    schemas = _schemas()
    validator = _validator("source-asset-ref", schemas)
    manifest = _manifest()
    assert len(manifest["source_assets"]) == LOGICAL_FILE_COUNT
    for asset in manifest["source_assets"]:
        assert list(validator.iter_errors(asset)) == [], asset["asset_id"]
        assert content_hash_excluding(asset) == asset["content_hash"], asset["asset_id"]


def test_raw_sha256_distinct_from_jcs_content_hash() -> None:
    manifest = _manifest()
    for asset in manifest["source_assets"]:
        assert _sha256(ROOT / asset["repository_relative_path"]) == asset["asset_sha256"]
        assert asset["asset_sha256"] != asset["content_hash"]


def test_2_source_packages_schema_valid_hash_self_consistent() -> None:
    schemas = _schemas()
    validator = _validator("source-package-ref", schemas)
    manifest = _manifest()
    for pkg_id, frozen in (("0808", P0808), ("0814", P0814)):
        pkg = manifest["source_packages"][pkg_id]
        assert list(validator.iter_errors(pkg)) == [], pkg_id
        assert content_hash_excluding(pkg) == pkg["content_hash"], pkg_id
        assert pkg["member_count"] == frozen["member_count"]
        assert pkg["total_bytes"] == frozen["total_bytes"]
        assert pkg["tree_hash"] == frozen["tree_hash"]


def test_replay_case_manifest_schema_valid_and_hash_self_consistent() -> None:
    schemas = _schemas()
    validator = _validator("replay-case-manifest", schemas)
    case = _case()
    assert list(validator.iter_errors(case)) == []
    assert content_hash_excluding(case) == case["content_hash"]


def test_import_audit_hash_and_time_evidence_are_self_consistent() -> None:
    audit = _audit()
    assert content_hash_excluding(audit) == audit["content_hash"]
    tiers = {tier["scope"]: tier for tier in audit["time_evidence"]["tiers"]}
    assert tiers["S01"]["is_proxy"] is True
    assert "非原始成文日期" in tiers["S01"]["note"]
    assert audit["time_evidence"]["ingested_at"]["is_proxy"] is False
    assert audit["time_evidence"]["ingested_at"]["value"] != "2026-08-16T00:00:00+08:00"


def test_repository_relative_root_is_real() -> None:
    manifest = _manifest()
    assert manifest["source_packages"]["0808"]["repository_relative_root"] == "fixtures/shrgt45/packages/0808"
    assert manifest["source_packages"]["0814"]["repository_relative_root"] == "fixtures/shrgt45/packages/0814"


def test_d005_per_file_identity_for_38_files() -> None:
    manifest = _manifest()
    by_id = {a["asset_id"]: a for a in manifest["source_assets"]}
    assert set(FROZEN_38) == {a for a in by_id if not a.startswith("s04.")}
    for asset_id, frozen_sha in FROZEN_38.items():
        assert by_id[asset_id]["asset_sha256"] == frozen_sha, asset_id


def test_package_tree_hashes_match_frozen_on_disk() -> None:
    def tree_hash(root: Path) -> str:
        entries = []
        for path in sorted(root.rglob("*")):
            if path.is_file():
                entries.append(f"{path.relative_to(root).as_posix()}\t{path.stat().st_size}\t{_sha256(path)}\n")
        entries.sort()
        return hashlib.sha256("".join(entries).encode("utf-8")).hexdigest().lower()

    assert tree_hash(FIXTURES / "packages" / "0808") == P0808["tree_hash"]
    assert tree_hash(FIXTURES / "packages" / "0814") == P0814["tree_hash"]


# --- closure assertions ------------------------------------------------------

def test_exact_disk_path_set_matches_171() -> None:
    assert _disk_path_errors(_manifest()) == []


def test_package_member_refs_match_actual_members() -> None:
    manifest = _manifest()
    p0808 = {a["asset_id"] for a in manifest["source_assets"] if a["asset_id"].startswith("s04.source0808::")}
    p0814 = {a["asset_id"] for a in manifest["source_assets"] if a["asset_id"].startswith("s04.demo0814::")}
    assert {r["id"] for r in manifest["source_packages"]["0808"]["member_asset_refs"]} == p0808
    assert {r["id"] for r in manifest["source_packages"]["0814"]["member_asset_refs"]} == p0814


def test_included_refs_match_171_exact() -> None:
    manifest = _manifest()
    case = _case()
    assert {r["id"] for r in case["included_asset_refs"]} == {a["asset_id"] for a in manifest["source_assets"]}


def test_all_stage_refs_are_versioned_and_resolve() -> None:
    manifest = _manifest()
    by_id = {a["asset_id"]: a for a in manifest["source_assets"]}
    case = _case()
    for stage, refs in case["stage_asset_refs"].items():
        for ref in refs:
            assert _is_versioned_ref(ref), stage
            assert ref["id"] in by_id, ref["id"]


def test_s04_refs_equal_0814_43_members() -> None:
    manifest = _manifest()
    case = _case()
    p0814 = {a["asset_id"] for a in manifest["source_assets"] if a["asset_id"].startswith("s04.demo0814::")}
    s04 = {r["id"] for r in case["stage_asset_refs"]["S04_DATA_AND_VERIFICATION"]}
    assert s04 == p0814
    assert len(s04) == 43


def test_all_lineage_and_rationale_refs_resolve() -> None:
    manifest = _manifest()
    case = _case()
    assert _semantic_errors(manifest, case) == []


def test_schema_version_is_frozen_0_1_0() -> None:
    manifest = _manifest()
    assert all(a["schema_version"] == FROZEN_SCHEMA_VERSION for a in manifest["source_assets"])
    assert all(p["schema_version"] == FROZEN_SCHEMA_VERSION for p in manifest["source_packages"].values())


# --- Fail-Closed mutations (rehash then independent semantic rejection) ------

def test_unknown_schema_version_rehash_still_rejected() -> None:
    manifest = _manifest()
    case = _case()
    manifest["source_assets"][0]["schema_version"] = "9.9.9"
    manifest["source_assets"][0] = _rehash(manifest["source_assets"][0])
    assert _semantic_errors(manifest, case)


def test_0814_mixed_0808_member_rehash_still_rejected() -> None:
    manifest = _manifest()
    case = _case()
    pkg = manifest["source_packages"]["0814"]
    pkg["member_asset_refs"][0] = {"id": _0808_MEMBER_ID, "schema_version": "0.1.0", "content_hash": "0" * 64}
    manifest["source_packages"]["0814"] = _rehash(pkg)
    assert _semantic_errors(manifest, case)


def test_s04_mixed_0808_ref_rehash_still_rejected() -> None:
    manifest = _manifest()
    case = _case()
    case["stage_asset_refs"]["S04_DATA_AND_VERIFICATION"].append(
        {"id": _0808_MEMBER_ID, "schema_version": "0.1.0", "content_hash": "0" * 64}
    )
    case = _rehash(case)
    assert _semantic_errors(manifest, case)


def test_bare_string_stage_ref_rejected() -> None:
    manifest = _manifest()
    case = _case()
    case["stage_asset_refs"]["S01_CANDIDATE"] = ["s01.current-research-constraints"]
    case = _rehash(case)
    assert _semantic_errors(manifest, case)


def test_malformed_versioned_ref_rejected() -> None:
    manifest = _manifest()
    case = _case()
    case["stage_asset_refs"]["S01_CANDIDATE"][0] = {"id": "s01.current-research-constraints"}
    case = _rehash(case)
    assert _semantic_errors(manifest, case)


def test_package_lineage_stale_ref_rejected() -> None:
    manifest = _manifest()
    case = _case()
    manifest["package_lineage"][0]["upstream_ref"]["content_hash"] = "0" * 64
    assert _semantic_errors(manifest, case)


def test_stage_ref_stale_hash_after_case_rehash_rejected() -> None:
    manifest = _manifest()
    case = _case()
    case["stage_asset_refs"]["S01_CANDIDATE"][0]["content_hash"] = "0" * 64
    case = _rehash(case)
    assert _semantic_errors(manifest, case)


def test_included_ref_stale_hash_after_case_rehash_rejected() -> None:
    manifest = _manifest()
    case = _case()
    case["included_asset_refs"][0]["content_hash"] = "0" * 64
    case = _rehash(case)
    assert _semantic_errors(manifest, case)


def test_rationale_ref_stale_hash_after_case_rehash_rejected() -> None:
    manifest = _manifest()
    case = _case()
    case["declared_finding_specs"][0]["rationale_source_refs"][0]["content_hash"] = "0" * 64
    case = _rehash(case)
    assert _semantic_errors(manifest, case)


def test_member_lineage_stale_hash_rejected() -> None:
    manifest = _manifest()
    case = _case()
    manifest["member_lineage"][0]["upstream_ref"]["content_hash"] = "0" * 64
    assert _semantic_errors(manifest, case)


def test_versioned_ref_schema_version_mismatch_after_case_rehash_rejected() -> None:
    manifest = _manifest()
    case = _case()
    case["stage_asset_refs"]["S01_CANDIDATE"][0]["schema_version"] = "9.9.9"
    case = _rehash(case)
    assert _semantic_errors(manifest, case)


def test_0814_duplicate_member_after_package_rehash_rejected() -> None:
    manifest = _manifest()
    case = _case()
    package = manifest["source_packages"]["0814"]
    package["member_asset_refs"][0] = deepcopy(package["member_asset_refs"][1])
    package = _rehash(package)
    manifest["source_packages"]["0814"] = package
    manifest["package_lineage"][0]["downstream_ref"]["content_hash"] = package["content_hash"]
    for spec in case["declared_finding_specs"]:
        for ref in spec.get("rationale_source_refs", []):
            if ref["id"] == package["package_id"]:
                ref["content_hash"] = package["content_hash"]
    case = _rehash(case)
    assert _semantic_errors(manifest, case)


def test_raw_asset_sha_change_after_asset_rehash_rejected() -> None:
    manifest = _manifest()
    asset = manifest["source_assets"][0]
    asset["asset_sha256"] = "0" * 64
    manifest["source_assets"][0] = _rehash(asset)
    assert _disk_path_errors(manifest)


def test_unresolved_rationale_ref_rejected() -> None:
    manifest = _manifest()
    case = _case()
    case["declared_finding_specs"][0]["rationale_source_refs"] = [
        {"id": "s99.unknown", "schema_version": "0.1.0", "content_hash": "0" * 64}
    ]
    case = _rehash(case)
    assert _semantic_errors(manifest, case)


def test_extra_unregistered_disk_path_rejected() -> None:
    manifest = _manifest()
    manifest["source_assets"][0]["repository_relative_path"] = "fixtures/shrgt45/assets/s01/UNREGISTERED.bin"
    manifest["source_assets"][0] = _rehash(manifest["source_assets"][0])
    assert _disk_path_errors(manifest)


def test_real_manifest_has_zero_semantic_and_disk_errors() -> None:
    manifest = _manifest()
    case = _case()
    assert _semantic_errors(manifest, case) == []
    assert _disk_path_errors(manifest) == []
