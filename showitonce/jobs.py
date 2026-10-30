"""Durable job state: a Postgres-compatible schema with SQLite for local runs.

The worker is deliberately boring. A capture becomes a row, stages become child rows,
and every transition writes an append-only event the phone or dashboard can poll.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .contracts import STAGE_NAMES
from .util import iso_now, json_dumps, new_id


class JobNotFound(KeyError):
    pass


class JobConflict(RuntimeError):
    pass


@dataclass
class StageRun:
    name: str
    status: str = "pending"
    attempts: int = 0
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None
    output: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "attempts": self.attempts,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
            "output": self.output,
        }


@dataclass
class Job:
    id: str
    capture_id: str
    skill: str
    robot: str
    status: str
    current_stage: str | None
    created_at: str
    updated_at: str
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    stages: list[StageRun] = field(default_factory=list)

    def stage(self, name: str) -> StageRun:
        for stage in self.stages:
            if stage.name == name:
                return stage
        raise KeyError(name)

    @property
    def progress(self) -> int:
        return sum(1 for stage in self.stages if stage.status == "succeeded")

    def to_dict(self) -> dict[str, Any]:
        order = {name: index for index, name in enumerate(STAGE_NAMES)}
        stages = sorted(self.stages, key=lambda stage: order.get(stage.name, 999))
        return {
            "id": self.id,
            "capture_id": self.capture_id,
            "skill": self.skill,
            "robot": self.robot,
            "status": self.status,
            "current_stage": self.current_stage,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "error": self.error,
            "metadata": self.metadata,
            "stages": [stage.to_dict() for stage in stages],
            "progress": self.progress,
            "stage_count": len(stages),
        }


@dataclass
class Event:
    id: str
    job_id: str
    seq: int
    stage: str | None
    kind: str
    message: str
    data: dict[str, Any]
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "job_id": self.job_id,
            "seq": self.seq,
            "stage": self.stage,
            "kind": self.kind,
            "message": self.message,
            "data": self.data,
            "created_at": self.created_at,
        }


SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS jobs (
        id TEXT PRIMARY KEY,
        capture_id TEXT NOT NULL,
        skill TEXT NOT NULL,
        robot TEXT NOT NULL,
        status TEXT NOT NULL,
        current_stage TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        error TEXT,
        metadata TEXT NOT NULL DEFAULT '{}'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS stage_runs (
        job_id TEXT NOT NULL,
        name TEXT NOT NULL,
        status TEXT NOT NULL,
        attempts INTEGER NOT NULL DEFAULT 0,
        started_at TEXT,
        finished_at TEXT,
        error TEXT,
        output TEXT NOT NULL DEFAULT '{}',
        PRIMARY KEY (job_id, name),
        FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS events (
        id TEXT PRIMARY KEY,
        job_id TEXT NOT NULL,
        seq INTEGER NOT NULL,
        stage TEXT,
        kind TEXT NOT NULL,
        message TEXT NOT NULL,
        data TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        UNIQUE (job_id, seq),
        FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_events_job_seq ON events(job_id, seq)",
]

_PLACEHOLDER = re.compile(r":([a-zA-Z_][a-zA-Z0-9_]*)")


class SqlJobStore:
    """One implementation for SQLite and Postgres via DB-API and named parameters."""

    def __init__(self, db_url: str, root: Path | None = None):
        self.db_url = db_url
        self.root = root
        self.is_postgres = db_url.startswith(("postgres://", "postgresql://"))
        self.is_sqlite = db_url.startswith("sqlite:///") or not self.is_postgres
        self.init_schema()

    # -- connection / SQL -------------------------------------------------
    def _connect(self):
        if self.is_postgres:
            try:
                import psycopg
                from psycopg.rows import dict_row
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError("install the cloud extra: pip install -e '.[cloud]'") from exc
            return psycopg.connect(self.db_url, row_factory=dict_row)
        raw = self.db_url[len("sqlite:///") :] if self.db_url.startswith("sqlite:///") else self.db_url
        path = Path(raw)
        if self.root and not path.is_absolute():
            path = self.root / path
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def _sql(self, sql: str, params: dict[str, Any] | None = None):
        params = params or {}
        if not self.is_postgres:
            return sql, params
        names: list[str] = []

        def repl(match: re.Match[str]) -> str:
            names.append(match.group(1))
            return "%s"

        translated = _PLACEHOLDER.sub(repl, sql)
        return translated, [params[name] for name in names]

    def _execute(self, sql: str, params: dict[str, Any] | None = None, *, commit: bool = True):
        conn = self._connect()
        try:
            statement, values = self._sql(sql, params)
            cursor = conn.execute(statement, values)
            if commit:
                conn.commit()
            return cursor
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_schema(self) -> None:
        conn = self._connect()
        try:
            for statement in SCHEMA:
                conn.execute(statement)
            conn.commit()
        finally:
            conn.close()

    # -- serialisation ----------------------------------------------------
    @staticmethod
    def _row_to_stage(row: Any) -> StageRun:
        return StageRun(
            name=row["name"],
            status=row["status"],
            attempts=int(row["attempts"] or 0),
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            error=row["error"],
            output=json.loads(row["output"] or "{}"),
        )

    def _rows_to_jobs(self, job_rows: Iterable[Any]) -> list[Job]:
        rows = list(job_rows)
        if not rows:
            return []
        ids = [row["id"] for row in rows]
        placeholders = ", ".join(f":id{i}" for i in range(len(ids)))
        params = {f"id{i}": job_id for i, job_id in enumerate(ids)}
        conn = self._connect()
        try:
            statement, values = self._sql(
                f"SELECT * FROM stage_runs WHERE job_id IN ({placeholders})", params
            )
            stage_rows = conn.execute(statement, values).fetchall()
        finally:
            conn.close()
        by_job: dict[str, list[StageRun]] = {}
        for row in stage_rows:
            by_job.setdefault(row["job_id"], []).append(self._row_to_stage(row))
        jobs: list[Job] = []
        stage_order = {name: index for index, name in enumerate(STAGE_NAMES)}
        for row in rows:
            stages = sorted(
                by_job.get(row["id"], []), key=lambda stage: stage_order.get(stage.name, 999)
            )
            jobs.append(
                Job(
                    id=row["id"],
                    capture_id=row["capture_id"],
                    skill=row["skill"],
                    robot=row["robot"],
                    status=row["status"],
                    current_stage=row["current_stage"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                    error=row["error"],
                    metadata=json.loads(row["metadata"] or "{}"),
                    stages=stages,
                )
            )
        return jobs

    # -- jobs -------------------------------------------------------------
    def create_job(
        self,
        capture_id: str,
        skill: str,
        robot: str = "so101",
        metadata: dict[str, Any] | None = None,
        stages: Iterable[str] = STAGE_NAMES,
        job_id: str | None = None,
    ) -> Job:
        job_id = job_id or new_id("job")
        now = iso_now()
        stage_names = list(stages)
        conn = self._connect()
        try:
            insert_job = (
                "INSERT INTO jobs (id, capture_id, skill, robot, status, current_stage, "
                "created_at, updated_at, error, metadata) VALUES "
                "(:id, :capture_id, :skill, :robot, 'queued', :current_stage, :now, :now, NULL, :metadata)"
            )
            statement, values = self._sql(insert_job, {
                "id": job_id,
                "capture_id": capture_id,
                "skill": skill,
                "robot": robot,
                "current_stage": stage_names[0] if stage_names else None,
                "now": now,
                "metadata": json_dumps(metadata or {}).strip(),
            })
            conn.execute(statement, values)
            insert_stage = (
                "INSERT INTO stage_runs (job_id, name, status, attempts, output) "
                "VALUES (:job_id, :name, 'pending', 0, '{}')"
            )
            for name in stage_names:
                statement, values = self._sql(
                    insert_stage, {"job_id": job_id, "name": name}
                )
                conn.execute(statement, values)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return self.get_job(job_id)

    def get_job(self, job_id: str) -> Job:
        conn = self._connect()
        try:
            statement, values = self._sql("SELECT * FROM jobs WHERE id = :id", {"id": job_id})
            row = conn.execute(statement, values).fetchone()
        finally:
            conn.close()
        if row is None:
            raise JobNotFound(job_id)
        return self._rows_to_jobs([row])[0]

    def list_jobs(self, limit: int = 50, status: str | None = None) -> list[Job]:
        sql = "SELECT * FROM jobs"
        params: dict[str, Any] = {"limit": int(limit)}
        if status:
            sql += " WHERE status = :status"
            params["status"] = status
        sql += " ORDER BY created_at DESC LIMIT :limit"
        conn = self._connect()
        try:
            statement, values = self._sql(sql, params)
            rows = conn.execute(statement, values).fetchall()
        finally:
            conn.close()
        return self._rows_to_jobs(rows)

    def update_job(self, job_id: str, **fields: Any) -> None:
        allowed = {"status", "current_stage", "error", "metadata", "capture_id", "skill", "robot"}
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"unknown job fields: {sorted(unknown)}")
        if not fields:
            return
        fields = dict(fields)
        if "metadata" in fields:
            fields["metadata"] = json_dumps(fields["metadata"]).strip()
        fields["updated_at"] = iso_now()
        fields["id"] = job_id
        assignments = ", ".join(f"{key} = :{key}" for key in fields if key != "id")
        self._execute(f"UPDATE jobs SET {assignments} WHERE id = :id", fields)

    def claim_job(self, job_id: str) -> bool:
        now = iso_now()
        cursor = self._execute(
            "UPDATE jobs SET status = 'running', updated_at = :now "
            "WHERE id = :id AND status = 'queued'",
            {"id": job_id, "now": now},
        )
        return cursor.rowcount == 1

    def claim_next_queued(self) -> str | None:
        for _ in range(5):
            conn = self._connect()
            try:
                statement, values = self._sql(
                    "SELECT id FROM jobs WHERE status = 'queued' ORDER BY created_at LIMIT 1"
                )
                row = conn.execute(statement, values).fetchone()
            finally:
                conn.close()
            if row is None:
                return None
            job_id = row["id"]
            if self.claim_job(job_id):
                return job_id
        return None

    def reset_for_retry(self, job_id: str) -> None:
        self._execute(
            "UPDATE jobs SET status = 'queued', error = NULL, updated_at = :now WHERE id = :id",
            {"id": job_id, "now": iso_now()},
        )

    # -- stages -----------------------------------------------------------
    def start_stage(self, job_id: str, name: str) -> StageRun:
        now = iso_now()
        self._execute(
            "UPDATE stage_runs SET status = 'running', attempts = attempts + 1, "
            "started_at = COALESCE(started_at, :now), finished_at = NULL, error = NULL "
            "WHERE job_id = :job_id AND name = :name",
            {"job_id": job_id, "name": name, "now": now},
        )
        self.update_job(job_id, current_stage=name)
        return self.get_job(job_id).stage(name)

    def finish_stage(self, job_id: str, name: str, output: dict[str, Any]) -> None:
        now = iso_now()
        self._execute(
            "UPDATE stage_runs SET status = 'succeeded', finished_at = :now, error = NULL, "
            "output = :output WHERE job_id = :job_id AND name = :name",
            {
                "job_id": job_id,
                "name": name,
                "now": now,
                "output": json_dumps(output).strip(),
            },
        )
        self.update_job(job_id, current_stage=name)

    def fail_stage(self, job_id: str, name: str, error: str) -> None:
        now = iso_now()
        self._execute(
            "UPDATE stage_runs SET status = 'failed', finished_at = :now, error = :error "
            "WHERE job_id = :job_id AND name = :name",
            {"job_id": job_id, "name": name, "now": now, "error": error},
        )

    def skip_stage(self, job_id: str, name: str, reason: str) -> None:
        now = iso_now()
        self._execute(
            "UPDATE stage_runs SET status = 'skipped', finished_at = :now, error = :reason "
            "WHERE job_id = :job_id AND name = :name",
            {"job_id": job_id, "name": name, "now": now, "reason": reason},
        )

    # -- events -----------------------------------------------------------
    def add_event(
        self,
        job_id: str,
        message: str,
        *,
        stage: str | None = None,
        kind: str = "info",
        data: dict[str, Any] | None = None,
    ) -> Event:
        now = iso_now()
        conn = self._connect()
        try:
            if self.is_postgres:
                conn.execute("SELECT id FROM jobs WHERE id = %s FOR UPDATE", (job_id,))
                row = conn.execute(
                    "SELECT COALESCE(MAX(seq), 0) + 1 AS seq FROM events WHERE job_id = %s",
                    (job_id,),
                ).fetchone()
            else:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    "SELECT COALESCE(MAX(seq), 0) + 1 AS seq FROM events WHERE job_id = ?",
                    (job_id,),
                ).fetchone()
            seq = int(row["seq"])
            event = Event(
                id=new_id("evt"),
                job_id=job_id,
                seq=seq,
                stage=stage,
                kind=kind,
                message=message,
                data=data or {},
                created_at=now,
            )
            marker = "%s" if self.is_postgres else "?"
            conn.execute(
                "INSERT INTO events (id, job_id, seq, stage, kind, message, data, created_at) "
                f"VALUES ({marker}, {marker}, {marker}, {marker}, {marker}, {marker}, "
                f"{marker}, {marker})",
                (
                    event.id,
                    event.job_id,
                    event.seq,
                    event.stage,
                    event.kind,
                    event.message,
                    json_dumps(event.data).strip(),
                    event.created_at,
                ),
            )
            conn.execute(
                f"UPDATE jobs SET updated_at = {marker} WHERE id = {marker}",
                (now, job_id),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return event

    def get_events(self, job_id: str, after: int = 0, limit: int = 500) -> list[Event]:
        conn = self._connect()
        try:
            statement, values = self._sql(
                "SELECT * FROM events WHERE job_id = :job_id AND seq > :after "
                "ORDER BY seq LIMIT :limit",
                {"job_id": job_id, "after": int(after), "limit": int(limit)},
            )
            rows = conn.execute(statement, values).fetchall()
        finally:
            conn.close()
        return [
            Event(
                id=row["id"],
                job_id=row["job_id"],
                seq=int(row["seq"]),
                stage=row["stage"],
                kind=row["kind"],
                message=row["message"],
                data=json.loads(row["data"] or "{}"),
                created_at=row["created_at"],
            )
            for row in rows
        ]
