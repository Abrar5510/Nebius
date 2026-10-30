"""Wiring for the CLI, dashboard and worker."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .clients import Clients
from .config import Settings
from .contracts import STAGE_NAMES, validate_capture
from .jobs import Job, SqlJobStore
from .orchestrator import Orchestrator, create_job
from .storage import Storage, StorageNotFound, make_storage


@dataclass
class Service:
    settings: Settings
    storage: Storage
    jobs: SqlJobStore
    clients: Clients
    orchestrator: Orchestrator

    @classmethod
    def bootstrap(cls, settings: Settings | None = None) -> Service:
        settings = settings or Settings.from_env()
        settings.validate()
        storage = make_storage(settings)
        jobs = SqlJobStore(settings.db_url, root=settings.root)
        clients = Clients(settings)
        orchestrator = Orchestrator(
            settings=settings, storage=storage, jobs=jobs, clients=clients
        )
        return cls(
            settings=settings,
            storage=storage,
            jobs=jobs,
            clients=clients,
            orchestrator=orchestrator,
        )

    # -- captures ---------------------------------------------------------
    def list_captures(self) -> list[dict[str, Any]]:
        captures: list[dict[str, Any]] = []
        for key in self.storage.list("captures/"):
            if not key.endswith("/capture.json"):
                continue
            try:
                data = self.storage.get_json(key)
                validate_capture(data)
            except Exception:
                continue
            captures.append(data)
        return sorted(captures, key=lambda item: item.get("created_at", ""), reverse=True)

    def get_capture(self, capture_id: str) -> dict[str, Any]:
        data = self.storage.get_json(f"captures/{capture_id}/capture.json")
        validate_capture(data)
        return data

    def capture_exists(self, capture_id: str) -> bool:
        return self.storage.exists(f"captures/{capture_id}/capture.json")

    # -- jobs -------------------------------------------------------------
    def create_job(
        self,
        capture_id: str,
        skill: str | None = None,
        robot: str = "so101",
        metadata: dict[str, Any] | None = None,
    ) -> Job:
        if metadata is not None and not isinstance(metadata, dict):
            raise ValueError("metadata must be a JSON object")
        capture = self.get_capture(capture_id)
        skill = skill or capture.get("skill") or capture.get("task_name", "new_skill")
        return create_job(
            settings=self.settings,
            storage=self.storage,
            jobs=self.jobs,
            capture_id=capture_id,
            skill=skill,
            robot=robot,
            metadata=metadata,
        )

    def run_job(self, job_id: str) -> Job:
        return self.orchestrator.run_job(job_id)

    def run_job_async(self, job_id: str):
        return self.orchestrator.run_job_async(job_id)

    def list_jobs(self, limit: int = 50) -> list[Job]:
        return self.jobs.list_jobs(limit=limit)

    def get_job(self, job_id: str) -> Job:
        return self.jobs.get_job(job_id)

    def events(self, job_id: str, after: int = 0) -> list[dict[str, Any]]:
        self.jobs.get_job(job_id)
        return [event.to_dict() for event in self.jobs.get_events(job_id, after=after)]

    # -- library ----------------------------------------------------------
    def library(self) -> dict[str, Any]:
        try:
            data = self.storage.get_json("library/index.json")
        except StorageNotFound:
            return {"schema_version": "showitonce.library/v1", "skills": {}}
        if not isinstance(data, dict):
            return {"schema_version": "showitonce.library/v1", "skills": {}}
        return data

    def skill_manifest(self, name: str, version: str | None = None) -> dict[str, Any]:
        data = self.library()
        entry = data.get("skills", {}).get(name)
        if not entry:
            raise StorageNotFound(f"skill not found: {name}")
        version = version or entry.get("latest")
        return self.storage.get_json(f"library/{name}/{version}/skill.json")

    # -- diagnostics ------------------------------------------------------
    def health(self) -> dict[str, Any]:
        return {
            "ok": True,
            "mode": self.settings.resolved_mode,
            "execution": self.settings.execution,
            "storage": self.settings.storage_backend,
            "database": "postgres" if self.jobs.is_postgres else "sqlite",
            "stages": list(STAGE_NAMES),
            "captures": len(self.list_captures()),
            "jobs": len(self.list_jobs(limit=200)),
        }
