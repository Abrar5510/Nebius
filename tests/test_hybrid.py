from __future__ import annotations

import threading
from dataclasses import replace

import pytest

from showitonce.clients import ClientError, parse_json_content
from showitonce.contracts import TASK_SPEC_SCHEMA
from showitonce.demo import seed_demo_capture
from showitonce.jobs import JobConflict
from showitonce.service import Service

# Roles deliberately miss "target", the way a model sometimes answers.
MODEL_SPEC = {
    "schema_version": TASK_SPEC_SCHEMA,
    "task_name": "place_cup",
    "instruction": "Place the red mug on the wooden coaster.",
    "objects": [
        {"id": "mug", "name": "red mug", "role": "object", "material": "ceramic"},
        {"id": "coaster", "name": "wooden coaster", "role": "surface", "material": "wood"},
    ],
    "subtasks": [{"id": "reach", "action": "reach", "target": "red mug"}],
    "success_predicates": [
        {"type": "object_on_surface", "object": "red mug", "surface": "wooden coaster"}
    ],
}


class FakeTokenFactory:
    reason_model = "nvidia/nemotron-ultra-test"
    fast_model = "nvidia/nemotron-nano-test"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def chat_json(self, prompt, *, tier="reason", system=None, max_tokens=1200):
        self.calls.append(tier)
        return {**MODEL_SPEC, "objects": [dict(obj) for obj in MODEL_SPEC["objects"]]}

    def chat(self, prompt, *, tier="fast", system=None, temperature=0.2, max_tokens=1200):
        self.calls.append(tier)
        return "Nano status line."


def test_hybrid_calls_token_factory_and_finishes_every_stage(service: Service) -> None:
    hybrid = Service.bootstrap(replace(service.settings, mode="hybrid"))
    fake = FakeTokenFactory()
    hybrid.clients._cache["token_factory"] = fake
    capture = seed_demo_capture(hybrid.storage, capture_id="cap_hybrid")
    job = hybrid.create_job(capture["capture_id"], skill="place_cup")

    finished = hybrid.run_job(job.id)

    assert finished.status == "succeeded", finished.error
    assert fake.calls.count("reason") == 1  # Ultra compiles the task once
    assert fake.calls.count("fast") == 10  # Nano writes one line per stage
    understand = finished.stage("understand").output
    assert understand["models"] == ["nvidia/nemotron-ultra-test"]
    spec = hybrid.storage.get_json(understand["task_spec"])
    assert spec["objects"][0]["role"] == "target"
    assert hybrid.storage.get_json(understand["understanding"])["synthetic"] is False
    # GPU stages stay honest about being mock.
    assert "mock" in finished.stage("extract").output["source"]


def test_hybrid_without_a_key_fails_without_retrying(service: Service) -> None:
    hybrid = Service.bootstrap(replace(service.settings, mode="hybrid"))
    capture = seed_demo_capture(hybrid.storage, capture_id="cap_nokey")
    job = hybrid.create_job(capture["capture_id"], skill="place_cup")
    finished = hybrid.run_job(job.id)
    assert finished.status == "failed"
    assert "NEBIUS_API_KEY" in (finished.error or "")
    assert finished.stage("understand").attempts == 1


def test_parse_json_content_tolerates_reasoning_wrappers() -> None:
    assert parse_json_content('<think>plan {not json}</think>\n{"a": 1}') == {"a": 1}
    assert parse_json_content('Here is the spec:\n```json\n{"a": 2}\n```') == {"a": 2}
    assert parse_json_content('Sure. {"a": 3} Done.') == {"a": 3}
    with pytest.raises(ClientError):
        parse_json_content("no json here")


def test_a_running_job_cannot_be_started_twice(service: Service) -> None:
    capture = seed_demo_capture(service.storage, capture_id="cap_twice")
    job = service.create_job(
        capture["capture_id"], skill="place_cup", metadata={"stage_delay_s": 0.05}
    )
    first = service.run_job_async(job.id)
    while service.get_job(job.id).status != "running":
        threading.Event().wait(0.01)

    with pytest.raises(JobConflict):
        service.run_job(job.id)
    service.run_job_async(job.id).join()  # swallowed, must not fail the job
    first.join()

    finished = service.get_job(job.id)
    assert finished.status == "succeeded", finished.error
    kinds = [event["kind"] for event in service.events(job.id)]
    assert kinds.count("job.started") == 1
    assert kinds.count("stage.completed") == 10
