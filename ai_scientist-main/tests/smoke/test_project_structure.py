"""T001 smoke tests: repository skeleton and execution guardrails.

These checks are offline and need no API keys. They verify that:

- the required skeleton paths exist;
- the package imports from ``src``;
- frozen governance/contract documents are byte-identical to the accepted
  T000 baseline (``governance/baseline.lock.json`` and its bound hashes, plus
  one tree pin over every file T001 must not modify);
- no business implementation (graph nodes, schemas, fixtures, frontend pages)
  leaked into this task;
- project files carry no machine-specific absolute paths and no secrets;
- CI runs the same commands as the local verification entry.

Canonicalization locked by T000: RFC 8785 JCS with minimal string escaping
(non-ASCII characters stay raw UTF-8), SHA-256, uppercase hex. ``content_hash``
is computed after removing the top-level ``content_hash`` field.

The frozen-tree pin is re-computable: for each file under the frozen scopes
emit ``<posix-relative-path>\\t<sha256>\\n``, ordinal-sort the lines, SHA-256
the joined UTF-8 text. If a governance-accepted change to the frozen trees
occurs, this constant must be updated as part of that change process.

Later tasks legitimately introduce LangGraph, FastAPI, schemas and fixtures;
they must update the corresponding T001 guardrail assertions here as part of
their own accepted change set.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
PACKAGE_DIR = SRC_ROOT / "ai_scientist_mvp"

# Pin over AGENTS.md, tasks/TASK-001.md, governance/**, docs/contracts/**,
# docs/adr/** as they existed at T005 closeout. The T005 CompletionRecord is
# intentionally part of the governance tree pin.
FROZEN_TREE_SHA256_T005_CLOSEOUT = (
    "EAA17CA34C43AC1145450ECB9605862D530BC4B996DFED47EAECC633235A7EFD"
)

_PACKAGE_SUBPACKAGES = (
    "domain",
    "application",
    "infrastructure",
    "providers",
    "workflow",
    "api",
    "agent",
    "skills",
)

_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(
        r"(?i)\b(api[_-]?key|secret|token|password|passwd)"
        r"\s*[:=]\s*[\"']?[A-Za-z0-9+/_.-]{8,}[\"']?"
    ),
)

_DRIVE_PATH = re.compile(r"\b[A-Za-z]:[\\/]")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _jcs_bytes(obj: object) -> bytes:
    return json.dumps(
        obj,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _content_hash(obj: dict) -> str:
    stripped = {key: value for key, value in obj.items() if key != "content_hash"}
    return hashlib.sha256(_jcs_bytes(stripped)).hexdigest().upper()


def _frozen_files() -> list[Path]:
    scopes = (
        PROJECT_ROOT / "AGENTS.md",
        PROJECT_ROOT / "tasks" / "TASK-001.md",
        PROJECT_ROOT / "governance",
        PROJECT_ROOT / "docs" / "contracts",
        PROJECT_ROOT / "docs" / "adr",
    )
    files: list[Path] = []
    for scope in scopes:
        if scope.is_file():
            files.append(scope)
        else:
            files.extend(sorted(p for p in scope.rglob("*") if p.is_file()))
    return files


def _frozen_tree_hash() -> str:
    entries: list[str] = []
    for path in _frozen_files():
        rel = path.relative_to(PROJECT_ROOT).as_posix()
        entries.append(rel + "\t" + _sha256(path) + "\n")
    entries.sort()
    return hashlib.sha256("".join(entries).encode("utf-8")).hexdigest().upper()


def _t001_owned_files() -> list[Path]:
    owned = [
        PROJECT_ROOT / ".gitattributes",
        PROJECT_ROOT / ".gitignore",
        PROJECT_ROOT / ".env.example",
        PROJECT_ROOT / ".editorconfig",
        PROJECT_ROOT / "README.md",
        PROJECT_ROOT / "pyproject.toml",
        PROJECT_ROOT / ".github" / "workflows" / "ci.yml",
        PROJECT_ROOT / "scripts" / "verify_project.ps1",
        PROJECT_ROOT / "web" / "README.md",
        PROJECT_ROOT / "contracts" / "README.md",
        PROJECT_ROOT / "fixtures" / "shrgt45" / "README.md",
        PROJECT_ROOT / "tests" / "smoke" / "test_project_structure.py",
    ]
    owned.extend(
        p for p in SRC_ROOT.rglob("*")
        if p.is_file()
        and "__pycache__" not in p.parts
        and not any(part.endswith(".egg-info") for part in p.parts)
    )
    return owned


def test_required_skeleton_paths_exist() -> None:
    required = [
        PROJECT_ROOT / ".gitattributes",
        PROJECT_ROOT / ".gitignore",
        PROJECT_ROOT / ".env.example",
        PROJECT_ROOT / ".editorconfig",
        PROJECT_ROOT / "README.md",
        PROJECT_ROOT / "pyproject.toml",
        PROJECT_ROOT / ".github" / "workflows" / "ci.yml",
        PROJECT_ROOT / "scripts" / "verify_project.ps1",
        PACKAGE_DIR / "__init__.py",
        PACKAGE_DIR / "py.typed",
        PROJECT_ROOT / "web" / "README.md",
        PROJECT_ROOT / "contracts" / "README.md",
        PROJECT_ROOT / "fixtures" / "shrgt45" / "README.md",
    ]
    required += [PACKAGE_DIR / sub / "__init__.py" for sub in _PACKAGE_SUBPACKAGES]
    missing = sorted(str(p.relative_to(PROJECT_ROOT)) for p in required if not p.is_file())
    assert not missing, f"missing required skeleton paths: {missing}"


def test_package_imports_from_src() -> None:
    sys.path.insert(0, str(SRC_ROOT))
    try:
        import ai_scientist_mvp
        from ai_scientist_mvp import api, application, domain, infrastructure, providers, workflow
    finally:
        sys.path.pop(0)

    assert ai_scientist_mvp.__version__ == "0.1.0"
    for module in (api, application, domain, infrastructure, providers, workflow):
        assert module.__name__.startswith("ai_scientist_mvp.")


def test_baseline_lock_and_frozen_artifacts_unchanged() -> None:
    lock_path = PROJECT_ROOT / "governance" / "baseline.lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))

    assert _content_hash(lock) == lock["content_hash"], "baseline.lock.json content_hash mismatch"
    assert lock["status"] == "ACCEPTED"
    assert lock["next_task"] == "tasks/TASK-001.md"

    for doc in lock["documents"]:
        actual = _sha256(PROJECT_ROOT / doc["ref"])
        assert actual == doc["sha256"], f"sha256 mismatch: {doc['ref']}"

    for rec in lock["decision_records"]:
        path = PROJECT_ROOT / rec["ref"]
        record = json.loads(path.read_text(encoding="utf-8"))
        assert _sha256(path) == rec["sha256"], f"sha256 mismatch: {rec['ref']}"
        assert _content_hash(record) == rec["content_hash"], f"content_hash mismatch: {rec['ref']}"
        assert record.get("selected_option_id") == "A", f"expected option A: {rec['ref']}"

    rq_path = PROJECT_ROOT / lock["research_question"]["ref"]
    rq = json.loads(rq_path.read_text(encoding="utf-8"))
    assert _sha256(rq_path) == lock["research_question"]["sha256"], "research question sha256"
    assert _content_hash(rq) == lock["research_question"]["content_hash"], "research question hash"

    wf_path = PROJECT_ROOT / lock["workflow"]["ref"]
    wf = json.loads(wf_path.read_text(encoding="utf-8"))
    assert _sha256(wf_path) == lock["workflow"]["sha256"], "workflow sha256"
    assert _content_hash(wf) == lock["workflow"]["content_hash"], "workflow content_hash"
    assert wf["workflow_version"] == "0.1.0", "workflow version"

    whitelist = PROJECT_ROOT / lock["fixture_scope"]["approved_whitelist_ref"]
    expected = lock["fixture_scope"]["approved_whitelist_sha256"]
    assert _sha256(whitelist) == expected, "whitelist sha256"

    assert _frozen_tree_hash() == FROZEN_TREE_SHA256_T005_CLOSEOUT, (
        "frozen trees changed since T005 closeout; no implementation task may rewrite "
        "AGENTS.md, governance/, docs/contracts/, docs/adr/ or tasks/TASK-001.md"
    )


def test_task001_completion_record_valid() -> None:
    record_path = PROJECT_ROOT / "governance" / "completions" / "TASK-001.completion.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert _content_hash(record) == record["content_hash"], (
        "completion record content_hash mismatch"
    )
    assert record["status"] == "ACCEPTED"
    assert record["verdict"]["implementation"] == "ACCEPTED"
    assert record["verdict"]["formal_closeout"] == "COMPLETED"
    assert record["task_ref"] == "tasks/TASK-001.md"
    assert _sha256(PROJECT_ROOT / record["task_ref"]) == record["task_sha256"]
    next_task = record["verdict"]["next_task"]
    assert next_task == "tasks/TASK-002.md"
    assert _sha256(PROJECT_ROOT / next_task) == record["verdict"]["next_task_sha256"]
    assert record["verdict"]["next_task_status"] == "READY_NOT_STARTED"


def test_task002_completion_record_valid() -> None:
    record_path = PROJECT_ROOT / "governance" / "completions" / "TASK-002.completion.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert _content_hash(record) == record["content_hash"], "T002 completion content_hash mismatch"
    assert record["status"] == "ACCEPTED"
    assert record["verdict"]["implementation"] == "ACCEPTED"
    assert record["verdict"]["independent_review"] == "APPROVED"
    assert record["verdict"]["formal_closeout"] == "COMPLETED"
    assert record["task_ref"] == "tasks/TASK-002.md"
    assert _sha256(PROJECT_ROOT / record["task_ref"]) == record["task_sha256"]
    assert _sha256(PROJECT_ROOT / record["closeout_card_ref"]) == record["closeout_card_sha256"]
    chain = record["implementation_chain"]
    assert chain[-1]["commit_id"] == "167725a231a7db88f421d44a06bcad8351b198db", (
        "accepted implementation HEAD must be 167725a"
    )
    next_task = record["verdict"]["next_task"]
    assert next_task == "tasks/TASK-003.md"
    assert _sha256(PROJECT_ROOT / next_task) == record["verdict"]["next_task_sha256"]
    assert record["verdict"]["next_task_status"] == "READY_NOT_STARTED"


def test_task003_completion_record_valid() -> None:
    record_path = PROJECT_ROOT / "governance" / "completions" / "TASK-003.completion.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert _content_hash(record) == record["content_hash"], "T003 completion content_hash mismatch"
    assert record["status"] == "ACCEPTED"
    assert record["verdict"]["implementation"] == "ACCEPTED"
    assert record["verdict"]["independent_review"] == "WAIVED_BY_PROJECT_OWNER"
    assert record["review_waiver"]["waived_by"] == "project_owner_01"
    assert record["verdict"]["formal_closeout"] == "COMPLETED"
    assert record["task_ref"] == "tasks/TASK-003.md"
    assert _sha256(PROJECT_ROOT / record["task_ref"]) == record["task_sha256"]
    assert _sha256(PROJECT_ROOT / record["correction_card_ref"]) == record["correction_card_sha256"]
    assert _sha256(PROJECT_ROOT / record["closeout_card_ref"]) == record["closeout_card_sha256"]
    assert record["implementation_chain"][-1]["commit_id"] == (
        "0c4ced142e98460e903fd8c7f441c6ba888ecc93"
    )
    fixture = record["fixture_identity"]
    assert fixture["logical_file_count"] == 171
    assert fixture["logical_total_bytes"] == 9_725_849
    assert fixture["s04_0808"]["member_count"] == 90
    assert fixture["s04_0814"]["member_count"] == 43
    for ref_key, sha_key in (
        ("manifest_ref", "manifest_sha256"),
        ("case_manifest_ref", "case_manifest_sha256"),
        ("import_audit_ref", "import_audit_sha256"),
    ):
        assert _sha256(PROJECT_ROOT / fixture[ref_key]) == fixture[sha_key]
    next_task = record["verdict"]["next_task"]
    assert next_task == "tasks/TASK-004.md"
    assert _sha256(PROJECT_ROOT / next_task) == record["verdict"]["next_task_sha256"]
    assert record["verdict"]["next_task_status"] == "READY_NOT_STARTED"
    assert "执行状态：`NOT_STARTED`" in (PROJECT_ROOT / next_task).read_text(encoding="utf-8")


def test_task004_completion_record_valid() -> None:
    record_path = PROJECT_ROOT / "governance" / "completions" / "TASK-004.completion.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert _content_hash(record) == record["content_hash"], "T004 completion content_hash mismatch"
    assert record["status"] == "ACCEPTED"
    assert record["verdict"]["implementation"] == "ACCEPTED"
    assert record["verdict"]["independent_review"] == "APPROVED"
    assert record["verdict"]["formal_closeout"] == "COMPLETED"
    assert record["task_ref"] == "tasks/TASK-004.md"
    assert _sha256(PROJECT_ROOT / record["task_ref"]) == record["task_sha256"]
    assert _sha256(PROJECT_ROOT / record["correction_card_ref"]) == record["correction_card_sha256"]
    assert _sha256(PROJECT_ROOT / record["closeout_card_ref"]) == record["closeout_card_sha256"]
    assert record["implementation_chain"][-1]["commit_id"] == (
        "3143649b11b2ad4b01d7047734d0c9e03554d24b"
    )
    next_task = record["verdict"]["next_task"]
    assert next_task == "tasks/TASK-005.md"
    assert _sha256(PROJECT_ROOT / next_task) == record["verdict"]["next_task_sha256"]
    assert record["verdict"]["next_task_status"] == "READY_NOT_STARTED"
    assert "执行同事只负责本任务的第一次构建" in (
        PROJECT_ROOT / next_task
    ).read_text(encoding="utf-8")


def test_task005_completion_record_valid() -> None:
    record_path = PROJECT_ROOT / "governance" / "completions" / "TASK-005.completion.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert _content_hash(record) == record["content_hash"], "T005 completion content_hash mismatch"
    assert record["status"] == "ACCEPTED"
    assert record["verdict"]["implementation"] == "ACCEPTED"
    assert record["verdict"]["primary_review"] == "APPROVED"
    assert record["verdict"]["formal_closeout"] == "COMPLETED"
    assert record["task_ref"] == "tasks/TASK-005.md"
    assert _sha256(PROJECT_ROOT / record["task_ref"]) == record["task_sha256"]
    assert _sha256(PROJECT_ROOT / record["closeout_card_ref"]) == record["closeout_card_sha256"]
    chain = record["implementation_chain"]
    assert chain[0]["commit_id"] == "9bef2c5cc1de68b87dc33d28a8eb335c417a3feb"
    assert chain[-1]["commit_id"] == "cac55a90a7aff0b0fd17bb5f61a1b5b5c2225d1a"
    outcome = record["accepted_outcome"]
    assert outcome["runtime_source_artifact_count"] == 81
    assert outcome["snapshot_count"] == 6
    assert outcome["validation_report_count"] == 6
    assert outcome["reviewable_finding_count"] == 10
    assert outcome["informational_gap_count"] == 2
    assert outcome["stage_run_count"] == 6
    assert outcome["run_execution_status"] == "WAITING_HUMAN"
    next_task = record["verdict"]["next_task"]
    assert next_task == "tasks/TASK-006.md"
    assert _sha256(PROJECT_ROOT / next_task) == record["verdict"]["next_task_sha256"]
    assert record["verdict"]["next_task_status"] == "READY_NOT_STARTED"
    next_text = (PROJECT_ROOT / next_task).read_text(encoding="utf-8")
    assert "执行状态：`NOT_STARTED`" in next_text
    assert "执行同事只负责本任务的第一次构建" in next_text


def test_root_contains_only_expected_files() -> None:
    allowed = {
        ".editorconfig",
        ".env.example",
        ".gitattributes",
        ".gitignore",
        "config.example.toml",
        "AGENTS.md",
        "README.md",
        "pyproject.toml",
    }
    unexpected = sorted(
        p.name for p in PROJECT_ROOT.iterdir() if p.is_file() and p.name not in allowed
    )
    assert not unexpected, f"unexpected files in project root: {unexpected}"


def test_no_business_implementation_present() -> None:
    allowed_non_init = {
        "domain/types.py",
        "domain/canonical_json.py",
        # T004 persistence kernel (no business logic; ports + local store)
        "domain/errors.py",
        "domain/store_types.py",
        "application/ports.py",
        "application/services.py",
        "infrastructure/paths.py",
        "infrastructure/contract_validation.py",
        "infrastructure/storage.py",
        # T005 offline replay adapter (no LangGraph/FastAPI/network)
        "application/replay_service.py",
        "providers/replay_protocols.py",
        "providers/shrgt45_replay.py",
        "providers/replay_validation.py",
        # T006 LangGraph workflow orchestration (no FastAPI/network)
        "application/replay_workflow_service.py",
        "workflow/state.py",
        "workflow/checkpoint.py",
        "workflow/replay_graph.py",
        "workflow/replay_cli.py",
        # P2 unified Qwen/OpenAI-compatible model boundary.
        "agent/llm/__init__.py",
        "agent/llm/config.py",
        "agent/llm/qwen.py",
        "agent/llm/resilient.py",
        "agent/llm/structured.py",
        "agent/llm/telemetry.py",
        # P3 paper-search Skill (offline provider boundary only).
        "skills/paper_search.py",
    }
    expected_py = (
        {"__init__.py"}
        | {sub + "/__init__.py" for sub in _PACKAGE_SUBPACKAGES}
        | allowed_non_init
    )
    actual_py = {p.relative_to(PACKAGE_DIR).as_posix() for p in PACKAGE_DIR.rglob("*.py")}
    assert actual_py == expected_py, (
        "unexpected .py files under src (business implementation leaked?)"
    )

    for path in PACKAGE_DIR.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(PACKAGE_DIR).as_posix()
        in_workflow = rel == "workflow" or rel.startswith("workflow/")
        for lineno, line in enumerate(text.splitlines(), start=1):
            assert not re.search(r"^\s*(?:import|from)\s+(?:fastapi)\b", line), (
                f"{path.name}:{lineno} imports the api framework"
            )
            if not in_workflow:
                assert not re.search(r"^\s*(?:import|from)\s+(?:langgraph)\b", line), (
                    f"{path.name}:{lineno} imports the orchestration framework outside workflow/"
                )
        assert "eval(" not in text, f"{path.name} contains eval("

    # web/ remains README-only until T008; fixtures/shrgt45/ is legitimately
    # populated by T003 (D-005 fixture import), so only web/ is asserted here.
    for placeholder_dir, note in (
        (PROJECT_ROOT / "web", "frontend pages"),
    ):
        files = sorted(p.name for p in placeholder_dir.rglob("*") if p.is_file())
        assert files == ["README.md"], (
            f"unexpected files in {placeholder_dir} ({note} leaked into an earlier task?)"
        )

    # contracts/ legitimately holds JSON Schema 2020-12 (T002); only schema
    # files and the README may live there.
    for path in (PROJECT_ROOT / "contracts").rglob("*"):
        if path.is_file():
            assert path.name == "README.md" or path.suffix == ".json", (
                f"unexpected file in contracts/: {path.relative_to(PROJECT_ROOT)}"
            )


def test_git_line_ending_policy() -> None:
    attrs = (PROJECT_ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert re.search(r"(?m)^\*\s+-text\s*$", attrs), (
        ".gitattributes must pin byte integrity (* -text) so the SHA-256 locked "
        "baseline is never converted on checkout, on any platform"
    )
    crlf_files = []
    for path in _frozen_files() + _t001_owned_files():
        if b"\r" in path.read_bytes():
            crlf_files.append(path.relative_to(PROJECT_ROOT).as_posix())
    assert not crlf_files, (
        "CRLF line endings found; author files as LF per .editorconfig: " + ", ".join(crlf_files)
    )


def test_env_example_contains_only_placeholders() -> None:
    env_path = PROJECT_ROOT / ".env.example"
    assignments: list[str] = []
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        name, sep, value = line.partition("=")
        assert sep == "=", f"unexpected line in .env.example: {raw!r}"
        assert re.fullmatch(r"[A-Z][A-Z0-9_]*", name), f"bad variable name: {name!r}"
        assert value.strip() in ("", "change_me"), (
            f"non-placeholder value in .env.example: {raw!r}"
        )
        assignments.append(name)
    assert assignments, ".env.example must declare at least one variable"


def test_project_files_have_no_absolute_paths() -> None:
    offenders = []
    for path in _t001_owned_files():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if _DRIVE_PATH.search(line):
                rel = path.relative_to(PROJECT_ROOT).as_posix()
                offenders.append(f"{rel}:{lineno}: {line.strip()}")
    assert not offenders, "machine-specific absolute paths found:\n" + "\n".join(offenders)


def test_project_files_have_no_secrets() -> None:
    offenders = []
    for path in _t001_owned_files():
        if path.name == ".env.example":
            continue  # placeholder values verified by test_env_example_contains_only_placeholders
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if any(pattern.search(line) for pattern in _SECRET_PATTERNS):
                rel = path.relative_to(PROJECT_ROOT).as_posix()
                offenders.append(f"{rel}:{lineno}")
                break
    assert not offenders, "suspected secret values found:\n" + "\n".join(offenders)


def test_pyproject_has_no_business_dependencies() -> None:
    data = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = data["project"]
    assert project["requires-python"] == ">=3.11"
    runtime_deps = [re.split(r"[^A-Za-z0-9_-]", dep)[0] for dep in project["dependencies"]]
    assert runtime_deps == ["jcs", "jsonschema", "langgraph"], (
        f"unexpected runtime dependency: {runtime_deps}"
    )
    for dep in project["optional-dependencies"]["dev"]:
        name = re.split(r"[^A-Za-z0-9_-]", dep)[0]
        assert name in {"pytest", "ruff", "mypy", "jsonschema"}, f"unexpected dev dependency: {dep}"


def test_ci_runs_same_commands_as_local_verification() -> None:
    ci = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    for marker in (
        "pytest tests/smoke",
        "ruff check .",
        "mypy src",
        "import ai_scientist_mvp",
        "verify_project.ps1",
    ):
        assert marker in ci, f"ci.yml missing verification command: {marker}"
