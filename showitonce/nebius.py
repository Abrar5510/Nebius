"""Nebius Serverless Jobs: build the CLI command, submit, and read status.

The orchestrator can run stages locally (default) or submit each stage as a Serverless
Job. This module is the seam between the two; it never hides a missing CLI or project.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any

from .config import Settings


class NebiusError(RuntimeError):
    pass


@dataclass
class ServerlessJobSpec:
    name: str
    image: str
    command: str = "python"
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    platform: str = "gpu-l40s-a"
    preset: str = "1gpu-8vcpu-32gb"
    timeout: str = "2h"
    subnet_id: str = ""
    project_id: str = ""
    disk_size: str = "100Gi"
    volume: str = ""

    def cli_args(self, cli: str = "nebius") -> list[str]:
        args = [
            cli,
            "ai",
            "job",
            "create",
            "--name",
            self.name,
            "--image",
            self.image,
            "--container-command",
            self.command,
            "--args",
            " ".join(self.args),
            "--platform",
            self.platform,
            "--preset",
            self.preset,
            "--timeout",
            self.timeout,
            "--disk-size",
            self.disk_size,
            "--format",
            "json",
        ]
        if self.subnet_id:
            args.extend(["--subnet-id", self.subnet_id])
        if self.project_id:
            args.extend(["--parent-id", self.project_id])
        for key, value in self.env.items():
            args.extend(["--env", f"{key}={value}"])
        if self.volume:
            args.extend(["--volume", self.volume])
        return args


@dataclass
class NebiusJobs:
    settings: Settings

    def spec_for_stage(self, job_id: str, stage: str) -> ServerlessJobSpec:
        if not self.settings.job_image:
            raise NebiusError("SHOWITONCE_JOB_IMAGE is not set")
        env = {
            "SHOWITONCE_MODE": self.settings.resolved_mode,
            "SHOWITONCE_EXECUTION": "local",
            "SHOWITONCE_STORAGE": self.settings.storage_backend,
            "SHOWITONCE_DB_URL": self.settings.db_url,
            "NEBIUS_S3_BUCKET": self.settings.s3_bucket,
            "NEBIUS_S3_ENDPOINT": self.settings.s3_endpoint,
            "NEBIUS_S3_REGION": self.settings.s3_region,
            "NEBIUS_API_KEY": self.settings.nebius_api_key,
            "COSMOS_REASON_URL": self.settings.cosmos_reason_url,
            "PARAKEET_URL": self.settings.parakeet_url,
        }
        return ServerlessJobSpec(
            name=f"showitonce-{stage}-{job_id[-10:]}",
            image=self.settings.job_image,
            args=["-m", "showitonce", "stage", stage, "--job", job_id],
            env={key: value for key, value in env.items() if value},
            platform=self.settings.job_platform,
            preset=self.settings.job_preset,
            timeout=self.settings.job_timeout,
            subnet_id=self.settings.nebius_subnet_id,
            project_id=self.settings.nebius_project_id,
        )

    def submit(self, spec: ServerlessJobSpec, *, dry_run: bool = False) -> dict[str, Any]:
        command = spec.cli_args(self.settings.nebius_cli)
        if dry_run:
            return {"dry_run": True, "command": command}
        executable = shutil.which(self.settings.nebius_cli)
        if not executable:
            raise NebiusError(
                f"{self.settings.nebius_cli!r} not found; install the Nebius CLI or use local execution"
            )
        try:
            result = subprocess.run(
                [executable] + command[1:],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
        except OSError as exc:
            raise NebiusError(f"could not run Nebius CLI: {exc}") from exc
        if result.returncode != 0:
            raise NebiusError(
                f"Nebius job create failed ({result.returncode}): "
                f"{(result.stderr or result.stdout).strip()[:1500]}"
            )
        payload = _last_json(result.stdout)
        operation_id = _dig(payload, "metadata", "id") or payload.get("id")
        resource_id = payload.get("resource_id") or _dig(payload, "metadata", "resource_id")
        return {
            "operation_id": operation_id,
            "resource_id": resource_id,
            "raw": payload,
        }

    def get(self, job_id: str) -> dict[str, Any]:
        executable = shutil.which(self.settings.nebius_cli)
        if not executable:
            raise NebiusError(f"{self.settings.nebius_cli!r} not found")
        result = subprocess.run(
            [executable, "ai", "job", "get", "--id", job_id, "--format", "json"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if result.returncode != 0:
            raise NebiusError(
                f"Nebius job get failed ({result.returncode}): "
                f"{(result.stderr or result.stdout).strip()[:1000]}"
            )
        return _last_json(result.stdout)


def _last_json(output: str) -> dict[str, Any]:
    for line in reversed(output.strip().splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            value = json.loads(line)
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            continue
    raise NebiusError(f"Nebius CLI did not return JSON: {output.strip()[:1000]}")


def _dig(value: Any, *keys: str) -> Any:
    current = value
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current
