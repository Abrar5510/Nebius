from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from showitonce.artifacts import build_object_centric_demo, read_object_demo, write_object_demo
from showitonce.contracts import TASK_SPEC_SCHEMA
from showitonce.demo import seed_demo_capture
from showitonce.service import Service
from showitonce.stages import StageContext, StageError
from showitonce.stages.evaluate import EvaluateStage
from showitonce.stages.extract import ExtractStage
from showitonce.stages.multiply import MultiplyStage
from showitonce.stages.reconstruct import ReconstructStage
from showitonce.stages.train import TrainStage

TASK_SPEC = {
    "schema_version": TASK_SPEC_SCHEMA,
    "task_name": "place_cup",
    "instruction": "Place the red mug on the wooden coaster.",
    "objects": [
        {"id": "mug", "name": "red mug", "role": "target", "material": "ceramic"},
        {"id": "coaster", "name": "wooden coaster", "role": "surface", "material": "wood"},
    ],
    "subtasks": [{"id": "reach", "action": "reach", "target": "red mug"}],
    "success_predicates": [{"type": "object_on_surface", "object": "red mug", "surface": "wooden coaster"}],
    "constraints": [],
    "failure_modes": ["drops the mug"],
}


def _prepare(service: Service, tmp_path: Path):
    settings = replace(service.settings, mode="live")
    live = Service.bootstrap(settings)
    capture = seed_demo_capture(live.storage, capture_id="cap_live")
    job = live.create_job(capture["capture_id"], skill="place_cup")
    spec_key = live.storage.put_json(f"jobs/{job.id}/understand/task_spec.json", TASK_SPEC)
    live.jobs.finish_stage(
        job.id,
        "understand",
        {
            "task_spec": spec_key,
            "task_name": TASK_SPEC["task_name"],
            "instruction": TASK_SPEC["instruction"],
            "objects": ["red mug", "wooden coaster"],
        },
    )
    arrays, meta = build_object_centric_demo(capture["capture_id"], TASK_SPEC, num_frames=32)
    meta["synthetic"] = False
    path = tmp_path / "demo_object_centric.npz"
    write_object_demo(path, arrays, meta)
    live.storage.put_bytes(
        f"captures/{capture['capture_id']}/demo_object_centric.npz", path.read_bytes()
    )
    live.storage.put_json(
        f"captures/{capture['capture_id']}/demo_object_centric.json", meta
    )
    return live, job


def test_live_extract_consumes_an_external_foundationpose_demo(
    service: Service, tmp_path: Path
) -> None:
    live, job = _prepare(service, tmp_path)
    context = StageContext(
        settings=live.settings,
        storage=live.storage,
        job=live.get_job(job.id),
        stage="extract",
        clients=live.clients,
    )
    result = ExtractStage().run(context)
    assert result.output["source"] == "foundationpose+wilor"
    assert result.output["num_frames"] == 32
    arrays, meta = read_object_demo(live.storage.local_path(result.output["demo"]))
    assert arrays["object_poses"].shape == (32, 2, 7)
    assert meta["synthetic"] is False


def test_live_reconstruct_refuses_to_fake_a_mesh(service: Service, tmp_path: Path) -> None:
    live, job = _prepare(service, tmp_path)
    context = StageContext(
        settings=live.settings,
        storage=live.storage,
        job=live.get_job(job.id),
        stage="reconstruct",
        clients=live.clients,
    )
    with pytest.raises(StageError, match="mesh"):
        ReconstructStage().run(context)


def test_live_train_refuses_local_execution(service: Service, tmp_path: Path) -> None:
    live, job = _prepare(service, tmp_path)
    context = StageContext(
        settings=live.settings,
        storage=live.storage,
        job=live.get_job(job.id),
        stage="train",
        clients=live.clients,
    )
    with pytest.raises(StageError, match="Serverless Job"):
        TrainStage().run(context)


def test_live_multiply_and_evaluate_do_not_fabricate_results(
    service: Service, tmp_path: Path
) -> None:
    live, job = _prepare(service, tmp_path)
    for stage, handler in (("multiply", MultiplyStage()), ("evaluate", EvaluateStage())):
        context = StageContext(
            settings=live.settings,
            storage=live.storage,
            job=live.get_job(job.id),
            stage=stage,
            clients=live.clients,
        )
        with pytest.raises(StageError, match="not implemented"):
            handler.run(context)
