from __future__ import annotations

from dataclasses import replace

import pytest

from showitonce.config import ConfigError, Settings
from showitonce.nebius import NebiusError, NebiusJobs, ServerlessJobSpec, _last_json


def test_serverless_spec_builds_cli_command() -> None:
    spec = ServerlessJobSpec(
        name="showitonce-train-job_123",
        image="registry/showitonce:latest",
        command="python",
        args=["-m", "showitonce", "stage", "train", "--job", "job_123"],
        env={"SHOWITONCE_MODE": "live", "NEBIUS_API_KEY": "secret"},
        subnet_id="subnet-1",
        project_id="project-1",
        volume="vol-1",
    )
    command = spec.cli_args()
    assert command[:6] == ["nebius", "ai", "job", "create", "--name", spec.name]
    assert command[command.index("--image") + 1] == spec.image
    assert command[command.index("--args") + 1] == "-m showitonce stage train --job job_123"
    assert command[command.index("--subnet-id") + 1] == "subnet-1"
    assert command[command.index("--parent-id") + 1] == "project-1"
    assert command[command.index("--volume") + 1] == "vol-1"
    assert "SHOWITONCE_MODE=live" in command
    assert "NEBIUS_API_KEY=secret" in command
    assert command[command.index("--format") + 1] == "json"


def test_spec_for_stage_carries_configuration(settings: Settings) -> None:
    settings = replace(
        settings,
        mode="live",
        job_image="registry/showitonce:latest",
        nebius_subnet_id="subnet-1",
        nebius_project_id="project-1",
        s3_bucket="bucket",
        cosmos_reason_url="https://cosmos.example/v1",
        nebius_api_key="key",
    )
    spec = NebiusJobs(settings).spec_for_stage("job_abcdefghijkl", "train")
    assert spec.name == "showitonce-train-cdefghijkl"
    assert spec.args == ["-m", "showitonce", "stage", "train", "--job", "job_abcdefghijkl"]
    assert spec.env["SHOWITONCE_MODE"] == "live"
    assert spec.env["SHOWITONCE_EXECUTION"] == "local"
    assert spec.env["SHOWITONCE_DB_URL"] == settings.db_url
    assert spec.env["NEBIUS_S3_BUCKET"] == "bucket"
    assert spec.env["COSMOS_REASON_URL"] == "https://cosmos.example/v1"
    assert "PARAKEET_URL" not in spec.env


def test_spec_for_stage_requires_an_image(settings: Settings) -> None:
    with pytest.raises(NebiusError, match="SHOWITONCE_JOB_IMAGE"):
        NebiusJobs(settings).spec_for_stage("job_1", "train")


def test_submit_dry_run_does_not_need_the_cli(settings: Settings) -> None:
    settings = replace(settings, job_image="image:latest")
    spec = NebiusJobs(settings).spec_for_stage("job_1", "train")
    payload = NebiusJobs(settings).submit(spec, dry_run=True)
    assert payload["dry_run"] is True
    assert payload["command"][0] == settings.nebius_cli


def test_submit_without_cli_fails_honestly(settings: Settings) -> None:
    settings = replace(settings, job_image="image:latest", nebius_cli="showitonce-missing-cli")
    spec = NebiusJobs(settings).spec_for_stage("job_1", "train")
    with pytest.raises(NebiusError, match="not found"):
        NebiusJobs(settings).submit(spec)


def test_last_json_finds_the_final_json_line() -> None:
    output = 'warning: something\n{"metadata": {"id": "op-1"}, "resource_id": "job-1"}\n'
    assert _last_json(output) == {"metadata": {"id": "op-1"}, "resource_id": "job-1"}
    with pytest.raises(NebiusError):
        _last_json("no json here")


def test_nebius_execution_requires_image_and_subnet(settings: Settings) -> None:
    with pytest.raises(ConfigError, match="SHOWITONCE_JOB_IMAGE"):
        replace(settings, execution="nebius").validate()
    with pytest.raises(ConfigError, match="NEBIUS_SUBNET_ID"):
        replace(settings, execution="nebius", job_image="image").validate()
    replace(
        settings,
        execution="nebius",
        job_image="image",
        nebius_subnet_id="subnet",
    ).validate()
