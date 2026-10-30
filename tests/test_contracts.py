from __future__ import annotations

import pytest

from showitonce.contracts import (
    CAPTURE_SCHEMA,
    DEMO_SCHEMA,
    EVAL_SCHEMA,
    TASK_SPEC_SCHEMA,
    ContractError,
    next_stage,
    stage_index,
    validate_capture,
    validate_demo_meta,
    validate_eval_report,
    validate_task_spec,
)


def test_stage_order_and_next_stage() -> None:
    assert stage_index("understand") == 0
    assert next_stage("understand") == "reconstruct"
    assert next_stage("library") is None
    with pytest.raises(KeyError):
        stage_index("dance")


def test_valid_capture_round_trips() -> None:
    capture = {
        "schema_version": CAPTURE_SCHEMA,
        "capture_id": "cap_1",
        "task_name": "Move the mug",
        "narration": "Place the mug on the coaster.",
        "room": {"name": "kitchen"},
        "objects": [{"name": "mug"}],
        "duration_s": 4.2,
    }
    assert validate_capture(capture) is capture


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda c: c.update(schema_version="old/v0"), "schema_version"),
        (lambda c: c.pop("capture_id"), "capture_id"),
        (lambda c: c.update(objects="mug"), "objects must be a list"),
        (lambda c: c.update(room=[]), "room must be an object"),
        (lambda c: c.update(duration_s=-3), "duration_s"),
    ],
)
def test_invalid_captures_are_rejected(mutate, message: str) -> None:
    capture = {
        "schema_version": CAPTURE_SCHEMA,
        "capture_id": "cap_1",
        "task_name": "Move the mug",
        "narration": "Place the mug on the coaster.",
        "room": {"name": "kitchen"},
        "objects": [{"name": "mug"}],
        "duration_s": 4.2,
    }
    mutate(capture)
    with pytest.raises(ContractError) as excinfo:
        validate_capture(capture)
    assert message in str(excinfo.value)


def test_task_spec_rejects_unknown_actions_and_predicates() -> None:
    spec = {
        "schema_version": TASK_SPEC_SCHEMA,
        "task_name": "place_cup",
        "instruction": "Place the cup.",
        "objects": [{"name": "cup", "role": "target"}],
        "subtasks": [{"id": "a", "action": "teleport", "target": "cup"}],
        "success_predicates": [{"type": "magic"}],
        "constraints": [{"type": "vibes"}],
    }
    with pytest.raises(ContractError) as excinfo:
        validate_task_spec(spec)
    message = str(excinfo.value)
    assert "subtasks[0].action" in message
    assert "success_predicates[0].type" in message
    assert "constraints[0].type" in message


def test_demo_meta_and_eval_validation() -> None:
    demo = {
        "schema_version": DEMO_SCHEMA,
        "capture_id": "cap_1",
        "objects": [{"name": "cup", "role": "target"}],
        "events": [],
        "fps": 10,
        "num_frames": 5,
    }
    assert validate_demo_meta(demo) is demo
    demo["fps"] = 0
    with pytest.raises(ContractError):
        validate_demo_meta(demo)

    report = {
        "schema_version": EVAL_SCHEMA,
        "rows": [{"policy": "zero-shot", "pose": 0.1, "instance": None}],
    }
    assert validate_eval_report(report) is report
    report["rows"][0]["pose"] = 1.4
    with pytest.raises(ContractError):
        validate_eval_report(report)
