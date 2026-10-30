"""Runtime configuration, loaded from the environment or a local ``.env``.

The default is deliberately credential-free: ``mock`` mode runs the full stage DAG
locally so a new contributor can see the product move before any GPU exists.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path

VALID_MODES = {"mock", "hybrid", "live", "auto"}
VALID_EXECUTION = {"local", "nebius"}


class ConfigError(RuntimeError):
    pass


def load_dotenv(path: Path) -> None:
    """Tiny ``.env`` loader. Existing process variables always win."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass(frozen=True)
class Settings:
    root: Path
    mode: str = "mock"
    execution: str = "local"
    data_dir: Path = field(default_factory=lambda: Path(".showitonce"))
    db_url: str = ""

    token_factory_base_url: str = "https://api.tokenfactory.nebius.com/v1/"
    nebius_api_key: str = ""
    nemotron_fast_model: str = ""
    nemotron_reason_model: str = ""

    cosmos_reason_url: str = ""
    cosmos_reason_api_key: str = ""
    parakeet_url: str = ""
    parakeet_api_key: str = ""

    s3_bucket: str = ""
    s3_endpoint: str = ""
    s3_region: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    storage_backend: str = "local"

    nebius_cli: str = "nebius"
    nebius_project_id: str = ""
    nebius_subnet_id: str = ""
    job_image: str = ""
    job_platform: str = "gpu-l40s-a"
    job_preset: str = "1gpu-8vcpu-32gb"
    job_timeout: str = "2h"

    @property
    def resolved_mode(self) -> str:
        if self.mode != "auto":
            return self.mode
        # Live GPU stages need a real phone capture, so a key alone means hybrid.
        if self.nebius_api_key:
            return "hybrid"
        return "mock"

    @property
    def live_reasoning(self) -> bool:
        """Token Factory and NVIDIA model calls are real (hybrid or live)."""
        return self.resolved_mode in {"hybrid", "live"}

    @property
    def objects_dir(self) -> Path:
        return self.data_dir / "objects"

    @property
    def sqlite_path(self) -> Path:
        if self.db_url.startswith("sqlite:///"):
            raw = self.db_url[len("sqlite:///") :]
            path = Path(raw)
            return path if path.is_absolute() else self.root / path
        return self.data_dir / "showitonce.db"

    def validate(self) -> None:
        if self.mode not in VALID_MODES:
            raise ConfigError(f"SHOWITONCE_MODE must be one of {sorted(VALID_MODES)}, got {self.mode!r}")
        if self.execution not in VALID_EXECUTION:
            raise ConfigError(
                f"SHOWITONCE_EXECUTION must be one of {sorted(VALID_EXECUTION)}, "
                f"got {self.execution!r}"
            )
        if self.execution == "nebius" and not self.job_image:
            raise ConfigError("SHOWITONCE_JOB_IMAGE is required when SHOWITONCE_EXECUTION=nebius")
        if self.execution == "nebius" and not self.nebius_subnet_id:
            raise ConfigError("NEBIUS_SUBNET_ID is required when SHOWITONCE_EXECUTION=nebius")
        if self.storage_backend not in {"local", "s3"}:
            raise ConfigError("SHOWITONCE_STORAGE must be 'local' or 's3'")

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if self.storage_backend == "local":
            self.objects_dir.mkdir(parents=True, exist_ok=True)

    def with_overrides(self, **kwargs: object) -> Settings:
        return replace(self, **kwargs)

    @classmethod
    def from_env(cls, root: Path | None = None) -> Settings:
        root = (root or Path(__file__).resolve().parent.parent).resolve()
        load_dotenv(root / ".env")

        data_dir_raw = _env("SHOWITONCE_DATA_DIR", ".showitonce")
        data_dir = Path(data_dir_raw)
        if not data_dir.is_absolute():
            data_dir = root / data_dir

        bucket = _env("NEBIUS_S3_BUCKET")
        storage = _env("SHOWITONCE_STORAGE") or ("s3" if bucket else "local")
        db_url = _env("SHOWITONCE_DB_URL", f"sqlite:///{data_dir / 'showitonce.db'}")

        settings = cls(
            root=root,
            mode=_env("SHOWITONCE_MODE", "mock").lower(),
            execution=_env("SHOWITONCE_EXECUTION", "local").lower(),
            data_dir=data_dir,
            db_url=db_url,
            token_factory_base_url=_env(
                "TOKEN_FACTORY_BASE_URL", "https://api.tokenfactory.nebius.com/v1/"
            ),
            nebius_api_key=_env("NEBIUS_API_KEY"),
            nemotron_fast_model=_env("NEMOTRON_FAST_MODEL"),
            nemotron_reason_model=_env("NEMOTRON_REASON_MODEL"),
            cosmos_reason_url=_env("COSMOS_REASON_URL").rstrip("/"),
            cosmos_reason_api_key=_env("COSMOS_REASON_API_KEY"),
            parakeet_url=_env("PARAKEET_URL").rstrip("/"),
            parakeet_api_key=_env("PARAKEET_API_KEY"),
            s3_bucket=bucket,
            s3_endpoint=_env("NEBIUS_S3_ENDPOINT"),
            s3_region=_env("NEBIUS_S3_REGION"),
            s3_access_key_id=_env("NEBIUS_S3_ACCESS_KEY_ID"),
            s3_secret_access_key=_env("NEBIUS_S3_SECRET_ACCESS_KEY"),
            storage_backend=storage,
            nebius_cli=_env("NEBIUS_CLI", "nebius"),
            nebius_project_id=_env("NEBIUS_PROJECT_ID"),
            nebius_subnet_id=_env("NEBIUS_SUBNET_ID"),
            job_image=_env("SHOWITONCE_JOB_IMAGE"),
            job_platform=_env("SHOWITONCE_JOB_PLATFORM", "gpu-l40s-a"),
            job_preset=_env("SHOWITONCE_JOB_PRESET", "1gpu-8vcpu-32gb"),
            job_timeout=_env("SHOWITONCE_JOB_TIMEOUT", "2h"),
        )
        settings.validate()
        return settings
