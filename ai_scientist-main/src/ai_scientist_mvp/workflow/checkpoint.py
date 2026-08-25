"""Persistent, cross-process LangGraph checkpointer (T006).

The LangGraph internal recovery state must survive a process restart, so it
cannot rely on the in-memory ``MemorySaver``. This saver stores serialized
checkpoints and pending writes in a per-Run SQLite file inside the isolated
``runs/<run_id>/`` directory, exactly like the T004 kernel.

Only reference-level graph state is serialized: the state schema is the small
``ReplayGraphState`` from :mod:`ai_scientist_mvp.workflow.state`, which holds
``ArtifactRef`` / ``VersionedRef`` and routing fields, never payload bytes.
"""
from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

from langgraph.checkpoint.base import (
    WRITES_IDX_MAP,
    BaseCheckpointSaver,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    get_checkpoint_id,
    get_checkpoint_metadata,
)

from ai_scientist_mvp.infrastructure.paths import derive_run_dir

_SCHEMA = """
CREATE TABLE IF NOT EXISTS checkpoints (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    parent_checkpoint_id TEXT,
    type TEXT,
    checkpoint BLOB NOT NULL,
    metadata_type TEXT,
    metadata BLOB,
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
);
CREATE TABLE IF NOT EXISTS writes (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    idx INTEGER NOT NULL,
    channel TEXT NOT NULL,
    type TEXT,
    value BLOB NOT NULL,
    task_path TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
);
"""


def graph_saver_path(runs_root: Path, run_id: str) -> Path:
    """Return the isolated LangGraph checkpointer file for a Run."""
    return derive_run_dir(runs_root, run_id) / "graph.sqlite"


class SqliteGraphSaver(BaseCheckpointSaver[Any]):
    """SQLite-backed LangGraph checkpointer that survives process restart.

    All access is guarded by a lock because LangGraph runs parallel branches
    (S05/S06) on worker threads that may write checkpoints concurrently.
    """

    def __init__(self, path: str | Path) -> None:
        super().__init__()
        self._lock = threading.RLock()
        self._path = Path(path)
        self.conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self.conn.executescript(_SCHEMA)
        self._migrate_schema()
        self.conn.commit()

    def _migrate_schema(self) -> None:
        checkpoint_columns = {
            row[1] for row in self.conn.execute("PRAGMA table_info(checkpoints)")
        }
        if "metadata_type" not in checkpoint_columns:
            self.conn.execute("ALTER TABLE checkpoints ADD COLUMN metadata_type TEXT")
        write_columns = {row[1] for row in self.conn.execute("PRAGMA table_info(writes)")}
        if "task_path" not in write_columns:
            self.conn.execute(
                "ALTER TABLE writes ADD COLUMN task_path TEXT NOT NULL DEFAULT ''"
            )

    def _ids(self, config: Any) -> tuple[str, str, str | None]:
        configurable = config.get("configurable", {})
        thread_id = configurable.get("thread_id")
        if not isinstance(thread_id, str) or not thread_id:
            raise ValueError("checkpointer config requires a configurable.thread_id")
        checkpoint_ns = configurable.get("checkpoint_ns", "") or ""
        checkpoint_id = configurable.get("checkpoint_id")
        return thread_id, checkpoint_ns, checkpoint_id

    def _tuple(
        self, thread_id: str, checkpoint_ns: str, row: tuple[Any, ...] | None
    ) -> CheckpointTuple | None:
        if row is None:
            return None
        checkpoint_id, parent_checkpoint_id, type_, blob, metadata_type, metadata = row
        with self._lock:
            writes = self.conn.execute(
                "SELECT task_id, channel, type, value FROM writes "
                "WHERE thread_id=? AND checkpoint_ns=? AND checkpoint_id=? "
                "ORDER BY task_id, idx",
                (thread_id, checkpoint_ns, checkpoint_id),
            ).fetchall()
        return CheckpointTuple(
            config={
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "checkpoint_id": checkpoint_id,
                }
            },
            checkpoint=self.serde.loads_typed((type_, blob)),
            metadata=self.serde.loads_typed((metadata_type or "msgpack", metadata))
            if metadata is not None
            else {},
            parent_config=(
                {
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_ns": checkpoint_ns,
                        "checkpoint_id": parent_checkpoint_id,
                    }
                }
                if parent_checkpoint_id
                else None
            ),
            pending_writes=[
                (task_id, channel, self.serde.loads_typed((type_, value)))
                for task_id, channel, type_, value in writes
            ],
        )

    def get_tuple(self, config: Any) -> CheckpointTuple | None:
        thread_id, checkpoint_ns, checkpoint_id = self._ids(config)
        with self._lock:
            if checkpoint_id:
                row = self.conn.execute(
                    "SELECT checkpoint_id, parent_checkpoint_id, type, checkpoint, "
                    "metadata_type, metadata "
                    "FROM checkpoints WHERE thread_id=? AND checkpoint_ns=? AND checkpoint_id=?",
                    (thread_id, checkpoint_ns, checkpoint_id),
                ).fetchone()
            else:
                row = self.conn.execute(
                    "SELECT checkpoint_id, parent_checkpoint_id, type, checkpoint, "
                    "metadata_type, metadata "
                    "FROM checkpoints WHERE thread_id=? AND checkpoint_ns=? "
                    "ORDER BY rowid DESC LIMIT 1",
                    (thread_id, checkpoint_ns),
                ).fetchone()
        return self._tuple(thread_id, checkpoint_ns, row)

    def list(
        self,
        config: Any | None,
        *,
        filter: dict[str, Any] | None = None,
        before: Any | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        thread_id = None
        checkpoint_ns = None
        checkpoint_id = None
        if config is not None:
            thread_id, checkpoint_ns, checkpoint_id = self._ids(config)
        before_id = get_checkpoint_id(before) if before else None
        query = (
            "SELECT thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id, "
            "type, checkpoint, metadata_type, metadata FROM checkpoints ORDER BY rowid DESC"
        )
        with self._lock:
            rows = self.conn.execute(query).fetchall()
        for row in rows:
            row_thread, row_ns, row_id, *stored = row
            if thread_id is not None and row_thread != thread_id:
                continue
            if checkpoint_ns is not None and row_ns != checkpoint_ns:
                continue
            if checkpoint_id is not None and row_id != checkpoint_id:
                continue
            if before_id is not None and row_id >= before_id:
                continue
            found = self._tuple(row_thread, row_ns, (row_id, *stored))
            if found is None:
                continue
            if filter and not all(
                found.metadata.get(key) == value for key, value in filter.items()
            ):
                continue
            if limit is not None and limit <= 0:
                break
            yield found
            if limit is not None:
                limit -= 1

    def put(
        self,
        config: Any,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: Any,
    ) -> Any:
        thread_id, checkpoint_ns, parent_checkpoint_id = self._ids(config)
        checkpoint_id = checkpoint["id"]
        type_, blob = self.serde.dumps_typed(checkpoint)
        meta_type, meta_blob = self.serde.dumps_typed(
            get_checkpoint_metadata(config, metadata)
        )
        with self._lock:
            self.conn.execute(
                "INSERT INTO checkpoints(thread_id, checkpoint_ns, checkpoint_id, "
                "parent_checkpoint_id, type, checkpoint, metadata_type, metadata) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (
                    thread_id,
                    checkpoint_ns,
                    checkpoint_id,
                    parent_checkpoint_id,
                    type_,
                    blob,
                    meta_type,
                    meta_blob,
                ),
            )
            self.conn.commit()
        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint_id,
            }
        }

    def put_writes(
        self,
        config: Any,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        thread_id, checkpoint_ns, checkpoint_id = self._ids(config)
        with self._lock:
            for idx, (channel, value) in enumerate(writes):
                type_, blob = self.serde.dumps_typed(value)
                write_idx = WRITES_IDX_MAP.get(channel, idx)
                # INSERT OR IGNORE keeps parallel-branch writes idempotent when
                # LangGraph re-emits the same (task_id, idx) for a checkpoint.
                self.conn.execute(
                    "INSERT OR IGNORE INTO writes(thread_id, checkpoint_ns, checkpoint_id, "
                    "task_id, idx, channel, type, value, task_path) VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        thread_id,
                        checkpoint_ns,
                        checkpoint_id,
                        task_id,
                        write_idx,
                        channel,
                        type_,
                        blob,
                        task_path,
                    ),
                )
            self.conn.commit()

    def close(self) -> None:
        with self._lock:
            self.conn.close()
