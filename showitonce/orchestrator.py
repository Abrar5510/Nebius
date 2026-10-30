"""Job orchestration: one worker moves a capture through the stage DAG."""

from __future__ import annotations

import threading
import time
import traceback
from typing import Any

from .clients import Clients
from .config import Settings
from .contracts import STAGE_NAMES
from .jobs import Job, JobConflict, SqlJobStore
from .stages import StageContext, StageError, StageHandler, StageResult, build_registry
from .storage import Storage


class Orchestrator:
    def __init__(
        self,
        *,
        settings: Settings,
        storage: Storage,
        jobs: SqlJobStore,
        clients: Clients | None = None,
        registry: dict[str, StageHandler] | None = None,
        max_attempts: int = 2,
        retry_delay_s: float = 1.0,
    ):
        self.settings = settings
        self.storage = storage
        self.jobs = jobs
        self.clients = clients or Clients(settings)
        self.registry = registry or build_registry()
        self.max_attempts = max_attempts
        self.retry_delay_s = retry_delay_s
        missing = [name for name in STAGE_NAMES if name not in self.registry]
        if missing:
            raise RuntimeError(f"stage registry is missing: {missing}")

    def run_job(self, job_id: str, *, claim: bool = True) -> Job:
        job = self.jobs.get_job(job_id)
        if job.status in {"succeeded", "failed", "cancelled"}:
            return job
        if claim and job.status == "running":
            raise JobConflict(f"job {job_id} is already running")
        if claim and job.status == "queued":
            if not self.jobs.claim_job(job_id):
                raise JobConflict(f"job {job_id} is not claimable")
        elif job.status == "queued":
            self.jobs.claim_job(job_id)

        self.jobs.add_event(job_id, "Job started.", kind="job.started")
        for name in STAGE_NAMES:
            current = self.jobs.get_job(job_id)
            if current.stage(name).status == "succeeded":
                continue
            if self._execute_stage(job_id, name) is None:
                return self.jobs.get_job(job_id)

        self.jobs.update_job(job_id, status="succeeded", error=None)
        self.jobs.add_event(job_id, "Skill ready. Every stage passed.", kind="job.succeeded")
        return self.jobs.get_job(job_id)

    def run_stage(self, job_id: str, name: str) -> Job:
        """Execute exactly one stage. Used by the Serverless Jobs entrypoint."""
        if name not in STAGE_NAMES:
            raise KeyError(f"unknown stage: {name}")
        job = self.jobs.get_job(job_id)
        if job.status == "queued":
            self.jobs.claim_job(job_id)
        if job.stage(name).status == "succeeded":
            return self.jobs.get_job(job_id)
        self._execute_stage(job_id, name)
        return self.jobs.get_job(job_id)

    def _execute_stage(self, job_id: str, name: str) -> StageResult | None:
        handler = self.registry[name]
        attempt = 0
        while True:
            attempt += 1
            self.jobs.start_stage(job_id, name)
            self.jobs.add_event(
                job_id,
                f"{name.title()} started" + (f" (attempt {attempt})" if attempt > 1 else "."),
                stage=name,
                kind="stage.started",
            )
            context = StageContext(
                settings=self.settings,
                storage=self.storage,
                job=self.jobs.get_job(job_id),
                stage=name,
                clients=self.clients,
            )
            try:
                result = handler.run(context)
            except StageError as exc:
                if exc.retryable and attempt < self.max_attempts:
                    self.jobs.add_event(
                        job_id,
                        f"{name.title()} hit a transient error; retrying: {exc}",
                        stage=name,
                        kind="stage.retrying",
                        data={"attempt": attempt, "error": str(exc)},
                    )
                    if self.retry_delay_s:
                        time.sleep(self.retry_delay_s * attempt)
                    continue
                self._fail(job_id, name, str(exc), retryable=exc.retryable)
                return None
            except Exception as exc:  # pragma: no cover - defensive boundary
                detail = f"{type(exc).__name__}: {exc}"
                self.jobs.add_event(
                    job_id,
                    f"{name.title()} crashed: {detail}",
                    stage=name,
                    kind="stage.failed",
                    data={"traceback": traceback.format_exc(limit=6)},
                )
                self._fail(job_id, name, detail, retryable=False)
                return None

            output = result.to_dict()
            self.jobs.finish_stage(job_id, name, output)
            line = self.clients.status_line(name, result.summary or f"{name.title()} complete.")
            self.jobs.add_event(
                job_id,
                line,
                stage=name,
                kind="stage.completed",
                data={"summary": result.summary, "output": output},
            )
            self._pace(context)
            return result

    @staticmethod
    def _pace(context: StageContext) -> None:
        """Optional per-job delay so the dashboard can show each stage land.

        This is demo pacing, not simulated work: mock stages still complete instantly
        and every artifact is already written when the delay begins.
        """
        try:
            delay = float(context.job.metadata.get("stage_delay_s", 0) or 0)
        except (TypeError, ValueError):
            delay = 0.0
        if delay > 0:
            time.sleep(delay)

    def _fail(self, job_id: str, stage: str, error: str, *, retryable: bool) -> Job:
        self.jobs.fail_stage(job_id, stage, error)
        self.jobs.update_job(job_id, status="failed", current_stage=stage, error=error)
        self.jobs.add_event(
            job_id,
            f"{stage.title()} failed: {error}",
            stage=stage,
            kind="stage.failed",
            data={"retryable": retryable},
        )
        return self.jobs.get_job(job_id)

    def run_job_async(self, job_id: str) -> threading.Thread:
        def target() -> None:
            try:
                self.run_job(job_id)
            except JobConflict:
                return  # another runner owns it; failing the job would be wrong
            except Exception as exc:  # pragma: no cover - worker boundary
                try:
                    self.jobs.update_job(job_id, status="failed", error=str(exc))
                    self.jobs.add_event(
                        job_id,
                        f"Worker error: {exc}",
                        kind="job.failed",
                        data={"traceback": traceback.format_exc(limit=6)},
                    )
                except Exception:
                    pass

        thread = threading.Thread(target=target, name=f"job-{job_id}", daemon=True)
        thread.start()
        return thread


class Worker:
    """Poll the queue and run jobs. Safe to run as a systemd service or DevPod process."""

    def __init__(self, orchestrator: Orchestrator, poll_interval_s: float = 2.0):
        self.orchestrator = orchestrator
        self.poll_interval_s = poll_interval_s
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run_once(self) -> Job | None:
        job_id = self.orchestrator.jobs.claim_next_queued()
        if not job_id:
            return None
        return self.orchestrator.run_job(job_id, claim=False)

    def run_forever(self, max_jobs: int | None = None) -> int:
        completed = 0
        while not self._stop.is_set():
            job = self.run_once()
            if job is None:
                if max_jobs is not None:
                    break
                self._stop.wait(self.poll_interval_s)
                continue
            completed += 1
            if max_jobs is not None and completed >= max_jobs:
                break
        return completed


def create_job(
    *,
    settings: Settings,
    storage: Storage,
    jobs: SqlJobStore,
    capture_id: str,
    skill: str,
    robot: str = "so101",
    metadata: dict[str, Any] | None = None,
) -> Job:
    from .contracts import validate_capture

    capture = storage.get_json(f"captures/{capture_id}/capture.json")
    validate_capture(capture)
    job = jobs.create_job(capture_id=capture_id, skill=skill, robot=robot, metadata=metadata)
    jobs.add_event(job.id, "Capture queued. Waiting for a worker.", kind="job.queued")
    return job
