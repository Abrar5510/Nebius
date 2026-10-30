"""Stage framework shared by every letter in the build plan."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..clients import Clients
from ..config import Settings
from ..contracts import validate_capture
from ..jobs import Job
from ..storage import Storage, StorageNotFound, guess_content_type


class StageError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


@dataclass
class StageResult:
    output: dict[str, Any] = field(default_factory=dict)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {**self.output, "summary": self.summary}


class StageContext:
    def __init__(
        self,
        *,
        settings: Settings,
        storage: Storage,
        job: Job,
        stage: str,
        clients: Clients,
    ):
        self.settings = settings
        self.storage = storage
        self.job = job
        self.stage = stage
        self.clients = clients
        self.workspace = settings.data_dir / "workspaces" / job.id / stage
        self.workspace.mkdir(parents=True, exist_ok=True)

    @property
    def capture_key(self) -> str:
        return f"captures/{self.job.capture_id}/capture.json"

    def capture(self) -> dict[str, Any]:
        try:
            data = self.storage.get_json(self.capture_key)
        except StorageNotFound as exc:
            raise StageError(f"capture not found: {self.job.capture_id}") from exc
        validate_capture(data)
        return data

    def capture_text(self, name: str, default: str = "") -> str:
        key = f"captures/{self.job.capture_id}/{name}"
        try:
            return self.storage.get_bytes(key).decode("utf-8")
        except StorageNotFound:
            return default

    def key(self, name: str) -> str:
        return f"jobs/{self.job.id}/{self.stage}/{name}"

    def job_key(self, name: str) -> str:
        return f"jobs/{self.job.id}/{name}"

    def put_bytes(
        self, name: str, data: bytes, content_type: str | None = None, *, job_level: bool = False
    ) -> str:
        key = self.job_key(name) if job_level else self.key(name)
        return self.storage.put_bytes(key, data, content_type)

    def put_text(self, name: str, text: str, *, job_level: bool = False) -> str:
        return self.put_bytes(
            name, text.encode("utf-8"), "text/plain; charset=utf-8", job_level=job_level
        )

    def put_json(self, name: str, value: Any, *, job_level: bool = False) -> str:
        key = self.job_key(name) if job_level else self.key(name)
        return self.storage.put_json(key, value)

    def put_file(self, name: str, path: Path, *, job_level: bool = False) -> str:
        key = self.job_key(name) if job_level else self.key(name)
        return self.storage.put_bytes(key, path.read_bytes(), guess_content_type(name))

    def get_json(self, key: str) -> Any:
        return self.storage.get_json(key)

    def previous(self, stage: str) -> dict[str, Any]:
        return self.job.stage(stage).output

    def local(self, name: str) -> Path:
        path = self.workspace / name
        path.parent.mkdir(parents=True, exist_ok=True)
        return path


class StageHandler(ABC):
    name: str
    requires: tuple[str, ...] = ()

    @abstractmethod
    def run(self, ctx: StageContext) -> StageResult: ...
