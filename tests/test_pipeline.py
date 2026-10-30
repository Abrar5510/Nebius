from __future__ import annotations

import json
import struct

import h5py
import pytest

from showitonce.artifacts import read_object_demo
from showitonce.contracts import (
    CAPTURE_SCHEMA,
    DEMO_SCHEMA,
    ROBOT_DEMO_SCHEMA,
    SKILL_SCHEMA,
    TASK_SPEC_SCHEMA,
    ContractError,
)
from showitonce.demo import seed_demo_capture
from showitonce.service import Service


def test_mock_pipeline_runs_every_stage(service: Service) -> None:
    capture = seed_demo_capture(service.storage, capture_id="cap_pipeline")
    job = service.create_job(capture["capture_id"], skill="place_cup", robot="so101")
    finished = service.run_job(job.id)

    assert finished.status == "succeeded", finished.error
    assert finished.progress == len(finished.stages) == 10
    assert [stage.status for stage in finished.stages] == ["succeeded"] * 10
    assert finished.error is None

    events = service.events(job.id)
    assert [event["seq"] for event in events] == list(range(1, len(events) + 1))
    assert events[0]["kind"] == "job.queued"
    assert events[1]["kind"] == "job.started"
    assert any(event["kind"] == "job.succeeded" for event in events)
    assert {event["kind"] for event in events} >= {
        "job.queued",
        "job.started",
        "stage.started",
        "stage.completed",
        "job.succeeded",
    }

    outputs = {name: finished.stage(name).output for name in (stage.name for stage in finished.stages)}
    assert outputs["understand"]["task_name"] == "place_cup"
    assert outputs["extract"]["num_frames"] == 120
    assert outputs["verify"]["success"] is True
    assert outputs["multiply"]["multiplier"] == 2042
    assert outputs["train"]["episodes"] == 2042
    assert outputs["evaluate"]["real_robot"] == "pending"
    assert outputs["deploy"]["deployed"] is False
    assert len(outputs["deploy"]["safety_layers"]) == 4
    assert outputs["library"]["version"] == "0.1.0"

    task_spec = service.storage.get_json(outputs["understand"]["task_spec"])
    assert task_spec["schema_version"] == TASK_SPEC_SCHEMA
    assert task_spec["objects"][0]["role"] == "target"

    arrays, meta = read_object_demo(service.storage.local_path(outputs["extract"]["demo"]))
    assert meta["schema_version"] == DEMO_SCHEMA
    assert arrays["object_poses"].shape == (120, 2, 7)
    assert arrays["hand_poses"].shape == (120, 2, 21, 3)
    assert arrays["contacts"].shape == (120, 2, 2)
    assert arrays["times"].shape == (120,)

    hdf5_key = outputs["retarget"]["robot_demo"]
    with h5py.File(service.storage.local_path(hdf5_key), "r") as handle:
        positions = handle["joint_positions"][()]
        actions = handle["actions"][()]
        assert positions.shape == (120, 6)
        assert actions.shape == (120, 6)
        assert list(handle["joint_names"].asstr()[:]) == [
            "shoulder_pan",
            "shoulder_lift",
            "elbow_flex",
            "wrist_flex",
            "wrist_roll",
            "gripper",
        ]
        assert handle.attrs["robot"] == "so101"

    meta = service.storage.get_json(outputs["retarget"]["robot_demo_meta"])
    assert meta["schema_version"] == ROBOT_DEMO_SCHEMA
    assert meta["verified"] is False

    with service.storage.local_path(outputs["train"]["lora"]).open("rb") as handle:
        header_len = struct.unpack("<Q", handle.read(8))[0]
        header = json.loads(handle.read(header_len))
    assert header["__metadata__"]["mock"] == "true"
    assert header["__metadata__"]["skill"] == "place_cup"
    assert len([key for key in header if key != "__metadata__"]) == 0

    usda = service.storage.get_bytes(outputs["reconstruct"]["scene_usd"]).decode()
    assert usda.startswith("#usda 1.0")
    assert "Red_Mug" in usda
    assert "Wooden_Coaster" in usda

    eval_report = service.storage.get_json(outputs["evaluate"]["eval"])
    assert eval_report["rows"][0]["policy"] == "GR00T zero-shot"
    assert eval_report["rows"][-1]["status"] == "pending hardware protocol"

    manifest = service.storage.get_json(outputs["library"]["skill"])
    assert manifest["schema_version"] == SKILL_SCHEMA
    assert manifest["privacy"]["raw_video_included"] is False
    assert manifest["source_job"] == job.id
    assert {item["path"] for item in manifest["files"]} == {
        "task_spec.json",
        "demo_object_centric.npz",
        "demo_object_centric.json",
        "demo_so101.hdf5",
        "lora_so101.safetensors",
        "verification.json",
        "eval.json",
        "deploy.json",
    }


def test_library_bumps_patch_version_for_a_new_job(service: Service) -> None:
    capture = seed_demo_capture(service.storage, capture_id="cap_versions")
    first = service.run_job(service.create_job(capture["capture_id"], skill="place_cup").id)
    second = service.run_job(service.create_job(capture["capture_id"], skill="place_cup").id)
    assert first.stage("library").output["version"] == "0.1.0"
    assert second.stage("library").output["version"] == "0.1.1"

    library = service.library()
    entry = library["skills"]["place-cup"]
    assert entry["latest"] == "0.1.1"
    assert entry["versions"] == ["0.1.0", "0.1.1"]
    manifest = service.skill_manifest("place-cup")
    assert manifest["version"] == "0.1.1"


def test_pipeline_fails_explicitly_for_unknown_robot(service: Service) -> None:
    capture = seed_demo_capture(service.storage, capture_id="cap_bad_robot")
    job = service.run_job(service.create_job(capture["capture_id"], robot="unknown-arm").id)
    assert job.status == "failed"
    assert job.stage("retarget").status == "failed"
    assert "no retarget profile" in (job.stage("retarget").error or "")
    assert job.stage("verify").status == "pending"


def test_run_job_is_idempotent_for_terminal_jobs(service: Service) -> None:
    capture = seed_demo_capture(service.storage, capture_id="cap_idempotent")
    job = service.run_job(service.create_job(capture["capture_id"]).id)
    event_count = len(service.events(job.id))
    rerun = service.run_job(job.id)
    assert rerun.status == "succeeded"
    assert len(service.events(job.id)) == event_count


def test_create_job_requires_a_valid_capture(service: Service) -> None:
    bad = {
        "schema_version": CAPTURE_SCHEMA,
        "capture_id": "cap_bad",
        "task_name": "broken",
    }
    service.storage.put_json("captures/cap_bad/capture.json", bad)
    with pytest.raises(ContractError, match="capture.json failed validation"):
        service.create_job("cap_bad")
